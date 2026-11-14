"""Exporters: JSON, CSV and Excel (per drawing and consolidated batch)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import DrawingResult

BOM_STD = ["item", "part_number", "description", "quantity", "material", "mass", "remarks"]
BOM_HEAD = {"item": "Item No", "part_number": "Part Number", "description": "Description",
            "quantity": "Quantity", "material": "Material Grade", "mass": "Mass / Weight",
            "remarks": "Remarks"}
TB_ORDER = ["drawing_number", "drawing_title", "revision", "drawn_by", "date", "checked_by",
            "checked_date", "approved_by", "approved_date", "scale", "projection", "sheet", "size",
            "material", "finish", "heat_treatment", "weight", "tolerance", "units", "company",
            "part_number"]
SUMMARY_COLS = ["file", "drawing_number", "drawing_title", "revision", "author_date", "drawn_by", "date",
                "scale", "projection", "sheet", "material_callout", "surface_finish", "heat_treatment",
                "standards", "assembly_weight", "bom_items", "bom_total_quantity", "revisions", "notes",
                "pages", "file_format", "page_kinds", "input_type", "mean_confidence", "review_required", "review_reasons", "status"]


# ---------------------------------------------------------------- row builders

def bom_records(res: DrawingResult) -> list[dict]:
    dn = _dn(res)
    extras = [c for c in res.bom_columns if c not in BOM_STD]
    out = []
    for r in res.bom:
        rec = {"drawing_number": dn, "source_file": Path(res.source_file).name, "page": r.page}
        for k in BOM_STD:
            rec[k] = getattr(r, k)
        rec["quantity_value"] = r.quantity_value
        rec["mass_kg"] = round(r.mass_kg, 4) if r.mass_kg is not None else None
        for k in extras:
            rec[k] = r.extra.get(k)
        rec["confidence"] = r.confidence
        rec["structural_confidence"] = getattr(r, "structural_confidence", 1.0)
        rec["flags"] = ";".join(r.flags) or None
        out.append(rec)
    return out


def title_records(res: DrawingResult) -> list[dict]:
    keys = [k for k in TB_ORDER if k in res.title_block] + \
           [k for k in res.title_block if k not in TB_ORDER]
    return [{"drawing_number": _dn(res), "field": k, "value": res.title_block[k].value,
             "normalized": res.title_block[k].normalized, "confidence": res.title_block[k].confidence}
            for k in keys]


def spec_records(res: DrawingResult) -> list[dict]:
    return [{"drawing_number": _dn(res), "category": s.category, "subtype": s.subtype, "value": s.value,
             "source": s.source, "context": s.context, "page": s.page, "confidence": round(s.confidence, 3)}
            for s in res.specs]


def revision_records(res: DrawingResult) -> list[dict]:
    return [{"drawing_number": _dn(res), "rev": r.rev, "description": r.description, "date": r.date,
             "date_iso": r.extra.get("date_iso"), "approved": r.approved, "page": r.page,
             "confidence": r.confidence} for r in res.revisions]


def note_records(res: DrawingResult) -> list[dict]:
    return [{"drawing_number": _dn(res), "page": n["page"], "number": n["number"], "text": n["text"],
             "confidence": n["confidence"]} for n in res.notes]


def dimension_records(res: DrawingResult) -> list[dict]:
    return [{"drawing_number": _dn(res), "page": d.page, "type": d.dim_type,
             "text": d.text, "nominal": d.nominal, "tolerance": d.tolerance,
             "prefix": d.prefix, "suffix": d.suffix, "raw": d.raw,
             "confidence": round(d.confidence, 3)} for d in res.dimensions]


# Target attribute list (SOW section 3): (category, field name, description, getter)
ATTRIBUTES = [
    ("Title Block", "Drawing Number", "Unique identification number of drawing", "drawing_number"),
    ("Title Block", "Drawing Title", "Name/description of assembly or component", "drawing_title"),
    ("Title Block", "Revision Level", "Current revision code or number", "revision"),
    ("Title Block", "Author / Date", "Drawn by person name and sign date", "author_date"),
    ("BOM Table", "Item Number", "Sequential item callout in assembly", "bom:item"),
    ("BOM Table", "Part Number", "Internal or supplier part number", "bom:part_number"),
    ("BOM Table", "Part Description", "Textual description of the part", "bom:description"),
    ("BOM Table", "Quantity", "Number of units required per assembly", "bom:quantity"),
    ("BOM Table", "Material Grade", "Base material specified in BOM line", "bom:material"),
    ("BOM Table", "Mass / Weight", "Unit weight or total assembly weight", "bom:mass"),
    ("Technical Notes", "Material Callout", "General material note on drawing", "material_callout"),
    ("Technical Notes", "Surface Finish", "Coating, plating, or surface roughness", "surface_finish"),
    ("Technical Notes", "Heat Treatment", "Thermal processing specifications", "heat_treatment"),
]
ATTR_COLS = ["attribute_category", "target_field_name", "description", "extracted_output"]


def attribute_records(summary: dict, bom: list[dict]) -> list[dict]:
    """One drawing in the SOW attribute-table layout. BOM attributes list the
    value of every BOM line, one line per item, in item order."""
    out = []
    for cat, name, desc, key in ATTRIBUTES:
        if key.startswith("bom:"):
            k = key[4:]
            vals = ["" if r.get(k) is None else str(r.get(k)) for r in bom]
            val = "\n".join(vals) if any(vals) else None
        else:
            val = summary.get(key)
            if key == "revision" and val:
                val = val if str(val).upper().startswith("REV") else f"REV {val}"
        out.append({"attribute_category": cat, "target_field_name": name, "description": desc,
                    "extracted_output": val})
    return out


def _attr_sheet(ws, drawings: list[tuple[dict, list[dict]]]) -> None:
    """drawings = [(summary, bom_records), ...]. Styled like the SOW table."""
    multi = len(drawings) > 1
    head = (["Drawing Number"] if multi else []) + ["Attribute Category", "Target Field Name",
                                                     "Description", "Sample Extracted Output"]
    ws.append(head)
    for c in ws[1]:
        c.fill, c.font = _HDR_FILL, _HDR_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    band = PatternFill("solid", fgColor="F2F2F2")
    for summary, bom in drawings:
        for i, rec in enumerate(attribute_records(summary, bom)):
            row = ([_cell(summary.get("drawing_number") or summary.get("file"))] if multi else []) + \
                  [_cell(rec[c]) for c in ATTR_COLS]
            ws.append(row)
            r = ws.max_row
            for j in range(1, len(row) + 1):
                cell = ws.cell(row=r, column=j)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = Border(bottom=_THIN)
                if i % 2:
                    cell.fill = band
                if rec["extracted_output"] in (None, "") and j == len(row):
                    cell.fill = _LOW_FILL
    widths = ([20] if multi else []) + [18, 22, 44, 46]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _dn(res: DrawingResult):
    return res.summary.get("drawing_number") or Path(res.source_file).stem


# ---------------------------------------------------------------- writers

def write_json(res: DrawingResult, path: Path) -> None:
    path.write_text(json.dumps(res.to_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_formula(v):
    if isinstance(v, str) and v and v[0] in _FORMULA_PREFIXES:
        return f"'{v}"
    return v


def write_csv(records: list[dict], path: Path, columns: list[str] | None = None) -> None:
    cols = columns or _columns(records)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # BOM-prefixed for Excel
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r.get(k) is None else _sanitize_formula(r.get(k))) for k in cols})


def write_csvs(res: DrawingResult, out_dir: Path, stem: str) -> list[Path]:
    files = []
    groups = [("bom", bom_records(res)), ("title_block", title_records(res)),
              ("specs", spec_records(res)), ("revisions", revision_records(res)),
              ("notes", note_records(res))]
    if res.dimensions:
        groups.append(("dimensions", dimension_records(res)))
    for name, recs in groups:
        p = out_dir / f"{stem}_{name}.csv"
        write_csv(recs, p, _default_cols(name, recs))
        files.append(p)
    return files


def write_xlsx(results: Iterable[DrawingResult], path: Path, statuses: dict | None = None) -> None:
    results = list(results)
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    summ = []
    for r in results:
        s = dict(r.summary)
        s["status"] = (statuses or {}).get(r.source_file, "ok")
        summ.append(s)
    _sheet(ws, summ, SUMMARY_COLS, flag_col="review_required")
    _attr_sheet(wb.create_sheet("Extraction", 0), [(r.summary, bom_records(r)) for r in results])

    bom = [rec for r in results for rec in bom_records(r)]
    extras = []
    for r in results:
        extras += [c for c in r.bom_columns if c not in BOM_STD and c not in extras]
    bom_cols = ["drawing_number", "item", "part_number", "description", "quantity", "quantity_value",
                "material", "mass", "mass_kg", "remarks"] + extras + ["confidence", "structural_confidence", "flags", "page",
                                                                      "source_file"]
    _sheet(wb.create_sheet("BOM"), bom, bom_cols, flag_col="flags")
    _sheet(wb.create_sheet("Title Block"), [x for r in results for x in title_records(r)],
           ["drawing_number", "field", "value", "normalized", "confidence"])
    _sheet(wb.create_sheet("Material & Specs"), [x for r in results for x in spec_records(r)],
           ["drawing_number", "category", "subtype", "value", "source", "context", "page", "confidence"])
    _sheet(wb.create_sheet("Revisions"), [x for r in results for x in revision_records(r)],
           ["drawing_number", "rev", "description", "date", "date_iso", "approved", "page", "confidence"])
    _sheet(wb.create_sheet("Notes"), [x for r in results for x in note_records(r)],
           ["drawing_number", "page", "number", "text", "confidence"])
    if any(r.dimensions for r in results):
        _sheet(wb.create_sheet("Dimensions"), [x for r in results for x in dimension_records(r)],
               ["drawing_number", "page", "type", "text", "nominal", "tolerance", "prefix", "suffix", "confidence"])
    warn = [{"source_file": Path(r.source_file).name, "warning": w} for r in results for w in r.warnings]
    _sheet(wb.create_sheet("Warnings"), warn, ["source_file", "warning"])
    wb.save(path)


# ---------------------------------------------------------------- styling

_HDR_FILL = PatternFill("solid", fgColor="1F3864")
_HDR_FONT = Font(bold=True, color="FFFFFF")
_FLAG_FILL = PatternFill("solid", fgColor="FFF2CC")
_LOW_FILL = PatternFill("solid", fgColor="F8CBAD")
_THIN = Side(style="thin", color="BFBFBF")
_HEAD_NAMES = {**BOM_HEAD, "quantity_value": "Qty (numeric)", "mass_kg": "Mass (kg)",
               "drawing_number": "Drawing Number", "drawing_title": "Drawing Title",
               "author_date": "Author / Date", "material_callout": "Material Callout",
               "surface_finish": "Surface Finish", "heat_treatment": "Heat Treatment"}


def _sheet(ws, records, cols, flag_col=None, low_conf=0.65):
    ws.append([_HEAD_NAMES.get(c, c.replace("_", " ").title()) for c in cols])
    for c in ws[1]:
        c.fill, c.font = _HDR_FILL, _HDR_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for rec in records:
        ws.append([_cell(rec.get(c)) for c in cols])
        row = ws.max_row
        flagged = flag_col and rec.get(flag_col) not in (None, "", False)
        conf = rec.get("confidence")
        for j, c in enumerate(cols, 1):
            cell = ws.cell(row=row, column=j)
            cell.border = Border(bottom=_THIN)
            cell.alignment = Alignment(vertical="top", wrap_text=c in ("description", "context", "text",
                                                                        "review_reasons", "warning"))
            if flagged:
                cell.fill = _FLAG_FILL
            if c == "confidence" and isinstance(conf, (int, float)) and conf < low_conf:
                cell.fill = _LOW_FILL
    for j, c in enumerate(cols, 1):
        width = max([len(str(ws.cell(row=1, column=j).value))] +
                    [len(str(_cell(r.get(c)) or "")) for r in records[:300]]) + 2
        ws.column_dimensions[get_column_letter(j)].width = min(max(width, 8), 60)
    ws.freeze_panes = "B2" if len(cols) > 3 else "A2"
    if records:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"


def _cell(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return _sanitize_formula(v)


def _columns(records):
    cols = []
    for r in records:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols or ["empty"]


def _default_cols(name, recs):
    if recs:
        return _columns(recs)
    return {"bom": ["drawing_number"] + BOM_STD, "title_block": ["drawing_number", "field", "value"],
            "specs": ["drawing_number", "category", "value"], "revisions": ["drawing_number", "rev"],
            "notes": ["drawing_number", "text"]}[name]


def write_sheets_xlsx(sheets: list[tuple[str, list[dict], list[str], str | None]], target,
                      extraction: list[tuple[dict, list[dict]]] | None = None) -> None:
    """Write pre-built record lists (e.g. after manual corrections in the UI).
    sheets = [(sheet_name, records, columns, flag_column_or_None), ...];
    extraction = [(summary, bom_records), ...] for the attribute-table sheet;
    target = path or binary file-like object."""
    wb = Workbook()
    wb.remove(wb.active)
    if extraction:
        _attr_sheet(wb.create_sheet("Extraction"), extraction)
    for name, records, cols, flag in sheets:
        _sheet(wb.create_sheet(name[:31]), records, cols, flag_col=flag)
    wb.save(target)
