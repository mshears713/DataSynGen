import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.spec import GenerationSpec, ValueKind
from app.services.tokenrouter import TokenRouterService
from app.validation.normalizer import (
    approx_equal,
    normalize_number,
    normalize_phrase,
    normalize_unit,
)

router = APIRouter(prefix="/debug", tags=["debug"])


class DebugTruth(BaseModel):
    measurement_phrase: str
    value_kind: str
    value_nominal: Optional[float] = None
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    value_tolerance: Optional[float] = None
    unit_norm: str


class DebugValidateRequest(BaseModel):
    generated_text: str
    expected_truth: DebugTruth


@router.post("/validate-sample")
async def debug_validate_sample(body: DebugValidateRequest, request: Request) -> dict:
    """
    Run full semantic validation on an ad-hoc generated_text + expected_truth pair.
    Returns the parsed extraction, field-level comparisons, and pass/fail result.
    Useful for diagnosing false-failures without running a full pipeline.
    """
    settings = request.app.state.settings
    if settings.mock_llm:
        return {
            "note": "MOCK_LLM=true — returning mock result, no real validator call made",
            "schema_valid": True,
            "semantic_match": True,
            "parsed": {},
            "field_comparisons": [],
            "raw_validator_output": "(mock)",
            "notes": "Mock mode active",
        }

    config = request.app.state.config_store.get()
    semantic_validator = request.app.state.semantic_validator

    truth = body.expected_truth
    try:
        kind = ValueKind(truth.value_kind)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown value_kind '{truth.value_kind}'")

    # Build a minimal GenerationSpec
    import uuid
    spec = GenerationSpec(
        spec_id=str(uuid.uuid4()),
        measurement_phrase=truth.measurement_phrase,
        value_kind=kind,
        value_nominal=truth.value_nominal,
        value_min=truth.value_min,
        value_max=truth.value_max,
        value_tolerance=truth.value_tolerance,
        unit_norm=truth.unit_norm,
    )

    result, category, raw_validator_text = await semantic_validator.validate(
        spec=spec,
        generated_text=body.generated_text,
        run_id="debug",
        sample_id="debug",
    )

    field_comparisons = []
    raw_extraction = None
    if result.extracted:
        field_comparisons = result.extracted.get("field_comparisons", [])
        raw_extraction = result.extracted.get("raw_extraction")

    notes = "; ".join(result.errors) if result.errors else "ok"

    return {
        "schema_valid": True,
        "semantic_match": result.passed,
        "failure_category": category.value if category else None,
        "parsed": raw_extraction or {},
        "field_comparisons": field_comparisons,
        "raw_validator_output": raw_validator_text,
        "notes": notes,
    }


@router.post("/llm-smoke")
async def llm_smoke(request: Request) -> dict:
    """Fires a minimal LLM call through the live TokenRouterService and returns sanitized diagnostics."""
    settings = request.app.state.settings
    llm_service = request.app.state.llm_service

    base_url: str = settings.tokenrouter_base_url
    mode: str = settings.tokenrouter_api_mode
    mock_llm: bool = settings.mock_llm

    if mock_llm:
        return {
            "success": True,
            "note": "MOCK_LLM=true — no real API call was made",
            "base_url": base_url,
            "mode": mode,
        }

    if not isinstance(llm_service, TokenRouterService):
        return {
            "success": False,
            "error": f"LLM service is {type(llm_service).__name__}, expected TokenRouterService",
        }

    endpoint = llm_service._endpoint
    model = "gpt-4o"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK only."}],
        "max_tokens": 5,
    }
    headers = {
        "Authorization": f"Bearer {llm_service._api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.monotonic()
    exc_class: str | None = None
    exc_msg: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    body_excerpt: str | None = None
    success = False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
        latency_ms = round((time.monotonic() - t0) * 1000)
        status_code = resp.status_code
        content_type = resp.headers.get("content-type", "")
        body_excerpt = resp.text[:500]
        success = 200 <= status_code < 300
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        exc_class = type(exc).__name__
        exc_msg = str(exc)[:300]

    return {
        "success": success,
        "base_url": base_url,
        "mode": mode,
        "endpoint": endpoint,
        "model": model,
        "status_code": status_code,
        "content_type": content_type,
        "body_excerpt": body_excerpt,
        "latency_ms": latency_ms,
        "exception": exc_class,
        "exception_message": exc_msg,
    }
