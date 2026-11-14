"""Visual validation overlays: highlighted bounding boxes over the drawing
so a reviewer can verify what was extracted from where."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

COLORS = {  # BGR
    "title_block": (200, 90, 20),
    "bom": (40, 160, 40),
    "bom_header": (20, 110, 20),
    "bom_row_flag": (0, 165, 255),
    "revision": (0, 140, 230),
    "notes": (170, 50, 160),
    "material": (40, 40, 220),
    "surface_finish": (200, 0, 200),
    "heat_treatment": (0, 90, 200),
    "standard": (130, 130, 130),
}
LABELS = {"title_block": "TITLE BLOCK", "bom": "BOM", "revision": "REVISIONS", "notes": "NOTES"}


def render_page(pa, specs, bom_rows, out_path: Path, max_width: int = 3200) -> None:
    img = pa.image.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    th = max(2, int(min(h, w) / 700))
    fs = max(0.6, min(h, w) / 1800)

    tint = img.copy()
    for r in pa.result.regions:
        col = COLORS.get(r.kind, (100, 100, 100))
        x0, y0, x1, y1 = (int(v) for v in r.bbox)
        cv2.rectangle(tint, (x0, y0), (x1, y1), col, -1)
    img = cv2.addWeighted(tint, 0.12, img, 0.88, 0)

    # thin boxes around each title-block cell that has text
    for c in pa.tb_cells:
        if c.words:
            cv2.rectangle(img, (int(c.x0), int(c.y0)), (int(c.x1), int(c.y1)),
                          COLORS["title_block"], max(1, th // 2))
    for t in pa.bom_tables:
        x0, y0, x1, y1 = (int(v) for v in t.header_bbox)
        cv2.rectangle(img, (x0, y0), (x1, y1), COLORS["bom_header"], th)
    for r in bom_rows:
        if r.bbox and set(r.flags) - {"mass_unit_assumed_kg"}:
            x0, y0, x1, y1 = (int(v) for v in r.bbox)
            cv2.rectangle(img, (x0, y0), (x1, y1), COLORS["bom_row_flag"], th)
            _label(img, "CHECK: " + ",".join(f for f in r.flags if f != "mass_unit_assumed_kg"),
                   x1 + 4, y1 - 2, COLORS["bom_row_flag"], fs * 0.6, max(1, th // 2))
    for s in specs:
        if s.bbox is None or s.source == "bom":
            continue
        x0, y0, x1, y1 = (int(v) for v in s.bbox)
        cv2.rectangle(img, (x0 - 3, y0 - 3), (x1 + 3, y1 + 3), COLORS.get(s.category, (0, 0, 0)),
                      max(1, th // 2))

    for r in pa.result.regions:
        col = COLORS.get(r.kind, (100, 100, 100))
        x0, y0, x1, y1 = (int(v) for v in r.bbox)
        cv2.rectangle(img, (x0, y0), (x1, y1), col, th * 2)
        _label(img, f"{LABELS.get(r.kind, r.kind.upper())}  conf {r.confidence:.2f}", x0, y0 - 6,
               col, fs, th)

    _legend(img, fs, th)
    if w > max_width:
        s = max_width / w
        img = cv2.resize(img, (max_width, int(h * s)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out_path), img)


def _label(img, text, x, y, col, fs, th):
    (tw, tht), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, th)
    y = max(y, tht + 4)
    cv2.rectangle(img, (x, y - tht - 4), (x + tw + 6, y + base), col, -1)
    cv2.putText(img, text, (x + 3, y - 2), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), th,
                cv2.LINE_AA)


def _legend(img, fs, th):
    items = [("Title block", "title_block"), ("BOM", "bom"), ("Revisions", "revision"),
             ("Notes", "notes"), ("Material", "material"), ("Finish", "surface_finish"),
             ("Heat treat", "heat_treatment"), ("Row to check", "bom_row_flag")]
    x, y = 12, 12
    s = fs * 0.7
    for name, key in items:
        (tw, tht), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, s, max(1, th // 2))
        cv2.rectangle(img, (x, y), (x + tht, y + tht), COLORS[key], -1)
        cv2.putText(img, name, (x + tht + 6, y + tht), cv2.FONT_HERSHEY_SIMPLEX, s, (30, 30, 30),
                    max(1, th // 2), cv2.LINE_AA)
        x += tw + tht + 30
