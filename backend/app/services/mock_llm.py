import json
import re

from app.models.llm import LLMResponse


class MockLLMService:
    """Deterministic mock LLM service for testing. No real API calls."""

    def __init__(self, deterministic: bool = True, fail_after: int = -1):
        self._deterministic = deterministic
        self._fail_after = fail_after  # fail after N calls (-1 = never)
        self._call_count = 0

    async def complete(
        self,
        prompt: str,
        system: str,
        task: str,
        run_id: str,
        sample_id: str | None = None,
    ) -> LLMResponse:
        self._call_count += 1

        if self._fail_after >= 0 and self._call_count > self._fail_after:
            from app.core.exceptions import LLMCallError
            raise LLMCallError(
                message="Mock LLM forced failure",
                detail=f"Call #{self._call_count} exceeded fail_after={self._fail_after}",
                retryable=False,
            )

        if task == "validation":
            text = self._make_validation_response(prompt)
        else:
            text = self._make_generation_response(prompt)

        return LLMResponse(
            text=text,
            raw=text,
            model_name="mock/model",
            provider="mock",
            input_tokens=50,
            output_tokens=20,
            latency_ms=10.0,
            cost_usd=0.0,
        )

    def _make_generation_response(self, prompt: str) -> str:
        phrase = self._extract_field(prompt, "Phrase")
        value_kind = self._extract_field(prompt, "Value kind")
        nominal = self._extract_field(prompt, "Nominal value")
        value_min = self._extract_field(prompt, "Min value")
        value_max = self._extract_field(prompt, "Max value")
        unit = self._extract_field(prompt, "Unit")

        phrase_str = phrase or "measurement"
        unit_str = unit or "mm"
        kind = (value_kind or "exact").lower()

        if kind in ("range", "min_max") and value_min and value_max:
            try:
                mn = float(value_min)
                mx = float(value_max)
                return f"{phrase_str.capitalize()} is between {mn} and {mx} {unit_str}."
            except ValueError:
                pass

        if kind == "min_only" and value_min:
            try:
                mn = float(value_min)
                return f"{phrase_str.capitalize()} at least {mn} {unit_str}."
            except ValueError:
                pass

        if kind == "max_only" and value_max:
            try:
                mx = float(value_max)
                return f"{phrase_str.capitalize()} at most {mx} {unit_str}."
            except ValueError:
                pass

        if kind == "tolerance" and nominal:
            tol = self._extract_field(prompt, "Tolerance")
            try:
                n = float(nominal)
                t = float(tol) if tol and tol not in ("None", "null", "none") else 0.1
                return f"{phrase_str.capitalize()} is {n} plus or minus {t} {unit_str}."
            except ValueError:
                pass

        if nominal and nominal not in ("None", "null", "none"):
            try:
                n = float(nominal)
                qualifier = "approximately " if kind == "approx" else ""
                return f"{phrase_str.capitalize()} is {qualifier}{n} {unit_str}."
            except ValueError:
                pass

        return f"{phrase_str.capitalize()} measures in {unit_str}."

    def _make_validation_response(self, prompt: str) -> str:
        # Extract the utterance from the prompt - try several common patterns
        utterance_match = re.search(
            r'(?:Utterance|utterance|Extract from|extract from|Text|text):\s*"([^"]+)"',
            prompt,
        )
        if not utterance_match:
            # Try any quoted string in the prompt
            utterance_match = re.search(r'"([^"]{10,})"', prompt)
        if not utterance_match:
            return json.dumps({
                "measurement_phrase": None,
                "value_kind": None,
                "value_nominal": None,
                "value_min": None,
                "value_max": None,
                "value_tolerance": None,
                "unit_norm": None,
            })

        utterance = utterance_match.group(1)

        # Parse the utterance to extract measurement info
        phrase = None
        value_kind = "exact"
        nominal = None
        val_min = None
        val_max = None
        tolerance = None
        unit_norm = None

        # Detect unit
        for u in ["mm", "cm", "in"]:
            if u in utterance.lower():
                unit_norm = u
                break

        # Detect values
        numbers = re.findall(r"\b\d+(?:\.\d+)?\b", utterance)

        lower = utterance.lower()
        if "between" in lower or "and" in lower:
            value_kind = "range"
            if len(numbers) >= 2:
                val_min = float(numbers[0])
                val_max = float(numbers[1])
        elif "at least" in lower or "minimum" in lower:
            value_kind = "min_only"
            if numbers:
                val_min = float(numbers[0])
        elif "at most" in lower or "maximum" in lower:
            value_kind = "max_only"
            if numbers:
                val_max = float(numbers[0])
        elif "plus or minus" in lower or "±" in lower:
            value_kind = "tolerance"
            if len(numbers) >= 2:
                nominal = float(numbers[0])
                tolerance = float(numbers[1])
        elif "approximately" in lower or "approx" in lower:
            value_kind = "approx"
            if numbers:
                nominal = float(numbers[0])
        else:
            value_kind = "exact"
            if numbers:
                nominal = float(numbers[0])

        # Detect phrase (simple keyword matching)
        phrases = [
            "outer diameter", "inner diameter", "overall length", "width", "height",
            "thickness", "depth", "hole diameter", "slot width", "flange thickness",
            "radius", "wall thickness",
        ]
        for p in phrases:
            if p in lower:
                phrase = p
                break

        return json.dumps({
            "measurement_phrase": phrase,
            "value_kind": value_kind,
            "value_nominal": nominal,
            "value_min": val_min,
            "value_max": val_max,
            "value_tolerance": tolerance,
            "unit_norm": unit_norm,
        })

    def _extract_field(self, prompt: str, field: str) -> str | None:
        pattern = rf"- {re.escape(field)}:\s*(.+)"
        m = re.search(pattern, prompt)
        if m:
            val = m.group(1).strip()
            return val if val not in ("None", "null", "none", "") else None
        return None
