from pydantic import BaseModel


class RunMetrics(BaseModel):
    run_id: str
    samples_attempted: int = 0
    samples_valid: int = 0
    samples_failed: int = 0
    schema_valid_rate: float = 0.0
    semantic_match_rate: float = 0.0
    overall_valid_rate: float = 0.0
    failure_breakdown: dict[str, int] = {}
    cost_usd_total: float = 0.0
    cost_per_valid_sample: float | None = None
    avg_latency_ms: float | None = None
    model_usage: dict[str, int] = {}
    prompt_usage: dict[str, int] = {}
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class BenchmarkRow(BaseModel):
    run_id: str
    run_name: str | None = None
    model_ref: str
    model_name: str
    prompt_ref: str
    prompt_version: int
    samples_attempted: int
    samples_valid: int
    valid_rate: float
    semantic_match_rate: float
    cost_usd_total: float
    cost_per_valid: float | None
    avg_latency_ms: float | None
    failure_breakdown: dict[str, int]


class BenchmarkComparison(BaseModel):
    runs: list[BenchmarkRow]
