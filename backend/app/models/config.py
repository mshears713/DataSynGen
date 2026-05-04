from typing import Any

from pydantic import BaseModel, field_validator, model_validator


class ModelEntry(BaseModel):
    provider: str = "tokenrouter"
    model: str
    enabled: bool = True
    notes: str = ""


class PromptEntry(BaseModel):
    task: str
    title: str
    active: bool = True
    version: int = 1
    template: str
    notes: str = ""


class TaskProfile(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 150
    retry_count: int = 3
    timeout: int = 30


class TaskRoute(BaseModel):
    model_ref: str
    prompt_ref: str
    profile_ref: str


class UnitsConfig(BaseModel):
    allowed: list[str] = ["mm", "cm", "in"]


class ValueKindsConfig(BaseModel):
    allowed: list[str] = ["exact", "approx", "range", "tolerance", "min_only", "max_only", "min_max"]


class ValidationSettings(BaseModel):
    max_text_length: int = 500
    min_text_length: int = 5


class GenerationSettings(BaseModel):
    default_batch_size: int = 10
    max_retries_on_empty: int = 2


class ExportSettings(BaseModel):
    default_format: str = "jsonl"


class ProjectMeta(BaseModel):
    name: str = "measurement_dataset_foundry"
    domain: str = "measurement_extraction"


class AppConfig(BaseModel):
    project: ProjectMeta = ProjectMeta()
    measurement_phrases: list[str]
    units: UnitsConfig = UnitsConfig()
    value_kinds: ValueKindsConfig = ValueKindsConfig()
    models: dict[str, ModelEntry]
    prompts: dict[str, PromptEntry]
    profiles: dict[str, TaskProfile]
    tasks: dict[str, TaskRoute]
    validation: ValidationSettings = ValidationSettings()
    generation: GenerationSettings = GenerationSettings()
    export: ExportSettings = ExportSettings()

    @model_validator(mode="after")
    def validate_task_refs(self) -> "AppConfig":
        for task_name, route in self.tasks.items():
            if route.model_ref not in self.models:
                raise ValueError(
                    f"Task '{task_name}' references unknown model_ref '{route.model_ref}'"
                )
            if route.prompt_ref not in self.prompts:
                raise ValueError(
                    f"Task '{task_name}' references unknown prompt_ref '{route.prompt_ref}'"
                )
            if route.profile_ref not in self.profiles:
                raise ValueError(
                    f"Task '{task_name}' references unknown profile_ref '{route.profile_ref}'"
                )
        return self

    @field_validator("measurement_phrases")
    @classmethod
    def validate_phrases_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("measurement_phrases must not be empty")
        return v
