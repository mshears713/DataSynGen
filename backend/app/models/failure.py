from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.spec import GenerationSpec


class FailureCategory(str, Enum):
    schema_invalid = "schema_invalid"
    semantic_mismatch = "semantic_mismatch"
    wrong_value = "wrong_value"
    wrong_unit = "wrong_unit"
    wrong_measurement_phrase = "wrong_measurement_phrase"
    missing_unit = "missing_unit"
    missing_value = "missing_value"
    extra_measurement = "extra_measurement"
    invalid_json = "invalid_json"
    rejected = "rejected"
    llm_error = "llm_error"
    text_too_short = "text_too_short"
    text_too_long = "text_too_long"
    empty_output = "empty_output"


class Failure(BaseModel):
    failure_id: str
    sample_id: str | None = None
    run_id: str
    failure_category: FailureCategory
    failure_details: str = ""
    original_spec: GenerationSpec
    generated_text: str | None = None
    validator_output: dict | None = None
    raw_error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
