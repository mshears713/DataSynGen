import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from app.core.exceptions import NotFoundError
from app.models.run import Run, RunAppend, RunConfig, RunConstraints, RunCreate, RunStatus
from app.pipeline.task_registry import task_registry

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_store(request: Request):
    return request.app.state.run_store


def _sample_store(request: Request):
    return request.app.state.sample_store


def _config_store(request: Request):
    return request.app.state.config_store


def _pipeline_runner(request: Request):
    return request.app.state.pipeline_runner


def _to_ui_run(run: Run) -> dict:
    """Convert backend Run to the camelCase shape expected by the frontend."""
    rc = run.run_config
    status_map = {
        RunStatus.created: "queued",
        RunStatus.running: "running",
        RunStatus.paused: "paused",
        RunStatus.completed: "completed",
        RunStatus.failed: "failed",
        RunStatus.cancelled: "failed",
    }
    prompts = list(dict.fromkeys(filter(None, [
        rc.generation_prompt_ref,
        rc.validation_prompt_ref,
    ])))
    return {
        "id": run.run_id,
        "status": status_map.get(run.status, run.status.value),
        "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
        "targetCount": run.target_count,
        "attempted": run.samples_attempted,
        "valid": run.samples_valid,
        "failed": run.samples_failed,
        "generationModel": rc.generation_model_ref,
        "validationModel": rc.validation_model_ref,
        "prompts": prompts,
        "estCostUsd": run.cost_usd_total,
        "configSnapshot": f"cfg_{run.run_id[-6:]}",
        "profile": rc.generation_profile_ref,
        "currentStage": None,
        "name": run.name,
        "notes": run.notes,
        "seed": run.seed,
        "constraints": run.constraints.model_dump() if run.constraints else None,
    }


def _validate_constraints(constraints: RunConstraints, config) -> None:
    """Raise HTTPException 422 if any constraint values are not in the active config."""
    if constraints.units:
        allowed = set(config.units.allowed)
        invalid = [u for u in constraints.units if u not in allowed]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid constraint units {invalid}. Allowed by config: {config.units.allowed}",
            )

    if constraints.measurement_phrases:
        allowed = set(config.measurement_phrases)
        invalid = [p for p in constraints.measurement_phrases if p not in allowed]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid constraint measurement_phrases {invalid}. "
                    f"Allowed by config: {config.measurement_phrases}"
                ),
            )

    if constraints.value_kinds:
        allowed = set(config.value_kinds.allowed)
        invalid = [k for k in constraints.value_kinds if k not in allowed]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid constraint value_kinds {invalid}. Allowed by config: {config.value_kinds.allowed}",
            )


@router.post("", status_code=201)
async def create_run(body: RunCreate, request: Request) -> dict:
    rs = _run_store(request)
    cs = _config_store(request)
    config = cs.get()

    # Validate constraints against active config
    if body.constraints:
        _validate_constraints(body.constraints, config)

    gen_task = config.tasks.get("generation")
    val_task = config.tasks.get("validation")

    run_config = RunConfig(
        generation_model_ref=body.generation_model_ref or (gen_task.model_ref if gen_task else ""),
        validation_model_ref=body.validation_model_ref or (val_task.model_ref if val_task else ""),
        generation_prompt_ref=body.generation_prompt_ref or (gen_task.prompt_ref if gen_task else ""),
        validation_prompt_ref=body.validation_prompt_ref or (val_task.prompt_ref if val_task else ""),
        generation_profile_ref=body.generation_profile_ref or (gen_task.profile_ref if gen_task else ""),
        validation_profile_ref=body.validation_profile_ref or (val_task.profile_ref if val_task else ""),
    )

    run_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:6]}"
    run = Run(
        run_id=run_id,
        name=body.name,
        run_config=run_config,
        target_count=body.target_count,
        notes=body.notes,
        seed=body.seed,
        constraints=body.constraints,
    )

    rs.save_run(run)
    rdir = rs.get_run_dir(run_id)
    cs.snapshot_to_run(run_id, rdir)

    return _to_ui_run(run)


@router.get("")
async def list_runs(request: Request, status: str | None = None) -> list[dict]:
    rs = _run_store(request)
    runs = rs.load_all_runs()
    if status:
        frontend_to_backend = {
            "queued": ["created"],
            "running": ["running"],
            "paused": ["paused"],
            "completed": ["completed"],
            "failed": ["failed", "cancelled"],
        }
        backend_statuses = frontend_to_backend.get(status, [status])
        runs = [r for r in runs if r.status.value in backend_statuses]
    runs.sort(key=lambda r: r.created_at, reverse=True)
    return [_to_ui_run(r) for r in runs]


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    result = _to_ui_run(run)
    result["is_running"] = task_registry.is_running(run_id)
    return result


@router.post("/{run_id}/start")
async def start_run(run_id: str, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run.status not in (RunStatus.created, RunStatus.paused):
        raise HTTPException(
            status_code=409,
            detail=f"Run is in state '{run.status}' and cannot be started",
        )

    if task_registry.is_running(run_id):
        raise HTTPException(status_code=409, detail="Run is already executing")

    pause_event, cancel_event = task_registry.create_events(run_id)
    runner = _pipeline_runner(request)

    run.status = RunStatus.running
    run.updated_at = datetime.utcnow()
    rs.save_run(run)

    task = asyncio.create_task(
        runner.execute_run(run, pause_event, cancel_event)
    )
    task_registry.register(run_id, task, pause_event, cancel_event)

    return {"run_id": run_id, "status": "running", "message": "Pipeline started"}


@router.post("/{run_id}/pause")
async def pause_run(run_id: str, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run.status != RunStatus.running:
        raise HTTPException(
            status_code=409,
            detail=f"Run is in state '{run.status}' and cannot be paused",
        )

    task_registry.signal_pause(run_id)
    return {
        "run_id": run_id,
        "status": "pause_requested",
        "message": "Pause signal sent. Run will pause after the current sample completes.",
    }


@router.post("/{run_id}/resume")
async def resume_run(run_id: str, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run.status != RunStatus.paused:
        raise HTTPException(
            status_code=409,
            detail=f"Run is in state '{run.status}' and cannot be resumed",
        )

    if task_registry.is_running(run_id):
        raise HTTPException(status_code=409, detail="Run is already executing")

    task_registry.clear_pause(run_id)
    pause_event, cancel_event = task_registry.create_events(run_id)
    runner = _pipeline_runner(request)

    run.status = RunStatus.running
    run.updated_at = datetime.utcnow()
    rs.save_run(run)

    task = asyncio.create_task(
        runner.execute_run(run, pause_event, cancel_event)
    )
    task_registry.register(run_id, task, pause_event, cancel_event)

    return {"run_id": run_id, "status": "running", "message": "Run resumed"}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run.status not in (RunStatus.running, RunStatus.paused):
        raise HTTPException(
            status_code=409,
            detail=f"Run is in state '{run.status}' and cannot be cancelled",
        )

    if task_registry.is_running(run_id):
        task_registry.signal_cancel(run_id)
    else:
        run.status = RunStatus.cancelled
        run.updated_at = datetime.utcnow()
        rs.save_run(run)

    return {"run_id": run_id, "status": "cancel_requested"}


@router.post("/{run_id}/append")
async def append_to_run(run_id: str, body: RunAppend, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run.status not in (RunStatus.completed, RunStatus.paused, RunStatus.cancelled):
        raise HTTPException(
            status_code=409,
            detail=f"Can only append to completed/paused/cancelled runs, got '{run.status}'",
        )

    if task_registry.is_running(run_id):
        raise HTTPException(status_code=409, detail="Run is still executing")

    run.target_count += body.additional_count
    run.status = RunStatus.paused
    run.updated_at = datetime.utcnow()
    rs.save_run(run)

    pause_event, cancel_event = task_registry.create_events(run_id)
    runner = _pipeline_runner(request)
    run.status = RunStatus.running
    rs.save_run(run)

    task = asyncio.create_task(
        runner.execute_run(run, pause_event, cancel_event)
    )
    task_registry.register(run_id, task, pause_event, cancel_event)

    return {
        "run_id": run_id,
        "new_target": run.target_count,
        "status": "running",
        "message": f"Appended {body.additional_count} samples and resumed",
    }


@router.get("/{run_id}/metrics")
async def get_run_metrics(run_id: str, request: Request) -> dict:
    from datetime import datetime as _dt
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    tracker = request.app.state.metrics_tracker
    sample_store = _sample_store(request)
    m = tracker.compute_run_metrics(run_id)
    rc = run.run_config

    recent_failures = []
    for sample in sample_store.stream_all_samples(run_id):
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

    failure_rate = m.samples_failed / m.samples_attempted if m.samples_attempted else 0.0
    return {
        "runId": run_id,
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
        "lastUpdate": _dt.utcnow().isoformat(),
        "recentFailures": recent_failures,
    }


@router.get("/{run_id}/events")
async def get_run_events(
    run_id: str, request: Request, limit: int = 200
) -> list[dict]:
    rs = _run_store(request)
    try:
        rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    events = rs.load_events(run_id, limit=limit)
    return [e.model_dump() for e in events]
