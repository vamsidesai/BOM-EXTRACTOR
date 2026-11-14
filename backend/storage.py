"""Storage service managing drawings, results, preview images, and metadata."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import DrawingSummaryItem, DrawingResultSchema

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RESULTS_DIR = STORAGE_DIR / "results"
PREVIEWS_DIR = STORAGE_DIR / "previews"
EXPORTS_DIR = STORAGE_DIR / "exports"
DB_FILE = STORAGE_DIR / "db.json"


def ensure_storage_dirs():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


class StorageManager:
    def __init__(self):
        ensure_storage_dirs()
        self._load_db()

    def _load_db(self):
        if DB_FILE.exists():
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except Exception:
                self.db = {"drawings": {}}
        else:
            self.db = {"drawings": {}}
            self._save_db()

    def _save_db(self):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)

    def create_drawing(self, filename: str, file_bytes: bytes) -> str:
        drawing_id = str(uuid.uuid4())[:8]
        ext = Path(filename).suffix.lower()
        file_format = ext.lstrip(".").upper()

        drawing_upload_dir = UPLOADS_DIR / drawing_id
        drawing_upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = drawing_upload_dir / filename
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        metadata = {
            "id": drawing_id,
            "filename": filename,
            "file_format": file_format,
            "file_size_bytes": len(file_bytes),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "verified": False,
            "review_required": False,
            "review_reasons": None,
            "mean_confidence": None,
            "text_confidence": None,
            "structural_confidence": None,
            "drawing_number": None,
            "drawing_title": None,
            "revision": None,
            "bom_items_count": 0,
            "page_count": 1,
            "processing_seconds": None,
            "error_message": None,
            "source_path": str(file_path),
        }

        self.db["drawings"][drawing_id] = metadata
        self._save_db()
        return drawing_id

    def list_drawings(self) -> List[DrawingSummaryItem]:
        items = []
        for d in self.db["drawings"].values():
            items.append(DrawingSummaryItem(**d))
        items.sort(key=lambda x: x.uploaded_at, reverse=True)
        return items

    def get_metadata(self, drawing_id: str) -> Optional[DrawingSummaryItem]:
        data = self.db["drawings"].get(drawing_id)
        if not data:
            return None
        return DrawingSummaryItem(**data)

    def get_source_path(self, drawing_id: str) -> Optional[Path]:
        data = self.db["drawings"].get(drawing_id)
        if not data:
            return None
        return Path(data["source_path"])

    def get_result(self, drawing_id: str) -> Optional[Dict[str, Any]]:
        result_file = RESULTS_DIR / f"{drawing_id}.json"
        if not result_file.exists():
            return None
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_result(self, drawing_id: str, result_dict: Dict[str, Any]):
        result_file = RESULTS_DIR / f"{drawing_id}.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        # Update metadata summary
        if drawing_id in self.db["drawings"]:
            d = self.db["drawings"][drawing_id]
            d["status"] = "completed"
            d["processing_seconds"] = result_dict.get("processing_seconds")
            summ = result_dict.get("summary", {})
            d["drawing_number"] = summ.get("drawing_number") or result_dict.get("title_block", {}).get("drawing_number", {}).get("value")
            d["drawing_title"] = summ.get("drawing_title") or result_dict.get("title_block", {}).get("drawing_title", {}).get("value")
            d["revision"] = summ.get("revision") or result_dict.get("title_block", {}).get("revision", {}).get("value")
            d["bom_items_count"] = len(result_dict.get("bom", []))
            d["page_count"] = len(result_dict.get("pages", [1]))
            d["mean_confidence"] = summ.get("mean_confidence")
            d["text_confidence"] = summ.get("text_confidence")
            d["structural_confidence"] = summ.get("structural_confidence")
            d["review_required"] = summ.get("review_required", False)
            d["review_reasons"] = summ.get("review_reasons")
            self._save_db()

    def update_drawing_status(self, drawing_id: str, status: str, error_message: Optional[str] = None):
        if drawing_id in self.db["drawings"]:
            self.db["drawings"][drawing_id]["status"] = status
            if error_message:
                self.db["drawings"][drawing_id]["error_message"] = error_message
            self._save_db()

    def update_drawing_verification(self, drawing_id: str, verified: bool):
        if drawing_id in self.db["drawings"]:
            self.db["drawings"][drawing_id]["verified"] = verified
            self._save_db()

    def update_result_content(self, drawing_id: str, updates: Dict[str, Any]):
        res = self.get_result(drawing_id)
        if not res:
            return None

        if "title_block" in updates and updates["title_block"] is not None:
            # updates could be full dict or partial field overrides
            for k, val in updates["title_block"].items():
                if isinstance(val, dict):
                    res["title_block"][k] = val
                else:
                    if k in res["title_block"]:
                        res["title_block"][k]["value"] = val
                    else:
                        res["title_block"][k] = {"value": val, "confidence": 1.0, "bbox": None, "raw": val}

        if "bom" in updates and updates["bom"] is not None:
            res["bom"] = updates["bom"]

        if "revisions" in updates and updates["revisions"] is not None:
            res["revisions"] = updates["revisions"]

        if "notes" in updates and updates["notes"] is not None:
            res["notes"] = updates["notes"]

        self.save_result(drawing_id, res)
        return res

    def delete_drawing(self, drawing_id: str) -> bool:
        if drawing_id not in self.db["drawings"]:
            return False

        del self.db["drawings"][drawing_id]
        self._save_db()

        # Clean up files
        shutil.rmtree(UPLOADS_DIR / drawing_id, ignore_errors=True)
        shutil.rmtree(PREVIEWS_DIR / drawing_id, ignore_errors=True)
        res_file = RESULTS_DIR / f"{drawing_id}.json"
        if res_file.exists():
            res_file.unlink(missing_ok=True)
        return True


storage = StorageManager()

