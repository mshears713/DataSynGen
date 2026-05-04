from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    created = "created"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class RunConfig(BaseModel):
    generation_model_ref: str
    validation_model_ref: str
    generation_prompt_ref: str
    validation_prompt_ref: str
    generation_profile_ref: str
    validation_profile_ref: str


class Run(BaseModel):
    run_id: str
    name: str | None = None
    status: RunStatus = RunStatus.created
    run_config: RunConfig
    target_count: int = 10
    samples_attempted: int = 0
    samples_valid: int = 0
    samples_failed: int = 0
    cost_usd_total: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    notes: str = ""
    seed: int = 0


class RunCreate(BaseModel):
    name: str | None = None
    target_count: int = 10
    notes: str = ""
    generation_model_ref: str | None = None
    validation_model_ref: str | None = None
    generation_prompt_ref: str | None = None
    validation_prompt_ref: str | None = None
    generation_profile_ref: str | None = None
    validation_profile_ref: str | None = None
    seed: int = 0


class RunAppend(BaseModel):
    additional_count: int = 10


class RunEvent(BaseModel):
    event_id: str
    run_id: str
    kind: str
    message: str
    data: dict = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)
