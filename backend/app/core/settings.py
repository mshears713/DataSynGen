import json
from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CORS = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

# Always load backend/.env (not cwd-relative), so `uvicorn` works from repo root too.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    tokenrouter_base_url: str = "https://api.tokenrouter.ai/v1"
    tokenrouter_api_key: str = "mock-key"
    # Anthropic-native API support (used when ANTHROPIC_API_KEY is set or USE_ANTHROPIC=true)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    use_anthropic: bool = False
    mock_llm: bool = False
    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    # Comma-separated in .env (list[str] would require JSON, which breaks CORS_ORIGINS=a,b)
    cors_origins: str = _DEFAULT_CORS
    api_host: str = "0.0.0.0"
    api_port: int = 8001

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw:
            return [x.strip() for x in _DEFAULT_CORS.split(",") if x.strip()]
        if raw.startswith("["):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        return [x.strip() for x in raw.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
