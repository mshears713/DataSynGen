from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.core.exceptions import NotFoundError
from app.models.export import ExportManifest, ExportRequest

router = APIRouter(prefix="/exports", tags=["exports"])


def _exporter(request: Request):
    return request.app.state.exporter


def _export_store(request: Request):
    return request.app.state.export_store


def _manifest_to_ui(manifest: ExportManifest) -> dict:
    """Convert backend ExportManifest to the ExportRecord shape expected by the frontend."""
    file_path = Path(manifest.file_path)
    filename = file_path.name if file_path.name else f"export_{manifest.export_id}.{manifest.format}"
    filters_str = " · ".join(
        f"{k}={v}" for k, v in manifest.filters.items() if v is not None
    ) if manifest.filters else ""
    return {
        "id": manifest.export_id,
        "filename": filename,
        "format": manifest.format.upper(),
        "sampleCount": manifest.sample_count,
        "createdAt": manifest.created_at.isoformat(),
        "filters": filters_str,
        # Keep original fields too
        "run_ids": manifest.run_ids,
        "file_path": manifest.file_path,
    }


@router.post("", status_code=201)
async def create_export(body: ExportRequest, request: Request) -> dict:
    exporter = _exporter(request)
    rs = request.app.state.run_store
    for run_id in body.run_ids:
        if not rs.run_exists(run_id):
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    manifest = exporter.create_export(body)
    return _manifest_to_ui(manifest)


@router.get("")
async def list_exports(request: Request) -> list[dict]:
    es = _export_store(request)
    manifests = es.load_all_manifests()
    manifests.sort(key=lambda m: m.created_at, reverse=True)
    return [_manifest_to_ui(m) for m in manifests]


@router.get("/{export_id}")
async def get_export(export_id: str, request: Request) -> dict:
    es = _export_store(request)
    try:
        manifest = es.load_manifest(export_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Export '{export_id}' not found")
    return _manifest_to_ui(manifest)


@router.get("/{export_id}/download")
async def download_export(export_id: str, request: Request) -> FileResponse:
    es = _export_store(request)
    try:
        manifest = es.load_manifest(export_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Export '{export_id}' not found")
    file_path = Path(manifest.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found on disk")
    media_type = "application/jsonlines+json" if manifest.format == "jsonl" else "text/csv"
    filename = f"export_{export_id}.{manifest.format}"
    return FileResponse(path=str(file_path), media_type=media_type, filename=filename)
