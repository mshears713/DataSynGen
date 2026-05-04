import json
import os
from pathlib import Path

from app.core.exceptions import NotFoundError
from app.models.failure import Failure, FailureCategory
from app.models.sample import Sample, SampleStatus, SampleUpdate
from app.storage.paths import failures_path, samples_path


class SampleStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir

    # --- Sample operations ---

    def append_sample(self, sample: Sample) -> None:
        path = samples_path(self._data_dir, sample.run_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(sample.model_dump_json() + "\n")

    def load_samples(
        self,
        run_id: str,
        status: SampleStatus | None = None,
        measurement_phrase: str | None = None,
        value_kind: str | None = None,
        model_ref: str | None = None,
        prompt_ref: str | None = None,
        include_in_export: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Sample], int]:
        path = samples_path(self._data_dir, run_id)
        if not path.exists():
            return [], 0

        all_samples: list[Sample] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = Sample(**json.loads(line))
                    if status and s.status != status:
                        continue
                    if measurement_phrase and s.spec.measurement_phrase != measurement_phrase:
                        continue
                    if value_kind and s.spec.value_kind.value != value_kind:
                        continue
                    if model_ref and s.model_metadata.model_ref != model_ref:
                        continue
                    if prompt_ref and s.model_metadata.prompt_ref != prompt_ref:
                        continue
                    if include_in_export is not None and s.include_in_export != include_in_export:
                        continue
                    all_samples.append(s)
                except Exception:
                    continue

        total = len(all_samples)
        return all_samples[offset : offset + limit], total

    def load_sample(self, run_id: str, sample_id: str) -> Sample:
        path = samples_path(self._data_dir, run_id)
        if not path.exists():
            raise NotFoundError("Sample", sample_id)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("sample_id") == sample_id:
                        return Sample(**data)
                except Exception:
                    continue
        raise NotFoundError("Sample", sample_id)

    def update_sample(self, run_id: str, sample_id: str, update: SampleUpdate) -> Sample:
        path = samples_path(self._data_dir, run_id)
        if not path.exists():
            raise NotFoundError("Sample", sample_id)

        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        found = False
        updated_sample = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("sample_id") == sample_id:
                    sample = Sample(**data)
                    patch = update.model_dump(exclude_none=True)
                    updated = sample.model_copy(update=patch)
                    from datetime import datetime
                    updated = updated.model_copy(update={"updated_at": datetime.utcnow()})
                    lines[i] = updated.model_dump_json() + "\n"
                    found = True
                    updated_sample = updated
                    break
            except Exception:
                continue

        if not found:
            raise NotFoundError("Sample", sample_id)

        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(lines), encoding="utf-8")
        os.replace(tmp, path)
        return updated_sample

    def get_processed_spec_ids(self, run_id: str) -> set[str]:
        path = samples_path(self._data_dir, run_id)
        if not path.exists():
            return set()
        spec_ids: set[str] = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if sid := data.get("spec_id"):
                        spec_ids.add(sid)
                except Exception:
                    continue
        return spec_ids

    def count_samples(self, run_id: str) -> dict[str, int]:
        path = samples_path(self._data_dir, run_id)
        if not path.exists():
            return {"total": 0, "valid": 0, "failed": 0}
        total = valid = failed = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    total += 1
                    status = data.get("status", "")
                    if status == "valid":
                        valid += 1
                    elif status == "failed":
                        failed += 1
                except Exception:
                    continue
        return {"total": total, "valid": valid, "failed": failed}

    # --- Failure operations ---

    def append_failure(self, failure: Failure) -> None:
        path = failures_path(self._data_dir, failure.run_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(failure.model_dump_json() + "\n")

    def load_failures(
        self,
        run_id: str,
        category: FailureCategory | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Failure], int]:
        path = failures_path(self._data_dir, run_id)
        if not path.exists():
            return [], 0

        all_failures: list[Failure] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    f_obj = Failure(**json.loads(line))
                    if category and f_obj.failure_category != category:
                        continue
                    all_failures.append(f_obj)
                except Exception:
                    continue

        total = len(all_failures)
        return all_failures[offset : offset + limit], total

    def load_failure(self, run_id: str, failure_id: str) -> Failure:
        path = failures_path(self._data_dir, run_id)
        if not path.exists():
            raise NotFoundError("Failure", failure_id)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("failure_id") == failure_id:
                        return Failure(**data)
                except Exception:
                    continue
        raise NotFoundError("Failure", failure_id)

    def stream_all_samples(self, run_id: str):
        path = samples_path(self._data_dir, run_id)
        if not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield Sample(**json.loads(line))
                except Exception:
                    continue
