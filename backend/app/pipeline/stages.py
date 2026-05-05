"""
Stage-based pipeline architecture.

Each stage receives a shared StageContext, performs its work,
and returns a StageResult indicating what should happen next.
"""
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.models.config import AppConfig
from app.models.failure import FailureCategory
from app.models.llm import ModelMetadata
from app.models.sample import ValidationResult
from app.models.spec import GenerationSpec


@dataclass
class StageContext:
    spec: GenerationSpec
    run_id: str
    sample_id: str
    config: AppConfig
    generated_text: str | None = None
    raw_llm_output: str | None = None       # generation LLM raw response
    raw_validator_output: str | None = None  # validation LLM raw response
    schema_result: ValidationResult | None = None
    semantic_result: ValidationResult | None = None
    model_metadata: ModelMetadata | None = None
    failure_category: FailureCategory | None = None
    failure_details: str = ""
    raw_error: str | None = None  # sanitized full error context for the Failure record
    attempt: int = 0


@dataclass
class StageResult:
    status: Literal["continue", "stop_valid", "stop_failed", "retry"]
    failure_category: FailureCategory | None = None
    failure_details: str = ""


class PipelineStage(Protocol):
    async def run(self, ctx: StageContext) -> StageResult: ...


class GenerationStage:
    """Calls TextGenerator. Sets ctx.generated_text and ctx.model_metadata."""

    def __init__(self, text_generator):
        self._gen = text_generator

    async def run(self, ctx: StageContext) -> StageResult:
        from app.core.exceptions import LLMCallError

        try:
            text, raw, metadata = await self._gen.generate(
                ctx.spec, ctx.run_id, ctx.sample_id
            )
        except LLMCallError as e:
            # Combine message + detail for an actionable failure record
            details = e.message
            if e.detail:
                details = f"{e.message} | {e.detail[:400]}"
            ctx.raw_error = details
            return StageResult(
                status="stop_failed",
                failure_category=FailureCategory.llm_error,
                failure_details=details,
            )
        except Exception as e:
            details = f"{type(e).__name__}: {e}"[:500]
            ctx.raw_error = details
            return StageResult(
                status="stop_failed",
                failure_category=FailureCategory.llm_error,
                failure_details=details,
            )

        ctx.generated_text = text
        ctx.raw_llm_output = raw
        ctx.model_metadata = metadata

        if not text or not text.strip():
            return StageResult(
                status="retry",
                failure_category=FailureCategory.empty_output,
                failure_details="LLM returned empty text",
            )

        return StageResult(status="continue")


class SchemaValidationStage:
    """Runs SchemaValidator on ctx.generated_text."""

    def __init__(self, schema_validator):
        self._validator = schema_validator

    async def run(self, ctx: StageContext) -> StageResult:
        result = self._validator.validate(ctx.spec, ctx.generated_text or "")
        ctx.schema_result = result

        if not result.passed:
            errors = result.errors
            if any("empty" in e.lower() for e in errors):
                cat = FailureCategory.empty_output
            elif any("too short" in e.lower() for e in errors):
                cat = FailureCategory.text_too_short
            elif any("too long" in e.lower() for e in errors):
                cat = FailureCategory.text_too_long
            elif any("json" in e.lower() for e in errors):
                cat = FailureCategory.invalid_json
            elif any("unit" in e.lower() for e in errors):
                cat = FailureCategory.wrong_unit
            else:
                cat = FailureCategory.schema_invalid

            return StageResult(
                status="stop_failed",
                failure_category=cat,
                failure_details="; ".join(errors),
            )

        return StageResult(status="continue")


class SemanticValidationStage:
    """Runs SemanticValidator to re-extract and compare against truth spec."""

    def __init__(self, semantic_validator):
        self._validator = semantic_validator

    async def run(self, ctx: StageContext) -> StageResult:
        result, category, raw_validator_text = await self._validator.validate(
            spec=ctx.spec,
            generated_text=ctx.generated_text or "",
            run_id=ctx.run_id,
            sample_id=ctx.sample_id,
        )
        ctx.semantic_result = result
        ctx.raw_validator_output = raw_validator_text

        if not result.passed:
            return StageResult(
                status="stop_failed",
                failure_category=category or FailureCategory.semantic_mismatch,
                failure_details="; ".join(result.errors),
            )

        return StageResult(status="stop_valid")
