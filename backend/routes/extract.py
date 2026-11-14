"""Extraction trigger and status polling routes."""
from __future__ import annotations

import asyncio
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from ..schemas import ExtractionConfigRequest, ExtractionJobStatus
from ..services.pipeline_service import get_job_status, run_extraction_sync
from ..storage import storage

router = APIRouter(prefix="/api/extract", tags=["Extraction"])


@router.post("/{drawing_id}")
async def start_extraction(
    drawing_id: str,
    config: Optional[ExtractionConfigRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    meta = storage.get_metadata(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Drawing not found.")

    job_id = f"job_{drawing_id}"
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_extraction_sync, drawing_id, config)

    return {"message": "Extraction started", "job_id": job_id, "drawing_id": drawing_id}


@router.get("/{drawing_id}/status", response_model=ExtractionJobStatus)
async def get_extraction_status(drawing_id: str):
    job_id = f"job_{drawing_id}"
    status = get_job_status(job_id)

    meta = storage.get_metadata(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Drawing not found.")

    if not status:
        # Fall back to drawing metadata status
        is_completed = meta.status == "completed"
        return ExtractionJobStatus(
            job_id=job_id,
            drawing_id=drawing_id,
            status=meta.status,
            progress=100 if is_completed else 0,
            current_step="Completed" if is_completed else "Idle",
            error_message=meta.error_message,
        )

    return ExtractionJobStatus(**status)

