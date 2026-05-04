from enum import Enum

from pydantic import BaseModel


class ValueKind(str, Enum):
    exact = "exact"
    approx = "approx"
    range = "range"
    tolerance = "tolerance"
    min_only = "min_only"
    max_only = "max_only"
    min_max = "min_max"


class GenerationSpec(BaseModel):
    spec_id: str
    measurement_phrase: str
    value_kind: ValueKind
    value_nominal: float | None = None
    value_min: float | None = None
    value_max: float | None = None
    value_tolerance: float | None = None
    unit_norm: str
    seed: int = 0
    tags: list[str] = []
