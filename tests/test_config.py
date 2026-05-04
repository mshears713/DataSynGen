"""Tests for config loading, validation, and persistence."""
import shutil
from pathlib import Path

import pytest
import yaml

from app.core.exceptions import ConfigError
from app.models.config import AppConfig
from app.storage.config_store import ConfigStore
from app.storage.paths import ensure_storage_dirs


def test_valid_config_loads(config_store: ConfigStore, test_config: AppConfig):
    assert test_config is not None
    assert test_config.project.name == "test_dataset"
    assert "outer diameter" in test_config.measurement_phrases
    assert "mm" in test_config.units.allowed
    assert "exact" in test_config.value_kinds.allowed


def test_config_has_models(test_config: AppConfig):
    assert "fast_model" in test_config.models
    assert test_config.models["fast_model"].model == "mock/fast"
    assert test_config.models["fast_model"].enabled is True


def test_config_has_prompts(test_config: AppConfig):
    assert "gen_prompt_v1" in test_config.prompts
    assert test_config.prompts["gen_prompt_v1"].task == "generation"
    assert test_config.prompts["gen_prompt_v1"].active is True


def test_config_has_valid_task_routing(test_config: AppConfig):
    assert "generation" in test_config.tasks
    gen = test_config.tasks["generation"]
    assert gen.model_ref in test_config.models
    assert gen.prompt_ref in test_config.prompts
    assert gen.profile_ref in test_config.profiles


def test_invalid_yaml_rejected(tmp_data_dir: Path, config_store: ConfigStore):
    with pytest.raises(ConfigError, match="Invalid YAML"):
        config_store.validate_raw("{ invalid: yaml: :")


def test_missing_required_field_rejected(tmp_data_dir: Path, config_store: ConfigStore):
    raw = """
project:
  name: test
"""
    with pytest.raises(ConfigError, match="validation failed"):
        config_store.validate_raw(raw)


def test_invalid_task_ref_rejected(tmp_data_dir: Path, config_store: ConfigStore):
    raw = config_store.get_raw()
    data = yaml.safe_load(raw)
    data["tasks"]["generation"]["model_ref"] = "nonexistent_model"
    bad_raw = yaml.dump(data)
    with pytest.raises(ConfigError):
        config_store.validate_raw(bad_raw)


def test_config_backup_created_on_save(tmp_data_dir: Path, config_store: ConfigStore):
    initial_backups = len(config_store.list_backups())
    raw = config_store.get_raw()
    config_store.save(raw)
    assert len(config_store.list_backups()) == initial_backups + 1


def test_config_backup_limit(tmp_data_dir: Path, config_store: ConfigStore):
    raw = config_store.get_raw()
    for _ in range(7):
        config_store.save(raw)
    assert len(config_store.list_backups()) <= 5


def test_config_snapshot_to_run(tmp_data_dir: Path, config_store: ConfigStore):
    run_dir = tmp_data_dir / "runs" / "test_run"
    run_dir.mkdir(parents=True)
    snapshot_path = config_store.snapshot_to_run("test_run", run_dir)
    assert snapshot_path.exists()
    content = snapshot_path.read_text()
    assert "measurement_extraction" in content


def test_config_is_loaded_flag(tmp_data_dir: Path):
    fresh_cs = ConfigStore(tmp_data_dir)
    assert not fresh_cs.is_loaded()
    fresh_cs.load()
    assert fresh_cs.is_loaded()


def test_config_validate_raw_does_not_save(tmp_data_dir: Path, config_store: ConfigStore):
    raw = config_store.get_raw()
    data = yaml.safe_load(raw)
    data["project"]["name"] = "changed_name"
    new_raw = yaml.dump(data)
    config_store.validate_raw(new_raw)
    # Original config should be unchanged
    assert config_store.get().project.name == "test_dataset"
