import shutil
import time
from pathlib import Path

import yaml

from app.core.exceptions import ConfigError, NotFoundError
from app.models.config import AppConfig
from app.storage.paths import active_config_path, configs_dir


class ConfigStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._config_path = active_config_path(data_dir)
        self._cached: AppConfig | None = None
        self._raw_yaml: str = ""

    def load(self) -> AppConfig:
        if not self._config_path.exists():
            raise ConfigError(
                message="Config file not found",
                detail=f"Expected config at {self._config_path}",
            )
        raw = self._config_path.read_text(encoding="utf-8")
        config = self._parse_and_validate(raw)
        self._cached = config
        self._raw_yaml = raw
        return config

    def get(self) -> AppConfig:
        if self._cached is None:
            return self.load()
        return self._cached

    def get_raw(self) -> str:
        if not self._raw_yaml:
            self.load()
        return self._raw_yaml

    def is_loaded(self) -> bool:
        return self._cached is not None

    def validate_raw(self, raw: str) -> AppConfig:
        return self._parse_and_validate(raw)

    def save(self, raw: str) -> AppConfig:
        validated = self._parse_and_validate(raw)
        self._backup()
        tmp = self._config_path.with_suffix(".yaml.tmp")
        tmp.write_text(raw, encoding="utf-8")
        tmp.replace(self._config_path)
        self._cached = validated
        self._raw_yaml = raw
        return validated

    def snapshot_to_run(self, run_id: str, run_dir: Path) -> Path:
        snapshot_path = run_dir / "config_snapshot.yaml"
        raw = self.get_raw()
        snapshot_path.write_text(raw, encoding="utf-8")
        return snapshot_path

    def list_backups(self) -> list[Path]:
        cfg_dir = configs_dir(self._data_dir)
        backups = sorted(cfg_dir.glob("dataset_config.yaml.bak.*"))
        return backups

    def _parse_and_validate(self, raw: str) -> AppConfig:
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ConfigError(message="Invalid YAML syntax", detail=str(e))
        if not isinstance(data, dict):
            raise ConfigError(message="Config must be a YAML mapping")
        try:
            return AppConfig(**data)
        except Exception as e:
            raise ConfigError(message="Config validation failed", detail=str(e))

    def _backup(self) -> None:
        if not self._config_path.exists():
            return
        ts = int(time.time())
        backup_path = self._config_path.parent / f"dataset_config.yaml.bak.{ts}"
        shutil.copy2(self._config_path, backup_path)
        # Keep only the 5 most recent backups
        backups = self.list_backups()
        for old in backups[:-5]:
            old.unlink(missing_ok=True)
