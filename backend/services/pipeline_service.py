"""Pipeline execution service for BOMX drawings."""
from __future__ import annotations

import copy
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import pymupdf as fitz
from PIL import Image

from bomx.config import DEFAULT_CONFIG
from bomx.pipeline import process_file
from ..schemas import ExtractionConfigRequest
from ..storage import PREVIEWS_DIR, storage

log = logging.getLogger(__name__)

# In-memory job progress tracking
JOB_STATUS: Dict[str, Dict[str, Any]] = {}


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    return JOB_STATUS.get(job_id)


def _render_pdf_pages(pdf_path: Path, out_dir: Path, dpi: int = 150) -> List[Dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_meta = []
    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for i in range(len(doc)):
        page = doc[i]
        pix = page.get_pixmap(matrix=matrix)
        out_png = out_dir / f"page_{i + 1}.png"
        pix.save(str(out_png))
        pages_meta.append({
            "page_num": i + 1,
            "width": pix.width,
            "height": pix.height,
            "path": str(out_png),
        })
    doc.close()
    return pages_meta


def _render_image_page(img_path: Path, out_dir: Path) -> List[Dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "page_1.png"
    with Image.open(img_path) as img:
        img_rgb = img.convert("RGB")
        w, h = img_rgb.size
        img_rgb.save(out_png, "PNG")
    return [{
        "page_num": 1,
        "width": w,
        "height": h,
        "path": str(out_png),
    }]


def run_extraction_sync(drawing_id: str, config_req: Optional[ExtractionConfigRequest] = None) -> Dict[str, Any]:
    job_id = f"job_{drawing_id}"
    JOB_STATUS[job_id] = {
        "job_id": job_id,
        "drawing_id": drawing_id,
        "status": "processing",
        "progress": 10,
        "current_step": "Initializing extraction configuration",
        "error_message": None,
    }
    storage.update_drawing_status(drawing_id, "processing")

    source_path = storage.get_source_path(drawing_id)
    if not source_path or not source_path.exists():
        err = f"Source file for drawing {drawing_id} not found."
        JOB_STATUS[job_id]["status"] = "failed"
        JOB_STATUS[job_id]["error_message"] = err
        storage.update_drawing_status(drawing_id, "failed", err)
        raise FileNotFoundError(err)

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if config_req:
        cfg["dpi"] = config_req.dpi
        cfg["ocr_lang"] = config_req.ocr_lang
        cfg["cell_ocr"] = config_req.cell_ocr
        cfg["deskew"] = config_req.deskew
        cfg["auto_rotate"] = config_req.auto_rotate
        cfg["low_conf_threshold"] = config_req.low_conf_threshold

    preview_dir = PREVIEWS_DIR / drawing_id
    preview_dir.mkdir(parents=True, exist_ok=True)

    try:
        JOB_STATUS[job_id]["progress"] = 25
        JOB_STATUS[job_id]["current_step"] = "Rendering document preview pages"

        # Pre-render web preview pages
        suffix = source_path.suffix.lower()
        rendered_pages = []
        if suffix == ".pdf":
            rendered_pages = _render_pdf_pages(source_path, preview_dir, dpi=150)
        elif suffix in [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]:
            rendered_pages = _render_image_page(source_path, preview_dir)

        JOB_STATUS[job_id]["progress"] = 45
        JOB_STATUS[job_id]["current_step"] = "Detecting drawing layout, regions and tables"

        # Run BOMX pipeline
        force_ocr = config_req.force_ocr if config_req else False
        overlay_dir = preview_dir / "overlays"
        res = process_file(source_path, cfg, force_ocr=force_ocr, overlay_dir=overlay_dir)

        JOB_STATUS[job_id]["progress"] = 75
        JOB_STATUS[job_id]["current_step"] = "Parsing title block, BOM rows, notes and specs"

        # If CAD format without initial preview, check if overlay generated or export pa image
        if not rendered_pages:
            # Check overlay images
            for page_idx, page_res in enumerate(res.pages):
                target_png = preview_dir / f"page_{page_idx + 1}.png"
                if page_res.overlay_path and Path(page_res.overlay_path).exists():
                    shutil.copyfile(page_res.overlay_path, target_png)
                elif suffix in [".dxf", ".dwg"]:
                    # Create placeholder or copy rendered image
                    from PIL import Image, ImageDraw
                    img = Image.new("RGB", (page_res.width or 2000, page_res.height or 1400), color=(255, 255, 255))
                    d = ImageDraw.Draw(img)
                    d.text((50, 50), f"CAD Drawing: {source_path.name} (Page {page_idx+1})", fill=(0, 0, 0))
                    img.save(target_png)

        JOB_STATUS[job_id]["progress"] = 90
        JOB_STATUS[job_id]["current_step"] = "Formatting structured output and bounding boxes"

        result_dict = res.to_dict()

        # Augment pages with image_url and geometry
        for idx, page in enumerate(result_dict.get("pages", [])):
            p_num = idx + 1
            page["image_url"] = f"/api/drawings/{drawing_id}/pages/{p_num}/image"
            if page.get("overlay_path"):
                page["overlay_url"] = f"/api/drawings/{drawing_id}/pages/{p_num}/overlay"

        # Save to storage
        storage.save_result(drawing_id, result_dict)

        JOB_STATUS[job_id]["progress"] = 100
        JOB_STATUS[job_id]["status"] = "completed"
        JOB_STATUS[job_id]["current_step"] = "Extraction completed successfully"

        return result_dict

    except Exception as e:
        log.exception(f"Extraction failed for {drawing_id}: {e}")
        err_msg = str(e)
        JOB_STATUS[job_id]["status"] = "failed"
        JOB_STATUS[job_id]["progress"] = 100
        JOB_STATUS[job_id]["error_message"] = err_msg
        storage.update_drawing_status(drawing_id, "failed", err_msg)
        raise
