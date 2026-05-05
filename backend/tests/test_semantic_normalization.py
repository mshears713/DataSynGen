"""
Regression tests for semantic validation normalization logic.

Run with:  python -m pytest backend/tests/test_semantic_normalization.py -v
Or directly: python backend/tests/test_semantic_normalization.py

These tests exercise normalizer.py + the _compare() method of SemanticValidator
without making any LLM calls (no tokenrouter required).
"""
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.validation.normalizer import (
    approx_equal,
    normalize_number,
    normalize_phrase,
    normalize_unit,
    normalize_value_kind,
)
from app.models.spec import GenerationSpec, ValueKind
from app.validation.semantic_validator import SemanticValidator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONFIGURED_PHRASES = [
    "outer diameter", "inner diameter", "overall length",
    "width", "height", "thickness", "depth",
    "hole diameter", "slot width", "flange thickness",
    "radius", "wall thickness",
]


def make_spec(phrase, kind, nominal=None, min_=None, max_=None, tol=None, unit="mm"):
    return GenerationSpec(
        spec_id="test-spec",
        measurement_phrase=phrase,
        value_kind=ValueKind(kind),
        value_nominal=nominal,
        value_min=min_,
        value_max=max_,
        value_tolerance=tol,
        unit_norm=unit,
    )


class FakeLLM:
    """Returns a pre-set JSON string without calling any API."""
    def __init__(self, response_text: str):
        self._text = response_text

    async def complete(self, **kwargs):
        from app.models.llm import LLMResponse
        return LLMResponse(text=self._text, raw=self._text, model_name="test", provider="test")


class FakeConfig:
    measurement_phrases = CONFIGURED_PHRASES

    class tasks:
        @staticmethod
        def get(name):
            return None

    class prompts:
        @staticmethod
        def get(name):
            return None


def make_validator(json_response: str) -> SemanticValidator:
    import types
    config = types.SimpleNamespace(
        measurement_phrases=CONFIGURED_PHRASES,
        tasks=types.SimpleNamespace(get=lambda k: None),
        prompts=types.SimpleNamespace(get=lambda k: None),
    )
    validator = SemanticValidator.__new__(SemanticValidator)
    validator._config = config
    validator._llm = FakeLLM(json_response)
    return validator


async def run_compare(validator: SemanticValidator, spec: GenerationSpec, extraction: dict):
    """Call _compare directly (sync-ish via extraction dict)."""
    return validator._compare(spec, extraction)


# ---------------------------------------------------------------------------
# Unit normalizer tests
# ---------------------------------------------------------------------------

def test_unit_mm_variants():
    assert normalize_unit("millimeter") == "mm"
    assert normalize_unit("millimeters") == "mm"
    assert normalize_unit("mm") == "mm"
    # normalize_unit strips and lowercases before lookup
    assert normalize_unit("MM") == "mm"
    assert normalize_unit("Millimeters") == "mm"


def test_unit_cm_variants():
    assert normalize_unit("centimeter") == "cm"
    assert normalize_unit("centimeters") == "cm"
    assert normalize_unit("cm") == "cm"


def test_unit_in_variants():
    assert normalize_unit("inch") == "in"
    assert normalize_unit("inches") == "in"
    assert normalize_unit("in") == "in"


def test_unit_unknown():
    assert normalize_unit("meters") is None
    assert normalize_unit("") is None
    assert normalize_unit(None) is None


# ---------------------------------------------------------------------------
# Phrase normalizer tests
# ---------------------------------------------------------------------------

def test_phrase_exact():
    assert normalize_phrase("radius", CONFIGURED_PHRASES) == "radius"
    assert normalize_phrase("width", CONFIGURED_PHRASES) == "width"
    assert normalize_phrase("depth", CONFIGURED_PHRASES) == "depth"


def test_phrase_with_value_and_unit():
    # The key regression: "radius to 371.03 millimeters" -> "radius"
    result = normalize_phrase("radius to 371.03 millimeters", CONFIGURED_PHRASES)
    assert result == "radius", f"expected 'radius', got '{result}'"


def test_phrase_outer_diameter_wins_over_diameter():
    # "outer diameter" should win over "diameter" (not in list) or "inner diameter"
    result = normalize_phrase("the outer diameter measurement", CONFIGURED_PHRASES)
    assert result == "outer diameter", f"got '{result}'"


def test_phrase_inner_diameter():
    result = normalize_phrase("inner diameter of 10.5 mm", CONFIGURED_PHRASES)
    assert result == "inner diameter", f"got '{result}'"


def test_phrase_wall_thickness():
    result = normalize_phrase("wall thickness is 3.2 mm", CONFIGURED_PHRASES)
    assert result == "wall thickness", f"got '{result}'"


def test_phrase_no_match():
    result = normalize_phrase("something unrelated", CONFIGURED_PHRASES)
    assert result is None


# ---------------------------------------------------------------------------
# Numeric normalizer tests
# ---------------------------------------------------------------------------

def test_numeric_int():
    assert normalize_number(371) == 371.0
    assert normalize_number("371") == 371.0


def test_numeric_float_trailing_zero():
    # 371.030 and 371.03 should be equal after normalization
    assert normalize_number("371.030") == normalize_number("371.03")
    assert approx_equal(normalize_number("371.030"), normalize_number("371.03"))


def test_numeric_approx_equal():
    # Within 5% tolerance
    assert approx_equal(100.0, 104.0)   # 4% diff → pass
    assert not approx_equal(100.0, 110.0)  # 10% diff → fail


def test_numeric_none():
    assert normalize_number(None) is None
    assert not approx_equal(None, 10.0)


# ---------------------------------------------------------------------------
# _compare() integration tests (no LLM)
# ---------------------------------------------------------------------------

import asyncio


def compare(phrase, kind, extraction, nominal=None, min_=None, max_=None, tol=None, unit="mm"):
    """Helper: run _compare and return (passed, category, comparisons, errors)."""
    spec = make_spec(phrase, kind, nominal=nominal, min_=min_, max_=max_, tol=tol, unit=unit)
    validator = make_validator("{}")  # response doesn't matter for _compare
    return asyncio.get_event_loop().run_until_complete(
        run_compare(validator, spec, extraction)
    )


def test_case_A_radius_exact_mm():
    """A: radius exact 371.03 mm — should pass."""
    passed, cat, comps, errs = compare(
        "radius", "exact",
        {
            "measurement_phrase": "radius to 371.03 millimeters",
            "value_kind": "exact",
            "value_nominal": 371.03,
            "unit_norm": "millimeters",
        },
        nominal=371.03, unit="mm",
    )
    assert passed, f"Should pass but errors: {errs}\ncomparisons: {comps}"


def test_case_B_width_approx_mm():
    """B: width approx 368.5 mm — should pass."""
    passed, cat, comps, errs = compare(
        "width", "approx",
        {
            "measurement_phrase": "width",
            "value_kind": "approx",
            "value_nominal": 368.5,
            "unit_norm": "mm",
        },
        nominal=368.5, unit="mm",
    )
    assert passed, f"Should pass but errors: {errs}"


def test_case_C_radius_max_only_in():
    """C: radius max_only 44.38 in — 'Maximum radius is 44.38 inches' should pass."""
    passed, cat, comps, errs = compare(
        "radius", "max_only",
        {
            "measurement_phrase": "radius",
            "value_kind": "max_only",
            "value_nominal": None,
            "value_max": 44.38,
            "unit_norm": "inches",
        },
        max_=44.38, unit="in",
    )
    assert passed, f"Should pass but errors: {errs}"


def test_case_D_width_min_only_in():
    """D: width min_only 14.24 in — 'at least 14.24 inches' should pass."""
    passed, cat, comps, errs = compare(
        "width", "min_only",
        {
            "measurement_phrase": "width",
            "value_kind": "min_only",
            "value_min": 14.24,
            "unit_norm": "in",
        },
        min_=14.24, unit="in",
    )
    assert passed, f"Should pass but errors: {errs}"


def test_case_E_depth_exact_word_number():
    """E: depth exact 47.75 mm — word-number 'forty-seven point seven five' should fail with clear message."""
    passed, cat, comps, errs = compare(
        "depth", "exact",
        {
            "measurement_phrase": "depth",
            "value_kind": "exact",
            "value_nominal": None,  # validator couldn't parse word-number
            "unit_norm": "mm",
        },
        nominal=47.75, unit="mm",
    )
    assert not passed
    # Failure message must clearly say value issue, not phrase or unit mismatch
    assert any("value" in e.lower() or "nominal" in e.lower() for e in errs), (
        f"Expected value mismatch error, got: {errs}"
    )


def test_phrase_mismatch_produces_clear_error():
    passed, cat, comps, errs = compare(
        "radius", "exact",
        {"measurement_phrase": "wall thickness", "value_nominal": 10.0, "unit_norm": "mm"},
        nominal=10.0, unit="mm",
    )
    assert not passed
    assert any("phrase" in e.lower() or "mismatch" in e.lower() for e in errs), f"errs: {errs}"


def test_unit_mismatch_produces_clear_error():
    passed, cat, comps, errs = compare(
        "radius", "exact",
        {"measurement_phrase": "radius", "value_nominal": 10.0, "unit_norm": "cm"},
        nominal=10.0, unit="mm",
    )
    assert not passed
    assert any("unit" in e.lower() for e in errs), f"errs: {errs}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [
        test_unit_mm_variants,
        test_unit_cm_variants,
        test_unit_in_variants,
        test_unit_unknown,
        test_phrase_exact,
        test_phrase_with_value_and_unit,
        test_phrase_outer_diameter_wins_over_diameter,
        test_phrase_inner_diameter,
        test_phrase_wall_thickness,
        test_phrase_no_match,
        test_numeric_int,
        test_numeric_float_trailing_zero,
        test_numeric_approx_equal,
        test_numeric_none,
        test_case_A_radius_exact_mm,
        test_case_B_width_approx_mm,
        test_case_C_radius_max_only_in,
        test_case_D_width_min_only_in,
        test_case_E_depth_exact_word_number,
        test_phrase_mismatch_produces_clear_error,
        test_unit_mismatch_produces_clear_error,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERR   {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)
