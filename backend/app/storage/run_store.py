import json
import os
from pathlib import Path

from app.core.exceptions import NotFoundError
from app.models.run import Run, RunEvent, RunStatus
from app.storage.paths import (
    events_path,
    run_dir,
    run_metadata_path,
    runs_dir,
)


class RunStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir

    def save_run(self, run: Run) -> None:
        rdir = run_dir(self._data_dir, run.run_id)
        rdir.mkdir(parents=True, exist_ok=True)
        path = run_metadata_path(self._data_dir, run.run_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load_run(self, run_id: str) -> Run:
        path = run_metadata_path(self._data_dir, run_id)
        if not path.exists():
            raise NotFoundError("Run", run_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return Run(**data)

    def load_all_runs(self) -> list[Run]:
        rdir = runs_dir(self._data_dir)
        if not rdir.exists():
            return []
        runs = []
        for item in sorted(rdir.iterdir()):
            if not item.is_dir():
                continue
            meta = item / "metadata.json"
            if not meta.exists():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                runs.append(Run(**data))
            except Exception:
                continue
        return runs

    def run_exists(self, run_id: str) -> bool:
        return run_metadata_path(self._data_dir, run_id).exists()

    def get_run_dir(self, run_id: str) -> Path:
        return run_dir(self._data_dir, run_id)

    def append_event(self, event: RunEvent) -> None:
        path = events_path(self._data_dir, event.run_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def load_events(self, run_id: str, limit: int = 200) -> list[RunEvent]:
        path = events_path(self._data_dir, run_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(RunEvent(**json.loads(line)))
                except Exception:
                    continue
        return events[-limit:]

    def recover_stale_running_runs(self) -> list[str]:
        """Mark any runs stuck in 'running' state as 'paused' on startup."""
        recovered = []
        for run in self.load_all_runs():
            if run.status == RunStatus.running:
                run.status = RunStatus.paused
                run.notes = (run.notes + " [recovered on startup]").strip()
                self.save_run(run)
                recovered.append(run.run_id)
        return recovered
