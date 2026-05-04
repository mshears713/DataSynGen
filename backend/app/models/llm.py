from pydantic import BaseModel


class LLMResponse(BaseModel):
    text: str
    raw: str
    model_name: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0
    cost_usd: float | None = None


class ModelMetadata(BaseModel):
    model_ref: str
    model_name: str
    provider: str
    prompt_ref: str
    prompt_version: int
    task: str
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
