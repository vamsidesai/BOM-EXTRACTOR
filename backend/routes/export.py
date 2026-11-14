"""Export endpoints for Excel, CSV, and JSON."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from ..schemas import BatchExportRequest
from ..services.export_service import generate_csv_export, generate_excel_export
from ..storage import storage

router = APIRouter(prefix="/api/drawings", tags=["Export"])


@router.get("/{drawing_id}/export/excel")
async def export_excel(drawing_id: str):
    try:
        path = generate_excel_export(drawing_id)
        return FileResponse(
            str(path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=path.name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel generation failed: {str(e)}")


@router.get("/{drawing_id}/export/csv")
async def export_csv(drawing_id: str):
    try:
        buf = generate_csv_export(drawing_id)
        meta = storage.get_metadata(drawing_id)
        name = meta.filename if meta else drawing_id
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}_csv_tables.zip"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV generation failed: {str(e)}")


@router.get("/{drawing_id}/export/json")
async def export_json(drawing_id: str):
    res = storage.get_result(drawing_id)
    if not res:
        raise HTTPException(status_code=404, detail="Drawing result not found.")

    meta = storage.get_metadata(drawing_id)
    name = meta.filename if meta else drawing_id
    content = json.dumps(res, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}_extraction.json"'},
    )

