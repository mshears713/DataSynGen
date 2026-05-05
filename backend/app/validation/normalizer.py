"""
Normalizer for extracted measurement fields.

All functions are pure (no I/O, no config required except where stated).
Used by SemanticValidator to canonicalize LLM-extracted values before comparison.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------

_UNIT_ALIASES: dict[str, str] = {
    # millimeter variants
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
    "mm": "mm",
    # centimeter variants
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetre": "cm",
    "centimetres": "cm",
    "cm": "cm",
    # inch variants
    "inch": "in",
    "inches": "in",
    "in": "in",
    '"': "in",
}

_UNIT_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_UNIT_ALIASES, key=len, reverse=True)) + r'|")\b',
    re.IGNORECASE,
)

_UNIT_WORDS = set(_UNIT_ALIASES.keys())  # used for phrase stripping


def normalize_unit(raw: str | None) -> str | None:
    """Map any unit word/symbol to canonical (mm/cm/in) or return None."""
    if not raw:
        return None
    key = raw.strip().lower().rstrip(".")
    return _UNIT_ALIASES.get(key)


def extract_unit_from_text(text: str) -> str | None:
    """Find the first recognized unit in free text and return canonical form."""
    m = _UNIT_PATTERN.search(text)
    if m:
        return _UNIT_ALIASES.get(m.group(0).lower().rstrip("."))
    return None


# ---------------------------------------------------------------------------
# Value kind normalization
# ---------------------------------------------------------------------------

_KIND_PHRASES: list[tuple[str, str]] = [
    # order matters — longer phrases first
    ("plus or minus", "tolerance"),
    ("no more than", "max_only"),
    ("at most", "max_only"),
    ("at least", "min_only"),
    ("between", "range"),
    ("approximately", "approx"),
    ("approximate", "approx"),
    ("roughly", "approx"),
    ("about", "approx"),
    ("around", "approx"),
    ("minimum", "min_only"),
    ("maximum", "max_only"),
    ("min_only", "min_only"),
    ("max_only", "max_only"),
    ("min", "min_only"),
    ("max", "max_only"),
    ("approx", "approx"),
    ("tolerance", "tolerance"),
    ("exact", "exact"),
    ("+/-", "tolerance"),
    ("±", "tolerance"),
]


def normalize_value_kind(raw: str | None) -> str | None:
    """Map extracted value_kind to a canonical kind string."""
    if not raw:
        return None
    key = raw.strip().lower()
    for phrase, kind in _KIND_PHRASES:
        if phrase in key:
            return kind
    # Pass through recognized canonical kinds
    canonical = {"exact", "approx", "range", "tolerance", "min_only", "max_only", "min_max"}
    if key in canonical:
        return key
    return raw.strip()


# ---------------------------------------------------------------------------
# Phrase normalization
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_PUNCT_RE = re.compile(r"[^\w\s]")
_MULTI_SPACE_RE = re.compile(r"\s+")

# Words to strip when cleaning extracted phrases
_STRIP_WORDS = (
    set(_UNIT_ALIASES.keys())
    | {"set", "to", "the", "a", "an", "is", "are", "of", "at", "be", "needs"}
)


def _clean_phrase(text: str) -> str:
    """Lowercase, strip numbers, strip unit words/symbols, collapse spaces."""
    text = text.lower().strip()
    text = _NUMBER_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    words = [w for w in text.split() if w not in _STRIP_WORDS]
    return _MULTI_SPACE_RE.sub(" ", " ".join(words)).strip()


def normalize_phrase(raw: str | None, configured_phrases: list[str]) -> str | None:
    """
    Map an extracted phrase (possibly verbose) to the best matching configured phrase.

    Strategy:
    1. Exact match (normalized) — fastest path
    2. Longest configured phrase whose words all appear in the cleaned extracted phrase
    3. Cleaned extracted phrase contained within a configured phrase string
    4. Return None if nothing matches
    """
    if not raw:
        return None

    cleaned = _clean_phrase(raw)
    configured_lower = [p.lower() for p in configured_phrases]

    # 1. Exact match after cleaning
    for i, cp in enumerate(configured_lower):
        if _clean_phrase(cp) == cleaned:
            return configured_phrases[i]

    # 2. All words of a configured phrase appear in extracted (longest wins)
    matches: list[tuple[int, str]] = []
    cleaned_words = set(cleaned.split())
    for i, cp in enumerate(configured_lower):
        cp_words = set(cp.split())
        if cp_words and cp_words.issubset(cleaned_words):
            matches.append((len(cp), configured_phrases[i]))
    if matches:
        return max(matches, key=lambda x: x[0])[1]

    # 3. Cleaned phrase appears inside a configured phrase
    for i, cp in enumerate(configured_lower):
        if cleaned and cleaned in cp:
            return configured_phrases[i]

    return None


# ---------------------------------------------------------------------------
# Numeric normalization
# ---------------------------------------------------------------------------

def normalize_number(raw) -> float | None:
    """Convert raw value to float, treating 371.03 == 371.030."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def approx_equal(a: float | None, b: float | None, tolerance: float = 0.05) -> bool:
    """True if a ≈ b within relative tolerance (default 5%)."""
    if a is None or b is None:
        return False
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= tolerance
