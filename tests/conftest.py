import os
import sys
from pathlib import Path

import pytest

# Add backend to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.config import AppConfig
from app.services.mock_llm import MockLLMService
from app.storage.config_store import ConfigStore
from app.storage.export_store import ExportStore
from app.storage.paths import ensure_storage_dirs
from app.storage.run_store import RunStore
from app.storage.sample_store import SampleStore


FIXTURES_DIR = Path(__file__).parent.parent / "backend" / "tests" / "fixtures"


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    ensure_storage_dirs(tmp_path)
    # Copy test config
    test_config = FIXTURES_DIR / "test_config.yaml"
    import shutil
    shutil.copy(test_config, tmp_path / "configs" / "dataset_config.yaml")
    return tmp_path


@pytest.fixture
def config_store(tmp_data_dir: Path) -> ConfigStore:
    cs = ConfigStore(tmp_data_dir)
    cs.load()
    return cs


@pytest.fixture
def test_config(config_store: ConfigStore) -> AppConfig:
    return config_store.get()


@pytest.fixture
def mock_llm() -> MockLLMService:
    return MockLLMService(deterministic=True)


@pytest.fixture
def run_store(tmp_data_dir: Path) -> RunStore:
    return RunStore(tmp_data_dir)


@pytest.fixture
def sample_store(tmp_data_dir: Path) -> SampleStore:
    return SampleStore(tmp_data_dir)


@pytest.fixture
def export_store(tmp_data_dir: Path) -> ExportStore:
    return ExportStore(tmp_data_dir)


@pytest.fixture
def app_client(tmp_data_dir: Path, monkeypatch):
    """Create a TestClient with isolated temp data dir and mock LLM."""
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_data_dir))
    monkeypatch.setenv("TOKENROUTER_API_KEY", "test-key")
    # Clear the lru_cache so settings reload with new env vars
    from app.core.settings import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from main import create_app
    app = create_app()

    # Use as context manager to ensure lifespan runs
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    get_settings.cache_clear()
