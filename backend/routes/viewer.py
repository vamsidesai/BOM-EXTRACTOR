"""Drawing viewer routes: original files, page images, and Konva overlays."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image

from ..storage import PREVIEWS_DIR, storage

router = APIRouter(prefix="/api/drawings", tags=["Viewer"])


@router.get("/{drawing_id}/file")
async def get_original_file(drawing_id: str):
    source_path = storage.get_source_path(drawing_id)
    if not source_path or not source_path.exists():
        raise HTTPException(status_code=404, detail="Original drawing file not found.")

    media_type = "application/pdf" if source_path.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(
        str(source_path),
        media_type=media_type,
        filename=source_path.name,
    )


@router.get("/{drawing_id}/pages/{page_num}/image")
async def get_page_image(drawing_id: str, page_num: int):
    preview_dir = PREVIEWS_DIR / drawing_id
    page_img = preview_dir / f"page_{page_num}.png"

    if not page_img.exists():
        # Check if source is image and copy
        source_path = storage.get_source_path(drawing_id)
        if source_path and source_path.exists() and source_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]:
            preview_dir.mkdir(parents=True, exist_ok=True)
            with Image.open(source_path) as im:
                im.convert("RGB").save(page_img, "PNG")
        else:
            raise HTTPException(status_code=404, detail=f"Page {page_num} image not found.")

    return FileResponse(str(page_img), media_type="image/png")


@router.get("/{drawing_id}/pages/{page_num}/overlay")
async def get_page_overlay_image(drawing_id: str, page_num: int):
    overlay_path = PREVIEWS_DIR / drawing_id / "overlays" / f"page_{page_num}_overlay.png"
    if not overlay_path.exists():
        # Fall back to base page image
        return await get_page_image(drawing_id, page_num)
    return FileResponse(str(overlay_path), media_type="image/png")


@router.get("/{drawing_id}/overlays")
async def get_drawing_overlays(drawing_id: str):
    res = storage.get_result(drawing_id)
    if not res:
        raise HTTPException(status_code=404, detail="Drawing extraction results not found.")

    pages = res.get("pages", [])
    overlays_by_page: Dict[int, List[Dict[str, Any]]] = {}

    for p_idx, page in enumerate(pages):
        page_num = p_idx + 1
        page_w = page.get("width") or 2000
        page_h = page.get("height") or 1400
        page_overlays = []

        # 1. Macro Regions (Title block, BOM table, Revisions, Notes)
        for r in page.get("regions", []):
            bb = r.get("bbox")
            if bb and len(bb) == 4:
                x0, y0, x1, y1 = bb
                page_overlays.append({
                    "id": f"region_{r.get('kind')}_{len(page_overlays)}",
                    "type": "region",
                    "category": r.get("kind"),
                    "label": r.get("kind", "").replace("_", " ").title(),
                    "confidence": r.get("confidence", 1.0),
                    "bbox": [x0, y0, x1, y1],
                    "norm": [x0 / page_w, y0 / page_h, (x1 - x0) / page_w, (y1 - y0) / page_h],
                    "color": _region_color(r.get("kind")),
                })

        # 2. Title Block Fields
        for field_name, f_val in res.get("title_block", {}).items():
            if isinstance(f_val, dict):
                bb = f_val.get("bbox")
                if bb and len(bb) == 4:
                    x0, y0, x1, y1 = bb
                    page_overlays.append({
                        "id": f"tb_{field_name}",
                        "type": "title_field",
                        "field": field_name,
                        "label": field_name.replace("_", " ").title(),
                        "value": f_val.get("value"),
                        "confidence": f_val.get("confidence", 1.0),
                        "bbox": [x0, y0, x1, y1],
                        "norm": [x0 / page_w, y0 / page_h, (x1 - x0) / page_w, (y1 - y0) / page_h],
                        "color": "#2563EB",  # Engineering blue
                    })

        # 3. BOM Rows
        for r_idx, row in enumerate(res.get("bom", [])):
            if row.get("page", 1) == page_num or len(pages) == 1:
                bb = row.get("bbox")
                if bb and len(bb) == 4:
                    x0, y0, x1, y1 = bb
                    page_overlays.append({
                        "id": f"bom_row_{r_idx}",
                        "type": "bom_row",
                        "rowIndex": r_idx,
                        "label": f"BOM Item {row.get('item', r_idx + 1)}",
                        "value": f"{row.get('part_number', '')} {row.get('description', '')}".strip(),
                        "confidence": row.get("confidence", 1.0),
                        "bbox": [x0, y0, x1, y1],
                        "norm": [x0 / page_w, y0 / page_h, (x1 - x0) / page_w, (y1 - y0) / page_h],
                        "color": "#16A34A" if not row.get("flags") else "#D97706",
                    })

        # 4. Specifications & Notes
        for s_idx, spec in enumerate(res.get("specs", [])):
            if spec.get("page", 1) == page_num:
                bb = spec.get("bbox")
                if bb and len(bb) == 4:
                    x0, y0, x1, y1 = bb
                    page_overlays.append({
                        "id": f"spec_{s_idx}",
                        "type": "spec",
                        "label": f"Spec: {spec.get('category')}",
                        "value": spec.get("value"),
                        "confidence": spec.get("confidence", 1.0),
                        "bbox": [x0, y0, x1, y1],
                        "norm": [x0 / page_w, y0 / page_h, (x1 - x0) / page_w, (y1 - y0) / page_h],
                        "color": "#0284C7",
                    })

        overlays_by_page[page_num] = page_overlays

    return {
        "drawing_id": drawing_id,
        "page_count": len(pages),
        "overlays": overlays_by_page,
    }


def _region_color(kind: Optional[str]) -> str:
    mapping = {
        "title_block": "#2563EB",  # Blue
        "bom": "#16A34A",          # Green
        "revision": "#8B5CF6",     # Purple / Lavender
        "notes": "#D97706",        # Amber
        "other": "#64748B",        # Gray
    }
    return mapping.get(kind or "other", "#2563EB")

