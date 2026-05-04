from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.core.exceptions import NotFoundError
from app.models.export import ExportRequest

router = APIRouter(prefix="/exports", tags=["exports"])


def _exporter(request: Request):
    return request.app.state.exporter


def _export_store(request: Request):
    return request.app.state.export_store


@router.post("", status_code=201)
async def create_export(body: ExportRequest, request: Request) -> dict:
    exporter = _exporter(request)
    rs = request.app.state.run_store

    # Validate run_ids exist
    for run_id in body.run_ids:
        if not rs.run_exists(run_id):
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    manifest = exporter.create_export(body)
    return manifest.model_dump()


@router.get("")
async def list_exports(request: Request) -> list[dict]:
    es = _export_store(request)
    manifests = es.load_all_manifests()
    manifests.sort(key=lambda m: m.created_at, reverse=True)
    return [m.model_dump() for m in manifests]


@router.get("/{export_id}")
async def get_export(export_id: str, request: Request) -> dict:
    es = _export_store(request)
    try:
        manifest = es.load_manifest(export_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Export '{export_id}' not found")
    return manifest.model_dump()


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

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )
