from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.exceptions import ConfigError
from app.models.config import AppConfig

router = APIRouter(prefix="/config", tags=["config"])


def _get_config_store(request: Request):
    return request.app.state.config_store


def _cost_tier(model_id: str) -> str:
    low = ["flash", "mini", "haiku", "lite", "nano"]
    high = ["opus", "pro", "ultra", "large", "plus"]
    ml = model_id.lower()
    if any(k in ml for k in low):
        return "low"
    if any(k in ml for k in high):
        return "high"
    return "medium"


def _infer_tasks_for_model(ref: str, config: AppConfig) -> list[str]:
    tasks = []
    for task_name, route in config.tasks.items():
        if route.model_ref == ref:
            tasks.append(task_name)
    return tasks if tasks else ["generation"]


def _strictness_from_temperature(temp: float) -> str:
    if temp <= 0.2:
        return "high"
    if temp <= 0.7:
        return "medium"
    return "low"


def _diversity_from_temperature(temp: float) -> str:
    if temp <= 0.2:
        return "low"
    if temp <= 0.7:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Full config
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Models — returns ModelDef shape expected by the frontend
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {
            "id": ref,
            "displayName": m.model.split("/")[-1].replace("-", " ").title() if "/" in m.model else ref,
            "modelId": m.model,
            "provider": m.provider,
            "notes": m.notes,
            "enabled": m.enabled,
            "tasks": _infer_tasks_for_model(ref, config),
            "costTier": _cost_tier(m.model),
            "lastUsed": None,
        }
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


# ---------------------------------------------------------------------------
# Prompts — returns PromptDef shape expected by the frontend
# ---------------------------------------------------------------------------

@router.get("/prompts")
async def list_prompts(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {
            "id": ref,
            "ref": ref,
            "title": p.title,
            "version": str(p.version),
            "task": p.task,
            "active": p.active,
            "notes": p.notes,
            "lastUsed": None,
            "body": p.template,
            "successRate": None,
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
    return {
        "id": ref,
        "ref": ref,
        "title": p.title,
        "version": str(p.version),
        "task": p.task,
        "active": p.active,
        "notes": p.notes,
        "lastUsed": None,
        "body": p.template,
        "successRate": None,
    }


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
    base_ref = ref.rstrip("0123456789").rstrip("_v")
    new_ref = f"{base_ref}_v{new_version}"
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


# ---------------------------------------------------------------------------
# Profiles — returns TaskProfile shape expected by the frontend
# Endpoint: /config/profiles  (alias for task-profiles)
# ---------------------------------------------------------------------------

@router.get("/profiles")
async def list_profiles(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {
            "id": ref,
            "name": ref,
            "temperature": p.temperature,
            "maxTokens": p.max_tokens,
            "retryCount": p.retry_count,
            "timeoutMs": p.timeout * 1000,
            "strictness": _strictness_from_temperature(p.temperature),
            "diversity": _diversity_from_temperature(p.temperature),
            "notes": "",
        }
        for ref, p in config.profiles.items()
    ]


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


# ---------------------------------------------------------------------------
# Task routing
# ---------------------------------------------------------------------------

@router.get("/task-routing")
async def list_task_routing(request: Request) -> list[dict]:
    cs = _get_config_store(request)
    config = cs.get()
    return [
        {"task": task, **route.model_dump()}
        for task, route in config.tasks.items()
    ]


@router.get("/domain")
async def get_domain_config(request: Request) -> dict:
    cs = _get_config_store(request)
    config = cs.get()
    return {
        "measurement_phrases": config.measurement_phrases,
        "units": config.units.allowed,
        "value_kinds": config.value_kinds.allowed,
    }


@router.patch("/domain")
async def update_domain_config(request: Request) -> dict:
    cs = _get_config_store(request)
    import yaml
    body = await request.json()
    raw = cs.get_raw()
    data = yaml.safe_load(raw)

    updated = False
    if "measurement_phrases" in body:
        phrases = body["measurement_phrases"]
        if not isinstance(phrases, list) or len(phrases) == 0:
            raise HTTPException(status_code=422, detail="measurement_phrases must be a non-empty list")
        data["measurement_phrases"] = phrases
        updated = True
    if "units" in body:
        units = body["units"]
        if not isinstance(units, list) or len(units) == 0:
            raise HTTPException(status_code=422, detail="units must be a non-empty list")
        if "units" not in data or not isinstance(data["units"], dict):
            data["units"] = {}
        data["units"]["allowed"] = units
        updated = True
    if "value_kinds" in body:
        vk = body["value_kinds"]
        if not isinstance(vk, list) or len(vk) == 0:
            raise HTTPException(status_code=422, detail="value_kinds must be a non-empty list")
        if "value_kinds" not in data or not isinstance(data["value_kinds"], dict):
            data["value_kinds"] = {}
        data["value_kinds"]["allowed"] = vk
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No valid domain fields provided")

    new_raw = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    try:
        config = cs.save(new_raw)
    except ConfigError as e:
        raise HTTPException(status_code=422, detail={"message": e.message, "detail": e.detail})

    return {
        "measurement_phrases": config.measurement_phrases,
        "units": config.units.allowed,
        "value_kinds": config.value_kinds.allowed,
    }


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
