from collections import defaultdict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("")
async def list_benchmarks(request: Request) -> list[dict]:
    """Return BenchmarkRow[] aggregated by generation_model_ref x generation_prompt_ref."""
    run_store = request.app.state.run_store
    tracker = request.app.state.metrics_tracker

    runs = run_store.load_all_runs()
    if not runs:
        return []

    # Group runs by (model_ref, prompt_ref)
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for run in runs:
        key = (run.run_config.generation_model_ref, run.run_config.generation_prompt_ref)
        groups[key].append(run)

    rows = []
    for idx, ((model_ref, prompt_ref), group_runs) in enumerate(groups.items()):
        total_attempted = 0
        total_valid = 0
        total_schema_valid = 0
        total_semantic = 0
        total_cost = 0.0
        total_latency = 0.0
        latency_count = 0

        for run in group_runs:
            m = tracker.compute_run_metrics(run.run_id)
            total_attempted += m.samples_attempted
            total_valid += m.samples_valid
            total_cost += m.cost_usd_total
            if m.samples_attempted > 0:
                total_schema_valid += round(m.schema_valid_rate * m.samples_attempted)
                total_semantic += round(m.semantic_match_rate * m.samples_attempted)
            if m.avg_latency_ms is not None:
                total_latency += m.avg_latency_ms
                latency_count += 1

        valid_pct = round((total_valid / total_attempted * 100) if total_attempted else 0)
        schema_pct = round((total_schema_valid / total_attempted * 100) if total_attempted else 0)
        semantic_pct = round((total_semantic / total_attempted * 100) if total_attempted else 0)
        failure_pct = 100 - valid_pct
        cost_per_valid = (total_cost / total_valid) if total_valid else 0.0
        avg_latency = round(total_latency / latency_count) if latency_count else 0

        rows.append({
            "id": f"bm_{idx}",
            "model": model_ref,
            "prompt": prompt_ref,
            "runCount": len(group_runs),
            "samples": total_attempted,
            "validPct": valid_pct,
            "schemaValidPct": schema_pct,
            "semanticMatchPct": semantic_pct,
            "failurePct": failure_pct,
            "costPerValidUsd": round(cost_per_valid, 6),
            "totalCostUsd": round(total_cost, 4),
            "throughput": 0,
            "avgLatencyMs": avg_latency,
            "notes": "",
        })

    rows.sort(key=lambda r: r["validPct"], reverse=True)
    return rows
