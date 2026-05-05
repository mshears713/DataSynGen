import json

from app.core.logging_config import get_logger
from app.models.config import AppConfig
from app.models.failure import FailureCategory
from app.models.sample import ValidationResult
from app.models.spec import GenerationSpec, ValueKind
from app.services.base import LLMService
from app.validation.normalizer import (
    approx_equal,
    normalize_number,
    normalize_phrase,
    normalize_unit,
    normalize_value_kind,
)

logger = get_logger(__name__)


def _fc(field: str, expected, actual_raw, actual_normalized, matched: bool, reason: str = "") -> dict:
    """Build a field-comparison dict."""
    return {
        "field": field,
        "expected": expected,
        "actual_raw": actual_raw,
        "actual_normalized": actual_normalized,
        "matched": matched,
        "reason": reason,
    }


class SemanticValidator:
    def __init__(self, llm_service: LLMService, config: AppConfig):
        self._llm = llm_service
        self._config = config

    async def validate(
        self,
        spec: GenerationSpec,
        generated_text: str,
        run_id: str,
        sample_id: str,
    ) -> tuple[ValidationResult, FailureCategory | None, str]:
        """
        Returns (ValidationResult, FailureCategory | None, raw_validator_text).
        raw_validator_text is the raw LLM response before parsing (empty on LLM error).
        """
        prompt, system = self._build_prompt(spec, generated_text)

        try:
            response = await self._llm.complete(
                prompt=prompt,
                system=system,
                task="validation",
                run_id=run_id,
                sample_id=sample_id,
            )
            raw_text = response.text
        except Exception as e:
            logger.warning(f"Semantic validation LLM call failed: {e}")
            return (
                ValidationResult(
                    passed=False,
                    errors=[f"Validator LLM call failed: {e}"],
                ),
                FailureCategory.llm_error,
                "",
            )

        extraction = self._parse_extraction(raw_text)
        if extraction is None:
            return (
                ValidationResult(
                    passed=False,
                    errors=["Validator returned invalid JSON"],
                    extracted={"raw": raw_text[:500]},
                ),
                FailureCategory.invalid_json,
                raw_text,
            )

        passed, category, field_comparisons, errors = self._compare(spec, extraction)

        return (
            ValidationResult(
                passed=passed,
                errors=errors,
                extracted={
                    "raw_extraction": extraction,
                    "field_comparisons": field_comparisons,
                },
            ),
            category,
            raw_text,
        )

    def _build_prompt(self, spec: GenerationSpec, generated_text: str) -> tuple[str, str]:
        route = self._config.tasks.get("validation")
        if route:
            prompt_entry = self._config.prompts.get(route.prompt_ref)
            if prompt_entry:
                user_prompt = prompt_entry.template.format(
                    generated_text=generated_text,
                    measurement_phrase=spec.measurement_phrase,
                    value_kind=spec.value_kind.value,
                    unit_norm=spec.unit_norm,
                )
                return user_prompt, "You are a precise measurement extraction system. Return only valid JSON."

        user_prompt = (
            f'Extract the measurement information from the following utterance and return it as JSON.\n\n'
            f'Utterance: "{generated_text}"\n\n'
            'Return a JSON object with these fields (use null for missing values):\n'
            '{\n'
            '  "measurement_phrase": "<the measurement being described>",\n'
            '  "value_kind": "<exact|approx|range|tolerance|min_only|max_only|min_max>",\n'
            '  "value_nominal": <number or null>,\n'
            '  "value_min": <number or null>,\n'
            '  "value_max": <number or null>,\n'
            '  "value_tolerance": <number or null>,\n'
            '  "unit_norm": "<mm|cm|in or null>"\n'
            '}\n\n'
            'Return only the JSON object. No explanation, no markdown.'
        )
        return user_prompt, "You are a precise measurement extraction system. Return only valid JSON."

    def _parse_extraction(self, raw: str) -> dict | None:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            import re
            m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass
        return None

    def _compare(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, list[dict], list[str]]:
        """
        Returns (passed, failure_category, field_comparisons, error_messages).
        """
        configured_phrases = self._config.measurement_phrases
        comparisons: list[dict] = []
        errors: list[str] = []
        category: FailureCategory | None = None

        # ── Phrase ──────────────────────────────────────────────────────────
        raw_phrase = extraction.get("measurement_phrase") or ""
        normalized_phrase = normalize_phrase(raw_phrase, configured_phrases)
        expected_phrase = spec.measurement_phrase.lower().strip()
        phrase_matched = (
            normalized_phrase is not None
            and normalized_phrase.lower().strip() == expected_phrase
        )
        comparisons.append(_fc(
            "measurement_phrase",
            expected=spec.measurement_phrase,
            actual_raw=raw_phrase,
            actual_normalized=normalized_phrase,
            matched=phrase_matched,
            reason="" if phrase_matched else (
                f"expected '{spec.measurement_phrase}', "
                f"got '{raw_phrase}' (normalized: '{normalized_phrase}')"
            ),
        ))
        if not phrase_matched:
            errors.append(f"Phrase mismatch: expected '{spec.measurement_phrase}', got '{raw_phrase}'")
            category = FailureCategory.wrong_measurement_phrase
            return False, category, comparisons, errors

        # ── Unit ────────────────────────────────────────────────────────────
        raw_unit = extraction.get("unit_norm") or ""
        normalized_unit = normalize_unit(raw_unit) or raw_unit.lower().strip()
        expected_unit = spec.unit_norm.lower().strip()
        unit_matched = normalized_unit == expected_unit

        if not unit_matched and not raw_unit:
            comparisons.append(_fc(
                "unit", expected=spec.unit_norm,
                actual_raw=raw_unit, actual_normalized=normalized_unit,
                matched=False, reason=f"missing unit (expected '{spec.unit_norm}')",
            ))
            errors.append(f"Missing unit in extraction (expected '{spec.unit_norm}')")
            return False, FailureCategory.missing_unit, comparisons, errors

        comparisons.append(_fc(
            "unit", expected=spec.unit_norm,
            actual_raw=raw_unit, actual_normalized=normalized_unit,
            matched=unit_matched,
            reason="" if unit_matched else f"expected '{spec.unit_norm}', got '{raw_unit}' (→'{normalized_unit}')",
        ))
        if not unit_matched:
            errors.append(f"Unit mismatch: expected '{spec.unit_norm}', got '{raw_unit}'")
            return False, FailureCategory.wrong_unit, comparisons, errors

        # ── Values (by kind) ─────────────────────────────────────────────────
        kind = spec.value_kind
        if kind in (ValueKind.exact, ValueKind.approx):
            ok, val_cat, val_comps, val_errs = self._check_nominal(spec, extraction)
        elif kind in (ValueKind.range, ValueKind.min_max):
            ok, val_cat, val_comps, val_errs = self._check_range(spec, extraction)
        elif kind == ValueKind.tolerance:
            ok, val_cat, val_comps, val_errs = self._check_tolerance(spec, extraction)
        elif kind == ValueKind.min_only:
            ok, val_cat, val_comps, val_errs = self._check_min(spec, extraction)
        elif kind == ValueKind.max_only:
            ok, val_cat, val_comps, val_errs = self._check_max(spec, extraction)
        else:
            ok, val_cat, val_comps, val_errs = True, None, [], []

        comparisons.extend(val_comps)
        errors.extend(val_errs)
        if not ok:
            return False, val_cat or FailureCategory.semantic_mismatch, comparisons, errors

        return True, None, comparisons, []

    def _check_nominal(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, list[dict], list[str]]:
        raw = extraction.get("value_nominal")
        norm = normalize_number(raw)
        expected = spec.value_nominal
        matched = approx_equal(norm, expected)
        fc = _fc(
            "value_nominal", expected=expected,
            actual_raw=raw, actual_normalized=norm,
            matched=matched,
            reason="" if matched else (
                "missing nominal value" if norm is None else
                f"expected {expected}, got {norm}"
            ),
        )
        if not matched:
            return False, FailureCategory.missing_value if norm is None else FailureCategory.wrong_value, [fc], [fc["reason"]]
        return True, None, [fc], []

    def _check_range(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, list[dict], list[str]]:
        comps: list[dict] = []
        errors: list[str] = []

        raw_min = extraction.get("value_min")
        norm_min = normalize_number(raw_min)
        min_matched = approx_equal(norm_min, spec.value_min)
        fc_min = _fc("value_min", spec.value_min, raw_min, norm_min, min_matched,
                     "" if min_matched else (
                         "missing min value" if norm_min is None else
                         f"expected {spec.value_min}, got {norm_min}"))
        comps.append(fc_min)

        raw_max = extraction.get("value_max")
        norm_max = normalize_number(raw_max)
        max_matched = approx_equal(norm_max, spec.value_max)
        fc_max = _fc("value_max", spec.value_max, raw_max, norm_max, max_matched,
                     "" if max_matched else (
                         "missing max value" if norm_max is None else
                         f"expected {spec.value_max}, got {norm_max}"))
        comps.append(fc_max)

        if not min_matched:
            errors.append(fc_min["reason"])
            return False, FailureCategory.missing_value if norm_min is None else FailureCategory.wrong_value, comps, errors
        if not max_matched:
            errors.append(fc_max["reason"])
            return False, FailureCategory.missing_value if norm_max is None else FailureCategory.wrong_value, comps, errors
        return True, None, comps, []

    def _check_tolerance(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, list[dict], list[str]]:
        raw = extraction.get("value_nominal")
        norm = normalize_number(raw)
        expected = spec.value_nominal
        matched = approx_equal(norm, expected)
        fc = _fc("value_nominal", expected, raw, norm, matched,
                 "" if matched else (
                     "missing nominal value" if norm is None else
                     f"expected {expected}, got {norm}"))
        if not matched:
            return False, FailureCategory.missing_value if norm is None else FailureCategory.wrong_value, [fc], [fc["reason"]]
        return True, None, [fc], []

    def _check_min(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, list[dict], list[str]]:
        raw = extraction.get("value_min")
        norm = normalize_number(raw)
        expected = spec.value_min
        matched = approx_equal(norm, expected)
        fc = _fc("value_min", expected, raw, norm, matched,
                 "" if matched else (
                     "missing min value" if norm is None else
                     f"expected {expected}, got {norm}"))
        if not matched:
            return False, FailureCategory.missing_value if norm is None else FailureCategory.wrong_value, [fc], [fc["reason"]]
        return True, None, [fc], []

    def _check_max(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, list[dict], list[str]]:
        raw = extraction.get("value_max")
        norm = normalize_number(raw)
        expected = spec.value_max
        matched = approx_equal(norm, expected)
        fc = _fc("value_max", expected, raw, norm, matched,
                 "" if matched else (
                     "missing max value" if norm is None else
                     f"expected {expected}, got {norm}"))
        if not matched:
            return False, FailureCategory.missing_value if norm is None else FailureCategory.wrong_value, [fc], [fc["reason"]]
        return True, None, [fc], []
