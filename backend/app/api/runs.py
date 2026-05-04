import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from app.core.exceptions import NotFoundError, RunStateError
from app.models.run import Run, RunAppend, RunConfig, RunCreate, RunStatus
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


@router.post("", status_code=201)
async def create_run(body: RunCreate, request: Request) -> dict:
    rs = _run_store(request)
    cs = _config_store(request)
    config = cs.get()

    # Resolve model/prompt/profile refs from body or config defaults
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
    )

    rs.save_run(run)

    # Snapshot config into run folder
    rdir = rs.get_run_dir(run_id)
    cs.snapshot_to_run(run_id, rdir)

    return run.model_dump()


@router.get("")
async def list_runs(request: Request, status: str | None = None) -> list[dict]:
    rs = _run_store(request)
    runs = rs.load_all_runs()
    if status:
        try:
            target_status = RunStatus(status)
            runs = [r for r in runs if r.status == target_status]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    # Most recent first
    runs.sort(key=lambda r: r.created_at, reverse=True)
    return [r.model_dump() for r in runs]


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> dict:
    rs = _run_store(request)
    try:
        run = rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    result = run.model_dump()
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

    signalled = task_registry.signal_pause(run_id)
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

    # Clear pause event and create fresh cancel if needed
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
        # Not running (was paused), update status directly
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

    # Start the runner
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
    rs = _run_store(request)
    try:
        rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    tracker = request.app.state.metrics_tracker
    metrics = tracker.compute_run_metrics(run_id)
    return metrics.model_dump()


@router.get("/{run_id}/events")
async def get_run_events(
    run_id: str, request: Request, limit: int = 100
) -> list[dict]:
    rs = _run_store(request)
    try:
        rs.load_run(run_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    events = rs.load_events(run_id, limit=limit)
    return [e.model_dump() for e in events]
