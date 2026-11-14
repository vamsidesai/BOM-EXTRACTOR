"""Export service for BOMX extraction results (Excel, CSV, JSON)."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..storage import EXPORTS_DIR, storage

# Styling constants matching BOMX enterprise aesthetic
HDR_FILL = PatternFill("solid", fgColor="172B4D")  # Dark navy
HDR_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
ROW_BAND = PatternFill("solid", fgColor="F8FAFC")
BORDER_THIN = Side(border_style="thin", color="E4EAF2")
CELL_BORDER = Border(left=BORDER_THIN, right=BORDER_THIN, top=BORDER_THIN, bottom=BORDER_THIN)


def generate_excel_export(drawing_id: str) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    res = storage.get_result(drawing_id)
    meta = storage.get_metadata(drawing_id)
    if not res:
        raise ValueError(f"No result found for drawing {drawing_id}")

    out_path = EXPORTS_DIR / f"{meta.filename if meta else drawing_id}_extracted.xlsx"
    wb = Workbook()

    # 1. Sheet: Summary
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["Drawing Information Summary", ""])
    ws_sum.cell(1, 1).font = Font(name="Arial", size=13, bold=True, color="172B4D")

    summary_rows = [
        ("Source File", meta.filename if meta else res.get("source_file")),
        ("Drawing Number", res.get("summary", {}).get("drawing_number") or res.get("title_block", {}).get("drawing_number", {}).get("value")),
        ("Drawing Title", res.get("summary", {}).get("drawing_title") or res.get("title_block", {}).get("drawing_title", {}).get("value")),
        ("Revision", res.get("summary", {}).get("revision") or res.get("title_block", {}).get("revision", {}).get("value")),
        ("Status", "Verified" if meta and meta.verified else ("Needs Review" if res.get("summary", {}).get("review_required") else "Extracted")),
        ("Mean OCR Confidence", f"{round((res.get('summary', {}).get('mean_confidence') or 0) * 100, 1)}%"),
        ("Structural Confidence", f"{round((res.get('summary', {}).get('structural_confidence') or 0) * 100, 1)}%"),
        ("Total BOM Items", len(res.get("bom", []))),
        ("Total Pages", len(res.get("pages", [1]))),
        ("Processing Time (s)", f"{res.get('processing_seconds', 0)}s"),
        ("Review Reasons", res.get("summary", {}).get("review_reasons") or "None"),
    ]

    for k, v in summary_rows:
        ws_sum.append([k, str(v) if v is not None else ""])

    for r in range(2, len(summary_rows) + 3):
        ws_sum.cell(r, 1).font = Font(name="Arial", size=10, bold=True, color="172B4D")
        ws_sum.cell(r, 1).fill = PatternFill("solid", fgColor="F1F5F9")
        ws_sum.cell(r, 1).border = CELL_BORDER
        ws_sum.cell(r, 2).border = CELL_BORDER

    ws_sum.column_dimensions["A"].width = 25
    ws_sum.column_dimensions["B"].width = 50

    # 2. Sheet: Bill of Materials
    ws_bom = wb.create_sheet(title="Bill of Materials")
    bom_headers = ["Item", "Part Number", "Description", "Quantity", "Material Grade", "Mass / Weight", "Remarks", "Flags", "Confidence"]
    ws_bom.append(bom_headers)
    for col_idx in range(1, len(bom_headers) + 1):
        cell = ws_bom.cell(1, col_idx)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    bom_rows = res.get("bom", [])
    for row_idx, r in enumerate(bom_rows, start=2):
        row_data = [
            r.get("item", ""),
            r.get("part_number", ""),
            r.get("description", ""),
            r.get("quantity", ""),
            r.get("material", ""),
            r.get("mass", ""),
            r.get("remarks", ""),
            "; ".join(r.get("flags", [])) if r.get("flags") else "",
            f"{round((r.get('confidence') or 1.0) * 100, 1)}%",
        ]
        ws_bom.append(row_data)
        fill = ROW_BAND if row_idx % 2 == 0 else PatternFill(fill_type=None)
        for c in range(1, len(row_data) + 1):
            cell = ws_bom.cell(row_idx, c)
            cell.border = CELL_BORDER
            if fill.fill_type:
                cell.fill = fill

    # Auto-adjust column widths
    for col in ws_bom.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_bom.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # 3. Sheet: Title Block
    ws_tb = wb.create_sheet(title="Title Block")
    tb_headers = ["Field Name", "Extracted Value", "Confidence", "Raw OCR"]
    ws_tb.append(tb_headers)
    for col_idx in range(1, len(tb_headers) + 1):
        cell = ws_tb.cell(1, col_idx)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT

    tb = res.get("title_block", {})
    for row_idx, (k, val_obj) in enumerate(tb.items(), start=2):
        if isinstance(val_obj, dict):
            val = val_obj.get("value", "")
            conf = f"{round((val_obj.get('confidence') or 0) * 100, 1)}%"
            raw = val_obj.get("raw", "")
        else:
            val = str(val_obj)
            conf = "100%"
            raw = str(val_obj)
        ws_tb.append([k.replace("_", " ").title(), val, conf, raw])
        for c in range(1, 5):
            ws_tb.cell(row_idx, c).border = CELL_BORDER

    ws_tb.column_dimensions["A"].width = 25
    ws_tb.column_dimensions["B"].width = 35
    ws_tb.column_dimensions["C"].width = 15
    ws_tb.column_dimensions["D"].width = 35

    # 4. Sheet: Revisions & Notes
    ws_rev = wb.create_sheet(title="Revisions & Notes")
    ws_rev.append(["Revision History"])
    ws_rev.cell(1, 1).font = Font(name="Arial", size=11, bold=True)
    rev_headers = ["Rev", "Description", "Date", "Approved By", "Confidence"]
    ws_rev.append(rev_headers)
    for c in range(1, len(rev_headers) + 1):
        ws_rev.cell(2, c).fill = HDR_FILL
        ws_rev.cell(2, c).font = HDR_FONT

    revisions = res.get("revisions", [])
    for row_idx, r in enumerate(revisions, start=3):
        ws_rev.append([
            r.get("rev", ""),
            r.get("description", ""),
            r.get("date", ""),
            r.get("approved", ""),
            f"{round((r.get('confidence') or 1.0) * 100, 1)}%",
        ])

    notes = res.get("notes", [])
    start_note_row = ws_rev.max_row + 2
    ws_rev.cell(start_note_row, 1, "Technical Notes").font = Font(name="Arial", size=11, bold=True)
    ws_rev.cell(start_note_row + 1, 1, "#").fill = HDR_FILL
    ws_rev.cell(start_note_row + 1, 1).font = HDR_FONT
    ws_rev.cell(start_note_row + 1, 2, "Note Text").fill = HDR_FILL
    ws_rev.cell(start_note_row + 1, 2).font = HDR_FONT

    for n_idx, n in enumerate(notes, start=start_note_row + 2):
        ws_rev.append([n.get("number") or str(n_idx - start_note_row - 1), n.get("text", "")])

    ws_rev.column_dimensions["A"].width = 10
    ws_rev.column_dimensions["B"].width = 60
    ws_rev.column_dimensions["C"].width = 15
    ws_rev.column_dimensions["D"].width = 20

    wb.save(out_path)
    return out_path


def generate_csv_export(drawing_id: str) -> io.BytesIO:
    """Generate a ZIP containing CSV files for all extracted sections."""
    res = storage.get_result(drawing_id)
    if not res:
        raise ValueError(f"No result found for drawing {drawing_id}")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # BOM CSV
        bom_buf = io.StringIO()
        bom_writer = csv.writer(bom_buf)
        bom_writer.writerow(["Item", "Part Number", "Description", "Quantity", "Material", "Mass", "Remarks", "Flags", "Confidence"])
        for r in res.get("bom", []):
            bom_writer.writerow([
                r.get("item", ""),
                r.get("part_number", ""),
                r.get("description", ""),
                r.get("quantity", ""),
                r.get("material", ""),
                r.get("mass", ""),
                r.get("remarks", ""),
                "; ".join(r.get("flags", [])),
                r.get("confidence", 1.0)
            ])
        zf.writestr("bill_of_materials.csv", bom_buf.getvalue())

        # Title Block CSV
        tb_buf = io.StringIO()
        tb_writer = csv.writer(tb_buf)
        tb_writer.writerow(["Field", "Value", "Confidence"])
        for k, v in res.get("title_block", {}).items():
            val = v.get("value") if isinstance(v, dict) else str(v)
            conf = v.get("confidence") if isinstance(v, dict) else 1.0
            tb_writer.writerow([k, val, conf])
        zf.writestr("title_block.csv", tb_buf.getvalue())

        # Revisions CSV
        rev_buf = io.StringIO()
        rev_writer = csv.writer(rev_buf)
        rev_writer.writerow(["Rev", "Description", "Date", "Approved", "Confidence"])
        for r in res.get("revisions", []):
            rev_writer.writerow([r.get("rev"), r.get("description"), r.get("date"), r.get("approved"), r.get("confidence")])
        zf.writestr("revisions.csv", rev_buf.getvalue())

    zip_buffer.seek(0)
    return zip_buffer

