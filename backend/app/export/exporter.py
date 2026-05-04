import csv
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.models.export import ExportManifest, ExportRequest
from app.models.sample import Sample
from app.storage.export_store import ExportStore
from app.storage.paths import export_file_path
from app.storage.sample_store import SampleStore


class Exporter:
    def __init__(
        self,
        sample_store: SampleStore,
        export_store: ExportStore,
        data_dir: Path,
    ):
        self._sample_store = sample_store
        self._export_store = export_store
        self._data_dir = data_dir

    def create_export(self, request: ExportRequest) -> ExportManifest:
        export_id = str(uuid4())[:8]
        fmt = request.format.lower()
        if fmt not in ("jsonl", "csv"):
            fmt = "jsonl"

        out_path = export_file_path(self._data_dir, export_id, fmt)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        samples = list(self._stream_filtered_samples(request))

        if fmt == "jsonl":
            self._write_jsonl(samples, out_path)
        else:
            self._write_csv(samples, out_path)

        manifest = ExportManifest(
            export_id=export_id,
            run_ids=request.run_ids,
            format=fmt,
            filters=request.model_dump(exclude={"run_ids", "format"}),
            sample_count=len(samples),
            file_path=str(out_path),
            created_at=datetime.utcnow(),
        )
        self._export_store.save_manifest(manifest)
        return manifest

    def _stream_filtered_samples(self, request: ExportRequest):
        for run_id in request.run_ids:
            for sample in self._sample_store.stream_all_samples(run_id):
                if not self._matches_filter(sample, request):
                    continue
                yield sample

    def _matches_filter(self, sample: Sample, request: ExportRequest) -> bool:
        if request.include_only_valid and sample.status.value != "valid":
            return False
        if request.include_only_export_flagged and not sample.include_in_export:
            return False
        if request.filter_measurement_phrase:
            if sample.spec.measurement_phrase not in request.filter_measurement_phrase:
                return False
        if request.filter_value_kind:
            if sample.spec.value_kind.value not in request.filter_value_kind:
                return False
        if request.filter_model_ref:
            if sample.model_metadata.model_ref not in request.filter_model_ref:
                return False
        if request.filter_prompt_ref:
            if sample.model_metadata.prompt_ref not in request.filter_prompt_ref:
                return False
        return True

    def _write_jsonl(self, samples: list[Sample], path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for sample in samples:
                record = {
                    "sample_id": sample.sample_id,
                    "run_id": sample.run_id,
                    "generated_text": sample.generated_text,
                    "truth": {
                        "measurement_phrase": sample.spec.measurement_phrase,
                        "value_kind": sample.spec.value_kind.value,
                        "value_nominal": sample.spec.value_nominal,
                        "value_min": sample.spec.value_min,
                        "value_max": sample.spec.value_max,
                        "value_tolerance": sample.spec.value_tolerance,
                        "unit_norm": sample.spec.unit_norm,
                    },
                    "model_ref": sample.model_metadata.model_ref,
                    "prompt_ref": sample.model_metadata.prompt_ref,
                    "status": sample.status.value,
                    "created_at": sample.created_at.isoformat(),
                }
                f.write(json.dumps(record) + "\n")

    def _write_csv(self, samples: list[Sample], path: Path) -> None:
        fieldnames = [
            "sample_id", "run_id", "generated_text",
            "measurement_phrase", "value_kind", "value_nominal",
            "value_min", "value_max", "value_tolerance", "unit_norm",
            "model_ref", "prompt_ref", "status", "created_at",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for sample in samples:
                writer.writerow({
                    "sample_id": sample.sample_id,
                    "run_id": sample.run_id,
                    "generated_text": sample.generated_text,
                    "measurement_phrase": sample.spec.measurement_phrase,
                    "value_kind": sample.spec.value_kind.value,
                    "value_nominal": sample.spec.value_nominal,
                    "value_min": sample.spec.value_min,
                    "value_max": sample.spec.value_max,
                    "value_tolerance": sample.spec.value_tolerance,
                    "unit_norm": sample.spec.unit_norm,
                    "model_ref": sample.model_metadata.model_ref,
                    "prompt_ref": sample.model_metadata.prompt_ref,
                    "status": sample.status.value,
                    "created_at": sample.created_at.isoformat(),
                })
