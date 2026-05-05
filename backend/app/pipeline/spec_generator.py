import hashlib
import json
import random
from typing import Iterator

from app.models.config import AppConfig
from app.models.spec import GenerationSpec, ValueKind


class SpecGenerator:
    def __init__(self, config: AppConfig):
        self._config = config

    def generate_specs(
        self,
        count: int,
        seed: int = 0,
        constraint_units: list[str] | None = None,
        constraint_phrases: list[str] | None = None,
        constraint_value_kinds: list[str] | None = None,
    ) -> list[GenerationSpec]:
        """Generate a deterministic list of specs.

        If constraint_* args are provided they narrow the sampling pool but
        determinism is preserved: same seed + same constraints + same count
        always produces the same spec list.
        """
        rng = random.Random(seed)
        phrases = constraint_phrases or self._config.measurement_phrases
        kinds = [ValueKind(k) for k in (constraint_value_kinds or self._config.value_kinds.allowed)]
        units = constraint_units or self._config.units.allowed

        if not phrases:
            raise ValueError("No measurement phrases available after applying constraints")
        if not kinds:
            raise ValueError("No value kinds available after applying constraints")
        if not units:
            raise ValueError("No units available after applying constraints")

        specs: list[GenerationSpec] = []
        for i in range(count):
            phrase = rng.choice(phrases)
            kind = rng.choice(kinds)
            unit = rng.choice(units)
            item_seed = seed * 10000 + i
            values = self._generate_values(kind, rng)
            spec = GenerationSpec(
                spec_id=self._make_spec_id(phrase, kind, unit, values, item_seed),
                measurement_phrase=phrase,
                value_kind=kind,
                unit_norm=unit,
                seed=item_seed,
                **values,
            )
            specs.append(spec)
        return specs

    def generate_specs_lazy(self, count: int, seed: int = 0) -> Iterator[GenerationSpec]:
        yield from self.generate_specs(count, seed)

    def _make_spec_id(
        self,
        phrase: str,
        kind: ValueKind,
        unit: str,
        values: dict,
        seed: int,
    ) -> str:
        canonical = json.dumps(
            {
                "phrase": phrase,
                "kind": kind.value,
                "unit": unit,
                "seed": seed,
                **{k: v for k, v in sorted(values.items()) if v is not None},
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def _generate_values(self, kind: ValueKind, rng: random.Random) -> dict:
        def rand_val() -> float:
            return round(rng.uniform(1.0, 500.0), 2)

        if kind in (ValueKind.exact, ValueKind.approx):
            return {"value_nominal": rand_val()}

        elif kind in (ValueKind.range, ValueKind.min_max):
            lo = rand_val()
            hi = round(lo + rng.uniform(0.5, 50.0), 2)
            return {"value_min": lo, "value_max": hi}

        elif kind == ValueKind.tolerance:
            nominal = rand_val()
            tol = round(rng.uniform(0.01, 5.0), 3)
            return {"value_nominal": nominal, "value_tolerance": tol}

        elif kind == ValueKind.min_only:
            return {"value_min": rand_val()}

        elif kind == ValueKind.max_only:
            return {"value_max": rand_val()}

        return {}
