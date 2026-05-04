from datetime import datetime

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


@router.get("/live")
async def live_metrics(request: Request) -> dict:
    """Return MetricsSnapshot shape for the most recently active run."""
    run_store = request.app.state.run_store
    tracker = request.app.state.metrics_tracker
    sample_store = request.app.state.sample_store

    runs = run_store.load_all_runs()
    if not runs:
        return _empty_snapshot()

    priority = {"running": 0, "paused": 1, "completed": 2, "failed": 3, "created": 4, "cancelled": 5}
    runs_sorted = sorted(
        runs,
        key=lambda r: (priority.get(r.status.value, 99), -r.updated_at.timestamp()),
    )
    run = runs_sorted[0]
    m = tracker.compute_run_metrics(run.run_id)
    rc = run.run_config

    recent_failures = []
    for sample in sample_store.stream_all_samples(run.run_id):
        if sample.status.value != "valid" and len(recent_failures) < 6:
            sv = sample.schema_validation
            sem = sample.semantic_validation
            if not sv.passed:
                cat = "schema_invalid"
            elif sem and not sem.passed:
                cat = "semantic_mismatch"
            else:
                cat = "unknown"
            recent_failures.append({
                "sampleId": sample.sample_id,
                "category": cat,
                "preview": sample.generated_text[:64],
            })

    failure_rate = (
        m.samples_failed / m.samples_attempted if m.samples_attempted else 0.0
    )

    return {
        "runId": run.run_id,
        "stage": "text_generation",
        "activeModel": rc.validation_model_ref or rc.generation_model_ref,
        "attempted": m.samples_attempted,
        "valid": m.samples_valid,
        "invalid": m.samples_failed,
        "schemaValidRate": m.schema_valid_rate,
        "semanticMatchRate": m.semantic_match_rate,
        "failureRate": failure_rate,
        "throughputPerMin": 0,
        "estCostUsd": m.cost_usd_total,
        "costPerValidUsd": m.cost_per_valid_sample or 0.0,
        "lastUpdate": datetime.utcnow().isoformat(),
        "recentFailures": recent_failures,
    }


def _empty_snapshot() -> dict:
    return {
        "runId": "",
        "stage": "text_generation",
        "activeModel": "",
        "attempted": 0,
        "valid": 0,
        "invalid": 0,
        "schemaValidRate": 0.0,
        "semanticMatchRate": 0.0,
        "failureRate": 0.0,
        "throughputPerMin": 0,
        "estCostUsd": 0.0,
        "costPerValidUsd": 0.0,
        "lastUpdate": datetime.utcnow().isoformat(),
        "recentFailures": [],
    }
