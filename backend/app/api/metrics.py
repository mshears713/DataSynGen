from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
async def metrics_summary(
    request: Request,
    run_ids: list[str] = Query(default=None),
) -> dict:
    tracker = request.app.state.metrics_tracker
    return tracker.compute_cross_run_summary(run_ids=run_ids or None)


@router.get("/benchmark")
async def benchmark(
    request: Request,
    run_ids: list[str] = Query(..., description="Run IDs to compare"),
) -> dict:
    tracker = request.app.state.metrics_tracker
    comparison = tracker.compute_benchmark(run_ids)
    return comparison.model_dump()
