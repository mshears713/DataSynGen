import json

from app.core.logging_config import get_logger
from app.models.config import AppConfig
from app.models.failure import FailureCategory
from app.models.sample import ValidationResult
from app.models.spec import GenerationSpec, ValueKind
from app.services.base import LLMService

logger = get_logger(__name__)

_TOLERANCE_FRACTION = 0.05  # 5% tolerance on numeric comparison


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
    ) -> tuple[ValidationResult, FailureCategory | None]:
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
            )

        extraction = self._parse_extraction(raw_text)
        if extraction is None:
            return (
                ValidationResult(
                    passed=False,
                    errors=["Validator returned invalid JSON"],
                    extracted=None,
                ),
                FailureCategory.invalid_json,
            )

        passed, category, detail = self._compare(spec, extraction)
        errors = [detail] if not passed else []

        return (
            ValidationResult(
                passed=passed,
                errors=errors,
                extracted=extraction,
            ),
            category,
        )

    def _build_prompt(
        self, spec: GenerationSpec, generated_text: str
    ) -> tuple[str, str]:
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

        # Fallback prompt
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
        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            # Try to extract JSON object from surrounding text
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
    ) -> tuple[bool, FailureCategory | None, str]:
        # Check measurement phrase
        extracted_phrase = (extraction.get("measurement_phrase") or "").lower().strip()
        expected_phrase = spec.measurement_phrase.lower().strip()
        if extracted_phrase and extracted_phrase != expected_phrase:
            return (
                False,
                FailureCategory.wrong_measurement_phrase,
                f"Phrase mismatch: expected '{expected_phrase}', got '{extracted_phrase}'",
            )

        # Check unit
        extracted_unit = (extraction.get("unit_norm") or "").lower().strip()
        expected_unit = spec.unit_norm.lower().strip()
        if not extracted_unit:
            return (
                False,
                FailureCategory.missing_unit,
                f"Missing unit in extraction (expected '{expected_unit}')",
            )
        if extracted_unit != expected_unit:
            return (
                False,
                FailureCategory.wrong_unit,
                f"Unit mismatch: expected '{expected_unit}', got '{extracted_unit}'",
            )

        # Check values based on value_kind
        kind = spec.value_kind
        if kind in (ValueKind.exact, ValueKind.approx):
            return self._check_nominal(spec, extraction)
        elif kind in (ValueKind.range, ValueKind.min_max):
            return self._check_range(spec, extraction)
        elif kind == ValueKind.tolerance:
            return self._check_tolerance(spec, extraction)
        elif kind == ValueKind.min_only:
            return self._check_min(spec, extraction)
        elif kind == ValueKind.max_only:
            return self._check_max(spec, extraction)

        return True, None, ""

    def _check_nominal(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, str]:
        extracted = extraction.get("value_nominal")
        if extracted is None:
            return (
                False,
                FailureCategory.missing_value,
                "Missing nominal value in extraction",
            )
        if not self._approx_equal(float(extracted), spec.value_nominal):
            return (
                False,
                FailureCategory.wrong_value,
                f"Value mismatch: expected {spec.value_nominal}, got {extracted}",
            )
        return True, None, ""

    def _check_range(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, str]:
        ext_min = extraction.get("value_min")
        ext_max = extraction.get("value_max")
        if ext_min is None or ext_max is None:
            return (
                False,
                FailureCategory.missing_value,
                "Missing min/max in range extraction",
            )
        if not self._approx_equal(float(ext_min), spec.value_min):
            return (
                False,
                FailureCategory.wrong_value,
                f"Min mismatch: expected {spec.value_min}, got {ext_min}",
            )
        if not self._approx_equal(float(ext_max), spec.value_max):
            return (
                False,
                FailureCategory.wrong_value,
                f"Max mismatch: expected {spec.value_max}, got {ext_max}",
            )
        return True, None, ""

    def _check_tolerance(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, str]:
        ext_nom = extraction.get("value_nominal")
        ext_tol = extraction.get("value_tolerance")
        if ext_nom is None:
            return (
                False,
                FailureCategory.missing_value,
                "Missing nominal value in tolerance extraction",
            )
        if not self._approx_equal(float(ext_nom), spec.value_nominal):
            return (
                False,
                FailureCategory.wrong_value,
                f"Nominal mismatch: expected {spec.value_nominal}, got {ext_nom}",
            )
        return True, None, ""

    def _check_min(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, str]:
        ext_min = extraction.get("value_min")
        if ext_min is None:
            return (
                False,
                FailureCategory.missing_value,
                "Missing min value in extraction",
            )
        if not self._approx_equal(float(ext_min), spec.value_min):
            return (
                False,
                FailureCategory.wrong_value,
                f"Min mismatch: expected {spec.value_min}, got {ext_min}",
            )
        return True, None, ""

    def _check_max(
        self, spec: GenerationSpec, extraction: dict
    ) -> tuple[bool, FailureCategory | None, str]:
        ext_max = extraction.get("value_max")
        if ext_max is None:
            return (
                False,
                FailureCategory.missing_value,
                "Missing max value in extraction",
            )
        if not self._approx_equal(float(ext_max), spec.value_max):
            return (
                False,
                FailureCategory.wrong_value,
                f"Max mismatch: expected {spec.value_max}, got {ext_max}",
            )
        return True, None, ""

    def _approx_equal(self, a: float, b: float | None) -> bool:
        if b is None:
            return False
        if b == 0:
            return abs(a) < 1e-9
        return abs(a - b) / abs(b) <= _TOLERANCE_FRACTION
