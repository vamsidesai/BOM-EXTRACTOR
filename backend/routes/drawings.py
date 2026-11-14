"""Drawings management and review routes."""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from ..schemas import (
    BatchDeleteRequest,
    DrawingDetailResponse,
    DrawingSummaryItem,
    UpdateDrawingPayload,
)
from ..storage import storage

router = APIRouter(prefix="/api/drawings", tags=["Drawings"])


@router.get("", response_model=List[DrawingSummaryItem])
async def list_drawings():
    return storage.list_drawings()


@router.get("/{drawing_id}", response_model=DrawingDetailResponse)
async def get_drawing_detail(drawing_id: str):
    meta = storage.get_metadata(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Drawing not found.")

    res = storage.get_result(drawing_id)
    preview_url = f"/api/drawings/{drawing_id}/pages/1/image"

    return DrawingDetailResponse(
        metadata=meta,
        result=res,
        preview_url=preview_url,
    )


@router.patch("/{drawing_id}")
async def update_drawing(drawing_id: str, payload: UpdateDrawingPayload):
    meta = storage.get_metadata(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Drawing not found.")

    if payload.verified is not None:
        storage.update_drawing_verification(drawing_id, payload.verified)

    updates = {}
    if payload.title_block is not None:
        updates["title_block"] = payload.title_block
    if payload.bom is not None:
        updates["bom"] = payload.bom
    if payload.revisions is not None:
        updates["revisions"] = payload.revisions
    if payload.notes is not None:
        updates["notes"] = payload.notes

    if updates:
        storage.update_result_content(drawing_id, updates)

    updated_meta = storage.get_metadata(drawing_id)
    updated_res = storage.get_result(drawing_id)
    return {
        "status": "success",
        "metadata": updated_meta,
        "result": updated_res,
    }


@router.delete("/{drawing_id}")
async def delete_drawing(drawing_id: str):
    success = storage.delete_drawing(drawing_id)
    if not success:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    return {"status": "success", "deleted_id": drawing_id}


@router.post("/batch-delete")
async def batch_delete_drawings(req: BatchDeleteRequest):
    deleted = []
    for d_id in req.ids:
        if storage.delete_drawing(d_id):
            deleted.append(d_id)
    return {"status": "success", "deleted": deleted, "count": len(deleted)}

