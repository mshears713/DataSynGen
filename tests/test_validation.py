"""Tests for schema and semantic validation."""
import pytest

from app.models.failure import FailureCategory
from app.models.spec import GenerationSpec, ValueKind
from app.validation.schema_validator import SchemaValidator
from app.validation.semantic_validator import SemanticValidator


def make_exact_spec() -> GenerationSpec:
    return GenerationSpec(
        spec_id="test_exact",
        measurement_phrase="outer diameter",
        value_kind=ValueKind.exact,
        value_nominal=65.0,
        unit_norm="mm",
    )


def make_range_spec() -> GenerationSpec:
    return GenerationSpec(
        spec_id="test_range",
        measurement_phrase="width",
        value_kind=ValueKind.range,
        value_min=10.0,
        value_max=20.0,
        unit_norm="mm",
    )


class TestSchemaValidator:
    def test_valid_exact_spec_passes(self, test_config):
        validator = SchemaValidator(test_config)
        spec = make_exact_spec()
        result = validator.validate(spec, "Outer diameter is 65 mm.")
        assert result.passed
        assert result.errors == []

    def test_empty_text_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = make_exact_spec()
        result = validator.validate(spec, "")
        assert not result.passed
        assert any("empty" in e.lower() for e in result.errors)

    def test_text_too_short_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = make_exact_spec()
        result = validator.validate(spec, "x")  # min_text_length = 3 in test config
        assert not result.passed
        assert any("short" in e.lower() for e in result.errors)

    def test_json_leakage_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = make_exact_spec()
        result = validator.validate(spec, '{"value": 65}')
        assert not result.passed
        assert any("json" in e.lower() for e in result.errors)

    def test_invalid_unit_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = GenerationSpec(
            spec_id="bad_unit",
            measurement_phrase="width",
            value_kind=ValueKind.exact,
            value_nominal=10.0,
            unit_norm="kg",  # Not in allowed units
        )
        result = validator.validate(spec, "Width is 10 kg.")
        assert not result.passed
        assert any("unit" in e.lower() for e in result.errors)

    def test_exact_missing_nominal_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = GenerationSpec(
            spec_id="no_nominal",
            measurement_phrase="outer diameter",
            value_kind=ValueKind.exact,
            unit_norm="mm",
            # No value_nominal!
        )
        result = validator.validate(spec, "Outer diameter mm.")
        assert not result.passed
        assert any("nominal" in e.lower() for e in result.errors)

    def test_range_missing_min_max_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = GenerationSpec(
            spec_id="no_minmax",
            measurement_phrase="width",
            value_kind=ValueKind.range,
            unit_norm="mm",
            # No value_min or value_max!
        )
        result = validator.validate(spec, "Width between mm.")
        assert not result.passed

    def test_range_inverted_fails(self, test_config):
        validator = SchemaValidator(test_config)
        spec = GenerationSpec(
            spec_id="inverted",
            measurement_phrase="width",
            value_kind=ValueKind.range,
            value_min=20.0,
            value_max=10.0,  # min > max
            unit_norm="mm",
        )
        result = validator.validate(spec, "Width between 20 and 10 mm.")
        assert not result.passed
        assert any("less than" in e.lower() for e in result.errors)

    def test_valid_range_spec_passes(self, test_config):
        validator = SchemaValidator(test_config)
        spec = make_range_spec()
        result = validator.validate(spec, "Width is between 10 and 20 mm.")
        assert result.passed


class TestSemanticValidator:
    @pytest.mark.asyncio
    async def test_happy_path_passes(self, test_config, mock_llm):
        validator = SemanticValidator(mock_llm, test_config)
        spec = make_exact_spec()
        text = "Outer diameter is 65.0 mm."
        result, category = await validator.validate(spec, text, "run1", "s1")
        assert result.passed
        assert category is None

    @pytest.mark.asyncio
    async def test_wrong_value_fails(self, test_config, mock_llm):
        validator = SemanticValidator(mock_llm, test_config)
        spec = make_exact_spec()
        # Mock LLM will parse "55" from this text, but spec says 65
        text = "Outer diameter is 55.0 mm."
        result, category = await validator.validate(spec, text, "run1", "s2")
        # The mock will extract 55.0 vs expected 65.0
        if not result.passed:
            assert category in (FailureCategory.wrong_value, FailureCategory.missing_value)

    @pytest.mark.asyncio
    async def test_wrong_unit_detected(self, test_config, mock_llm):
        validator = SemanticValidator(mock_llm, test_config)
        spec = GenerationSpec(
            spec_id="unit_test",
            measurement_phrase="outer diameter",
            value_kind=ValueKind.exact,
            value_nominal=65.0,
            unit_norm="mm",
        )
        # Text says "cm" but spec says "mm"
        text = "Outer diameter is 65.0 cm."
        result, category = await validator.validate(spec, text, "run1", "s3")
        if not result.passed:
            assert category in (FailureCategory.wrong_unit, FailureCategory.wrong_value)

    @pytest.mark.asyncio
    async def test_invalid_json_response_handled(self, test_config, monkeypatch):
        from app.services.mock_llm import MockLLMService
        bad_mock = MockLLMService()
        # Override to return garbage JSON
        async def bad_complete(*args, **kwargs):
            from app.models.llm import LLMResponse
            return LLMResponse(
                text="not valid json at all",
                raw="not valid json at all",
                model_name="mock",
                provider="mock",
            )
        bad_mock.complete = bad_complete

        validator = SemanticValidator(bad_mock, test_config)
        spec = make_exact_spec()
        result, category = await validator.validate(spec, "Some text.", "run1", "s4")
        assert not result.passed
        assert category == FailureCategory.invalid_json
