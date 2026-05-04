import json
import os
from pathlib import Path

from app.core.exceptions import NotFoundError
from app.models.export import ExportManifest
from app.storage.paths import export_manifest_path, exports_dir


class ExportStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir

    def save_manifest(self, manifest: ExportManifest) -> None:
        path = export_manifest_path(self._data_dir, manifest.export_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load_manifest(self, export_id: str) -> ExportManifest:
        path = export_manifest_path(self._data_dir, export_id)
        if not path.exists():
            raise NotFoundError("Export", export_id)
        return ExportManifest(**json.loads(path.read_text(encoding="utf-8")))

    def load_all_manifests(self) -> list[ExportManifest]:
        edir = exports_dir(self._data_dir)
        if not edir.exists():
            return []
        manifests = []
        for path in sorted(edir.glob("*_manifest.json")):
            try:
                manifests.append(ExportManifest(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return manifests
