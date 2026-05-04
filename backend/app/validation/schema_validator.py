from app.models.config import AppConfig
from app.models.sample import ValidationResult
from app.models.spec import GenerationSpec, ValueKind


class SchemaValidator:
    def __init__(self, config: AppConfig):
        self._config = config

    def validate(self, spec: GenerationSpec, generated_text: str) -> ValidationResult:
        errors: list[str] = []

        # Text checks
        errors.extend(self._check_text(generated_text))

        # Spec structural checks
        errors.extend(self._check_value_kind_fields(spec))

        # Unit check
        errors.extend(self._check_unit(spec))

        return ValidationResult(passed=len(errors) == 0, errors=errors)

    def _check_text(self, text: str) -> list[str]:
        errors = []
        if not text or not text.strip():
            errors.append("Generated text is empty")
            return errors

        stripped = text.strip()
        val = self._config.validation

        if len(stripped) < val.min_text_length:
            errors.append(
                f"Text too short: {len(stripped)} chars (min {val.min_text_length})"
            )
        if len(stripped) > val.max_text_length:
            errors.append(
                f"Text too long: {len(stripped)} chars (max {val.max_text_length})"
            )

        # Check for JSON/metadata leakage
        if stripped.startswith("{") or stripped.startswith("["):
            errors.append("Generated text appears to be JSON (metadata leakage)")

        return errors

    def _check_value_kind_fields(self, spec: GenerationSpec) -> list[str]:
        errors = []
        kind = spec.value_kind

        if kind in (ValueKind.exact, ValueKind.approx):
            if spec.value_nominal is None:
                errors.append(f"value_kind '{kind}' requires value_nominal")

        elif kind in (ValueKind.range, ValueKind.min_max):
            if spec.value_min is None:
                errors.append(f"value_kind '{kind}' requires value_min")
            if spec.value_max is None:
                errors.append(f"value_kind '{kind}' requires value_max")
            if (
                spec.value_min is not None
                and spec.value_max is not None
                and spec.value_min >= spec.value_max
            ):
                errors.append("value_min must be less than value_max")

        elif kind == ValueKind.tolerance:
            if spec.value_nominal is None:
                errors.append("value_kind 'tolerance' requires value_nominal")
            if spec.value_tolerance is None:
                errors.append("value_kind 'tolerance' requires value_tolerance")
            elif spec.value_tolerance <= 0:
                errors.append("value_tolerance must be positive")

        elif kind == ValueKind.min_only:
            if spec.value_min is None:
                errors.append("value_kind 'min_only' requires value_min")

        elif kind == ValueKind.max_only:
            if spec.value_max is None:
                errors.append("value_kind 'max_only' requires value_max")

        return errors

    def _check_unit(self, spec: GenerationSpec) -> list[str]:
        allowed = self._config.units.allowed
        if spec.unit_norm not in allowed:
            return [f"Unit '{spec.unit_norm}' not in allowed units: {allowed}"]
        return []
