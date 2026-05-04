from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.settings import Settings, get_settings
from app.storage.paths import ensure_storage_dirs

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    config_store = request.app.state.config_store
    config_loaded = config_store.is_loaded()

    if settings.mock_llm:
        llm_configured = True
        llm_provider = "mock"
    elif settings.use_anthropic or settings.anthropic_api_key:
        llm_configured = bool(settings.anthropic_api_key)
        llm_provider = "anthropic"
    else:
        llm_configured = bool(
            settings.tokenrouter_api_key and settings.tokenrouter_api_key != "mock-key"
        )
        llm_provider = "tokenrouter"

    storage_writable = _check_storage_writable(settings.data_dir)

    return {
        "status": "ok",
        "config_loaded": config_loaded,
        "llm_configured": llm_configured,
        "llm_provider": llm_provider,
        # Keep tokenrouter_configured for backwards compat with existing tests
        "tokenrouter_configured": llm_configured,
        "storage_writable": storage_writable,
        "mock_llm": settings.mock_llm,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _check_storage_writable(data_dir: Path) -> bool:
    try:
        test_file = data_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except Exception:
        return False
