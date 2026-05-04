from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.exceptions import ConfigError
from app.models.config import AppConfig

router = APIRouter(prefix="/config", tags=["config"])


def _get_config_store(request: Request):
    return request.app.state.config_store


@router.get("", response_model=dict)
async def get_config(request: Request) -> dict:
    cs = _get_config_store(request)
    config = cs.get()
    return config.model_dump()


@router.get("/raw", response_class=PlainTextResponse)
async def get_config_raw(request: Request) -> str:
    cs = _get_config_store(request)
    return cs.get_raw()


@router.put("", response_model=dict)
async def update_config(request: Request) -> dict:
    cs = _get_config_store(request)
    raw = await request.body()
    raw_str = raw.decode("utf-8")
    try:
        config = cs.save(raw_str)
    except ConfigError as e:
        raise HTTPException(status_code=422, detail={"message": e.message, "detail": e.detail})
    return config.model_dump()


@router.post("/validate", response_model=dict)
async def validate_config(request: Request) -> dict:
    cs = _get_config_store(request)
    raw = await request.body()
    raw_str = raw.decode("utf-8")
    try:
        config = cs.validate_raw(raw_str)
        return {"valid": True, "config": config.model_dump()}
    except ConfigError as e:
        return {"valid": False, "error": e.message, "detail": e.detail}


@router.get("/prompts")
async def list_prompts(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {
            "ref": ref,
            "task": p.task,
            "title": p.title,
            "active": p.active,
            "version": p.version,
            "notes": p.notes,
        }
        for ref, p in config.prompts.items()
    ]


@router.get("/prompts/{ref}")
async def get_prompt(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    config = cs.get()
    if ref not in config.prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{ref}' not found")
    p = config.prompts[ref]
    return {"ref": ref, **p.model_dump()}


@router.post("/prompts/{ref}/activate")
async def activate_prompt(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    prompts = data.get("prompts", {})
    if ref not in prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{ref}' not found")

    task = prompts[ref].get("task")
    # Deactivate all prompts for same task, activate target
    for k, v in prompts.items():
        if v.get("task") == task:
            prompts[k]["active"] = k == ref

    data["prompts"] = prompts
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    cs.save(new_raw)
    return {"ref": ref, "active": True}


@router.post("/prompts/{ref}/deactivate")
async def deactivate_prompt(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    prompts = data.get("prompts", {})
    if ref not in prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{ref}' not found")
    prompts[ref]["active"] = False
    data["prompts"] = prompts
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    cs.save(new_raw)
    return {"ref": ref, "active": False}


@router.post("/prompts/{ref}/duplicate")
async def duplicate_prompt(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    prompts = data.get("prompts", {})
    if ref not in prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{ref}' not found")

    source = dict(prompts[ref])
    new_version = source.get("version", 1) + 1
    source["version"] = new_version
    source["active"] = False
    source["title"] = source.get("title", ref) + f" v{new_version}"

    # Generate new ref
    base_ref = ref.rstrip("0123456789").rstrip("_v")
    new_ref = f"{base_ref}_v{new_version}"
    # Ensure unique
    counter = 1
    while new_ref in prompts:
        new_ref = f"{base_ref}_v{new_version}_{counter}"
        counter += 1

    prompts[new_ref] = source
    data["prompts"] = prompts
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    cs.save(new_raw)
    return {"new_ref": new_ref, **source}


@router.patch("/prompts/{ref}")
async def update_prompt(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    body = await request.json()
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    prompts = data.get("prompts", {})
    if ref not in prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{ref}' not found")
    allowed_fields = {"title", "template", "notes", "active"}
    for field, val in body.items():
        if field in allowed_fields:
            prompts[ref][field] = val
    data["prompts"] = prompts
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    cs.save(new_raw)
    return {"ref": ref, **prompts[ref]}


@router.get("/models")
async def list_models(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {"ref": ref, **m.model_dump()}
        for ref, m in config.models.items()
    ]


@router.patch("/models/{ref}")
async def update_model(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    body = await request.json()
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    models = data.get("models", {})
    if ref not in models:
        raise HTTPException(status_code=404, detail=f"Model '{ref}' not found")
    allowed_fields = {"enabled", "notes"}
    for field, val in body.items():
        if field in allowed_fields:
            models[ref][field] = val
    data["models"] = models
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    cs.save(new_raw)
    return {"ref": ref, **models[ref]}


@router.get("/task-profiles")
async def list_task_profiles(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {"ref": ref, **p.model_dump()}
        for ref, p in config.profiles.items()
    ]


@router.patch("/task-profiles/{ref}")
async def update_task_profile(ref: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    body = await request.json()
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    profiles = data.get("profiles", {})
    if ref not in profiles:
        raise HTTPException(status_code=404, detail=f"Profile '{ref}' not found")
    allowed_fields = {"temperature", "max_tokens", "retry_count", "timeout"}
    for field, val in body.items():
        if field in allowed_fields:
            profiles[ref][field] = val
    data["profiles"] = profiles
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    cs.save(new_raw)
    return {"ref": ref, **profiles[ref]}


@router.get("/task-routing")
async def list_task_routing(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {"task": task, **route.model_dump()}
        for task, route in config.tasks.items()
    ]


@router.patch("/task-routing/{task}")
async def update_task_routing(task: str, request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    body = await request.json()
    raw = cs.get_raw()
    data = yaml.safe_load(raw)
    tasks = data.get("tasks", {})
    if task not in tasks:
        raise HTTPException(status_code=404, detail=f"Task '{task}' not found")
    allowed_fields = {"model_ref", "prompt_ref", "profile_ref"}
    for field, val in body.items():
        if field in allowed_fields:
            tasks[task][field] = val
    data["tasks"] = tasks
    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    try:
        cs.save(new_raw)
    except ConfigError as e:
        raise HTTPException(status_code=422, detail={"message": e.message, "detail": e.detail})
    return {"task": task, **tasks[task]}
