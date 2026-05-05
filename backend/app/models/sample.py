from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.llm import ModelMetadata
from app.models.spec import GenerationSpec


class SampleStatus(str, Enum):
    valid = "valid"
    failed = "failed"
    pending_review = "pending_review"


class ValidationResult(BaseModel):
    passed: bool
    errors: list[str] = []
    extracted: dict | None = None


class Sample(BaseModel):
    sample_id: str
    run_id: str
    spec_id: str
    spec: GenerationSpec
    generated_text: str
    raw_llm_output: str          # raw generation LLM response
    raw_validator_output: str | None = None  # raw validator LLM response
    status: SampleStatus
    schema_validation: ValidationResult
    semantic_validation: ValidationResult | None = None
    model_metadata: ModelMetadata
    include_in_export: bool = True
    review_tags: list[str] = []
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SampleUpdate(BaseModel):
    review_tags: list[str] | None = None
    notes: str | None = None
    include_in_export: bool | None = None
    status: SampleStatus | None = None


class SampleFilter(BaseModel):
    status: SampleStatus | None = None
    measurement_phrase: str | None = None
    value_kind: str | None = None
    model_ref: str | None = None
    prompt_ref: str | None = None
    include_in_export: bool | None = None
    limit: int = 100
    offset: int = 0
