from fastapi import APIRouter, HTTPException, Query, Request

from app.core.exceptions import NotFoundError
from app.models.failure import FailureCategory
from app.models.sample import SampleStatus, SampleUpdate

router = APIRouter(prefix="/runs/{run_id}", tags=["samples"])


def _rs(request: Request):
    return request.app.state.run_store


def _ss(request: Request):
    return request.app.state.sample_store


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
        try:
            status_enum = SampleStatus(status)
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
        "samples": [s.model_dump() for s in samples],
    }


@router.get("/samples/{sample_id}")
async def get_sample(run_id: str, sample_id: str, request: Request) -> dict:
    ss = _ss(request)
    try:
        sample = ss.load_sample(run_id, sample_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return sample.model_dump()


@router.patch("/samples/{sample_id}")
async def update_sample(
    run_id: str, sample_id: str, update: SampleUpdate, request: Request
) -> dict:
    ss = _ss(request)
    try:
        updated = ss.update_sample(run_id, sample_id, update)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return updated.model_dump()


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
