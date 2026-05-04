from pathlib import Path


def runs_dir(data_dir: Path) -> Path:
    return data_dir / "runs"


def run_dir(data_dir: Path, run_id: str) -> Path:
    return runs_dir(data_dir) / run_id


def run_metadata_path(data_dir: Path, run_id: str) -> Path:
    return run_dir(data_dir, run_id) / "metadata.json"


def run_config_snapshot_path(data_dir: Path, run_id: str) -> Path:
    return run_dir(data_dir, run_id) / "config_snapshot.yaml"


def samples_path(data_dir: Path, run_id: str) -> Path:
    return run_dir(data_dir, run_id) / "samples.jsonl"


def failures_path(data_dir: Path, run_id: str) -> Path:
    return run_dir(data_dir, run_id) / "failures.jsonl"


def events_path(data_dir: Path, run_id: str) -> Path:
    return run_dir(data_dir, run_id) / "events.jsonl"


def metrics_path(data_dir: Path, run_id: str) -> Path:
    return run_dir(data_dir, run_id) / "metrics.json"


def configs_dir(data_dir: Path) -> Path:
    return data_dir / "configs"


def active_config_path(data_dir: Path) -> Path:
    return configs_dir(data_dir) / "dataset_config.yaml"


def exports_dir(data_dir: Path) -> Path:
    return data_dir / "exports"


def export_file_path(data_dir: Path, export_id: str, fmt: str) -> Path:
    return exports_dir(data_dir) / f"{export_id}.{fmt}"


def export_manifest_path(data_dir: Path, export_id: str) -> Path:
    return exports_dir(data_dir) / f"{export_id}_manifest.json"


def ensure_storage_dirs(data_dir: Path) -> None:
    for d in [runs_dir(data_dir), configs_dir(data_dir), exports_dir(data_dir)]:
        d.mkdir(parents=True, exist_ok=True)
