"""Dashboard statistics and overview endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from ..schemas import DashboardStatsResponse
from ..storage import storage

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats():
    drawings = storage.list_drawings()

    total_drawings = len(drawings)
    verified_drawings = sum(1 for d in drawings if d.verified)
    failed_drawings = sum(1 for d in drawings if d.status == "failed")
    review_required_drawings = sum(
        1 for d in drawings if d.status == "completed" and not d.verified and (d.review_required or (d.mean_confidence and d.mean_confidence < 0.85))
    )
    total_bom_items = sum(d.bom_items_count for d in drawings)

    # Confidence distribution
    conf_dist = {"high (>85%)": 0, "medium (65-85%)": 0, "low (<65%)": 0}
    for d in drawings:
        if d.mean_confidence is not None:
            if d.mean_confidence >= 0.85:
                conf_dist["high (>85%)"] += 1
            elif d.mean_confidence >= 0.65:
                conf_dist["medium (65-85%)"] += 1
            else:
                conf_dist["low (<65%)"] += 1

    # File type distribution
    file_type_dist = {}
    for d in drawings:
        fmt = d.file_format or "OTHER"
        file_type_dist[fmt] = file_type_dist.get(fmt, 0) + 1

    return DashboardStatsResponse(
        total_drawings=total_drawings,
        verified_drawings=verified_drawings,
        review_required_drawings=review_required_drawings,
        failed_drawings=failed_drawings,
        total_bom_items=total_bom_items,
        recent_drawings=drawings[:10],
        confidence_distribution=conf_dist,
        file_type_distribution=file_type_dist,
    )

