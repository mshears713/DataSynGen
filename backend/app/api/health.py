from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    config_store = request.app.state.config_store
    config_loaded = config_store.is_loaded()

    tokenrouter_configured = bool(
        settings.tokenrouter_api_key and settings.tokenrouter_api_key != "mock-key"
    ) or settings.mock_llm

    storage_writable = _check_storage_writable(settings.data_dir)
    ts = datetime.utcnow().isoformat()

    return {
        # Fields expected by the frontend ping()
        "ok": True,
        "ts": ts,
        # Additional diagnostic fields
        "status": "ok",
        "config_loaded": config_loaded,
        "tokenrouter_configured": tokenrouter_configured,
        "storage_writable": storage_writable,
        "mock_llm": settings.mock_llm,
        "timestamp": ts,
    }


def _check_storage_writable(data_dir: Path) -> bool:
    try:
        test_file = data_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except Exception:
        return False
