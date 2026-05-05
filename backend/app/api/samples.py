from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.exceptions import NotFoundError
from app.models.failure import Failure, FailureCategory
from app.models.sample import Sample, SampleStatus, SampleUpdate

router = APIRouter(prefix="/runs/{run_id}", tags=["samples"])
global_router = APIRouter(tags=["samples"])


def _rs(request: Request):
    return request.app.state.run_store


def _ss(request: Request):
    return request.app.state.sample_store


_HINT_MAP = {
    "missing_unit": "Generation prompt is dropping unit tokens. Tighten the prompt with an explicit unit requirement.",
    "schema_invalid": "Lower temperature or enable JSON-mode for the generation model.",
    "semantic_mismatch": "Validator may be too lenient — try a stronger validation model.",
    "extra_measurement_added": "Switch to a stricter single-measurement prompt.",
    "wrong_value": "Generation model is rounding aggressively. Try a higher-fidelity model.",
    "duplicate_value": "Increase diversity in profile settings.",
    "invalid_json": "Enable strict JSON output or add a repair pass.",
    "timeout": "Raise per-task timeout or reduce max_tokens.",
    "llm_error": "Check API key / rate limits in API Status.",
    "rejected": "Inspect representative samples for a pattern.",
    "wrong_measurement_phrase": "Verify prompt instructs the correct phrase format.",
    "unknown": "Inspect representative samples for a pattern.",
}

_BACKEND_TO_FRONTEND_CAT = {
    "schema_invalid": "schema_invalid",
    "semantic_mismatch": "semantic_mismatch",
    "wrong_value": "wrong_value",
    "wrong_unit": "missing_unit",
    "wrong_measurement_phrase": "wrong_measurement_phrase",
    "missing_unit": "missing_unit",
    "missing_value": "wrong_value",
    "extra_measurement": "extra_measurement_added",
    "invalid_json": "invalid_json",
    "rejected": "rejected",
    "llm_error": "llm_error",
    "text_too_short": "schema_invalid",
    "text_too_long": "schema_invalid",
    "empty_output": "llm_error",
}


def _sample_to_ui(sample: Sample) -> dict:
    """Convert backend Sample to the camelCase shape expected by the frontend."""
    spec = sample.spec
    meta = sample.model_metadata

    status = "valid" if sample.status.value == "valid" else "invalid"

    failure_category = None
    if status == "invalid":
        sv = sample.schema_validation
        sem = sample.semantic_validation
        if not sv.passed:
            if sv.errors:
                err = sv.errors[0].lower()
                if "unit" in err:
                    failure_category = "missing_unit"
                elif "json" in err:
                    failure_category = "invalid_json"
                else:
                    failure_category = "schema_invalid"
            else:
                failure_category = "schema_invalid"
        elif sem and not sem.passed:
            failure_category = "semantic_mismatch"
        else:
            failure_category = "unknown"

    value = ""
    if spec.value_nominal is not None:
        value = str(spec.value_nominal)
    elif spec.value_min is not None:
        value = str(spec.value_min)
    elif spec.value_max is not None:
        value = str(spec.value_max)

    sem_out = sample.semantic_validation
    if not sample.schema_validation.passed and sample.schema_validation.errors:
        validator_notes = "; ".join(sample.schema_validation.errors[:2])
    elif sem_out and not sem_out.passed and sem_out.errors:
        validator_notes = "; ".join(sem_out.errors[:2])
    else:
        validator_notes = "ok"

    # Field-level comparisons from semantic validation
    field_comparisons: list[dict] = []
    raw_extraction: dict | None = None
    if sem_out and sem_out.extracted:
        field_comparisons = sem_out.extracted.get("field_comparisons", [])
        raw_extraction = sem_out.extracted.get("raw_extraction")

    return {
        "id": sample.sample_id,
        "runId": sample.run_id,
        "status": status,
        "failureCategory": failure_category,
        "generatedText": sample.generated_text,
        "expectedTruth": {
            "measurementPhrase": spec.measurement_phrase,
            "valueKind": spec.value_kind.value,
            "value": value,
            "unit": spec.unit_norm,
        },
        "validatorOutput": {
            "schemaValid": sample.schema_validation.passed,
            "semanticMatch": sem_out.passed if sem_out else False,
            "notes": validator_notes,
            "fieldComparisons": field_comparisons,
            "rawExtraction": raw_extraction,
        },
        "rawGenerationOutput": sample.raw_llm_output,
        "rawValidatorOutput": sample.raw_validator_output,
        # Keep legacy key for any clients that read it
        "rawModelOutput": sample.raw_llm_output,
        "model": meta.model_name or meta.model_ref,
        "promptVersion": meta.prompt_ref,
        "timestamp": sample.created_at.isoformat(),
        "reviewed": "reviewed" in sample.review_tags,
        "tags": sample.review_tags,
        "excludeFromExport": not sample.include_in_export,
        "notes": sample.notes or None,
    }


# ---------------------------------------------------------------------------
# Global endpoints — no run_id in path
# ---------------------------------------------------------------------------

@global_router.get("/samples")
async def list_all_samples(
    request: Request,
    run_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
) -> list[dict]:
    rs = _rs(request)
    ss = _ss(request)
    runs = rs.load_all_runs()
    if run_id:
        runs = [r for r in runs if r.run_id == run_id]

    result: list[dict] = []
    for run in runs:
        status_enum = None
        if status:
            backend_status = "failed" if status == "invalid" else status
            try:
                status_enum = SampleStatus(backend_status)
            except ValueError:
                pass
        samples, _ = ss.load_samples(
            run_id=run.run_id,
            status=status_enum,
            limit=limit,
            offset=0,
        )
        result.extend(_sample_to_ui(s) for s in samples)
        if len(result) >= limit:
            break

    return result[:limit]


@global_router.get("/failures")
async def list_all_failures(
    request: Request,
    run_id: str | None = None,
) -> list[dict]:
    """Return FailureBucket[] aggregated across all runs."""
    rs = _rs(request)
    ss = _ss(request)
    runs = rs.load_all_runs()
    if run_id:
        runs = [r for r in runs if r.run_id == run_id]

    # key: frontend category, value: aggregated bucket data
    buckets: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "affectedModels": set(),
        "affectedPrompts": set(),
        "exampleSampleIds": [],
    })

    for run in runs:
        rc = run.run_config
        failures_list, _ = ss.load_failures(run_id=run.run_id, limit=500)
        for f in failures_list:
            fe_cat = _BACKEND_TO_FRONTEND_CAT.get(f.failure_category.value, "unknown")
            buckets[fe_cat]["count"] += 1
            buckets[fe_cat]["affectedModels"].add(rc.generation_model_ref)
            buckets[fe_cat]["affectedPrompts"].add(rc.generation_prompt_ref)
            if len(buckets[fe_cat]["exampleSampleIds"]) < 3 and f.sample_id:
                buckets[fe_cat]["exampleSampleIds"].append(f.sample_id)

    result = [
        {
            "category": cat,
            "count": data["count"],
            "trend": [0] * 12,
            "affectedModels": list(data["affectedModels"]),
            "affectedPrompts": list(data["affectedPrompts"]),
            "exampleSampleIds": data["exampleSampleIds"],
            "hint": _HINT_MAP.get(cat, "Inspect representative samples for a pattern."),
        }
        for cat, data in buckets.items()
    ]
    result.sort(key=lambda b: b["count"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Per-run endpoints
# ---------------------------------------------------------------------------

@router.get("/samples")
async def list_samples(
    run_id: str,
    request: Request,
    status: str | None = None,
    measurement_phrase: str | None = None,
    value_kind: str | None = None,
    model_ref: str | None = None,
    prompt_ref: str | None = None,
    include_in_export: bool | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> dict:
    rs = _rs(request)
    try:
        rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    ss = _ss(request)
    status_enum = None
    if status:
        backend_status = "failed" if status == "invalid" else status
        try:
            status_enum = SampleStatus(backend_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    samples, total = ss.load_samples(
        run_id=run_id,
        status=status_enum,
        measurement_phrase=measurement_phrase,
        value_kind=value_kind,
        model_ref=model_ref,
        prompt_ref=prompt_ref,
        include_in_export=include_in_export,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "samples": [_sample_to_ui(s) for s in samples],
    }


@router.get("/samples/{sample_id}")
async def get_sample(run_id: str, sample_id: str, request: Request) -> dict:
    ss = _ss(request)
    try:
        sample = ss.load_sample(run_id, sample_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return _sample_to_ui(sample)


@router.patch("/samples/{sample_id}")
async def update_sample(
    run_id: str, sample_id: str, update: SampleUpdate, request: Request
) -> dict:
    ss = _ss(request)
    try:
        updated = ss.update_sample(run_id, sample_id, update)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return _sample_to_ui(updated)


@router.get("/failures")
async def list_failures(
    run_id: str,
    request: Request,
    category: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> dict:
    rs = _rs(request)
    try:
        rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    ss = _ss(request)
    cat_enum = None
    if category:
        try:
            cat_enum = FailureCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    failures, total = ss.load_failures(
        run_id=run_id,
        category=cat_enum,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "failures": [f.model_dump() for f in failures],
    }


@router.get("/failures/{failure_id}")
async def get_failure(run_id: str, failure_id: str, request: Request) -> dict:
    ss = _ss(request)
    try:
        failure = ss.load_failure(run_id, failure_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Failure '{failure_id}' not found")
    return failure.model_dump()
