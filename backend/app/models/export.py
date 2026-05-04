from datetime import datetime

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    run_ids: list[str]
    format: str = "jsonl"
    include_only_valid: bool = True
    include_only_export_flagged: bool = True
    filter_measurement_phrase: list[str] | None = None
    filter_value_kind: list[str] | None = None
    filter_model_ref: list[str] | None = None
    filter_prompt_ref: list[str] | None = None


class ExportManifest(BaseModel):
    export_id: str
    run_ids: list[str]
    format: str
    filters: dict
    sample_count: int
    file_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
