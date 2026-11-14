"""2D CAD (DXF / DWG) and scanned-PDF tests.

    pytest -q tests/test_cad.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bomx.cad import dwg_backends  # noqa: E402
from bomx.config import load_config  # noqa: E402
from bomx.export import attribute_records, bom_records, write_json  # noqa: E402
from bomx.pipeline import process_file  # noqa: E402
import evaluate  # noqa: E402
import make_cad_samples  # noqa: E402

DATA = Path(__file__).parent / "data"
LEGACY = DATA / "legacy"
GEARBOX_PNG = DATA / "gearbox_casing_legacy.png"

# what a person reads on the gearbox drawing (tests/data/gearbox_casing_legacy.png and
# the legacy PDF / DWG versions of it)
GEARBOX = {
    "Drawing Number": "DWG-2026-8893-R2",
    "Drawing Title": "GEARBOX CASING ASSEMBLY",
    "Revision Level": "REV A",
    "Author / Date": "J. DOE / 2024-08-15",
    "Item Number": "01\n02\n03\n04\n05\n06",
    "Part Number": "PN-5511-A\nPN-5511-B\nPN-5511-C\nPN-5511-D\nPN-5511-E\nPN-5511-F",
    "Part Description": "LOWER CASING\nUPPER CASING\nCASING GASKET\nHEX HEAD BOLT M10x45\n"
                        "DOWEL PIN D10\nDRAIN PLUG G3/8",
    "Quantity": "1\n1\n1\n12\n2\n1",
    "Material Grade": "Cast Iron ASTM A48\nCast iron ASTM A48\nNitrile/Cork\nCarbon Steel Gr 8.8\n"
                      "Hardened Steel\nBrass",
    "Mass / Weight": "12.40 kg\n9.80 kg\n0.05 kg\n0.05 kg\n0.02 kg\n0.03 kg",
    "Material Callout": "REFER TO BOM FOR MATERIALS",
    "Surface Finish": "MACHINED SEATS / Ra 1.6 um, UNMACHINED CAST / Ra 6.3 um",
    "Heat Treatment": "STRESS RELIEVE CASTINGS BEFORE FINAL MACHINING",
}


def _attrs(res) -> dict:
    return {r["target_field_name"]: r["extracted_output"]
            for r in attribute_records(res.summary, bom_records(res))}


def _tesseract():
    from bomx.imaging import find_tesseract, tesseract_available
    find_tesseract(None)
    return tesseract_available()


needs_ocr = pytest.mark.skipif(not _tesseract(), reason="Tesseract not installed")


# ------------------------------------------------------------------ native CAD

@pytest.fixture(scope="module")
def cad_samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("cad")
    make_cad_samples.main(str(d))
    return d


def _as_json(res, tmp: Path) -> dict:
    p = tmp / "r.json"
    write_json(res, p)
    return json.loads(p.read_text())


def test_native_cad_samples_exact(cad_samples, tmp_path):
    """DXF with real text entities: TEXT in model space; MTEXT on a paper-space
    sheet with a model-space detail viewport and a far-away stray object;
    an inch drawing whose title block holds its values only as block
    attributes and whose BOM is a block. Text comes from the CAD entities, so
    every field must be exact and no OCR is used."""
    truths = json.loads((cad_samples / "ground_truth.json").read_text())
    cfg = load_config()
    for t in truths:
        path = next(cad_samples.glob(t["file"] + ".*"))
        res = process_file(path, cfg)
        assert {p.source for p in res.pages} == {"native"}, t["file"]
        scored = evaluate.score(t, _as_json(res, tmp_path))
        assert scored["passed"] == scored["checks"], (t["file"], scored["failures"])
        assert not res.summary["review_required"], (t["file"], res.summary["review_reasons"])


def test_paper_space_layout_and_viewport_text(cad_samples):
    res = process_file(cad_samples / "cad2_pivot_bracket.dxf", load_config())
    assert res.pages[0].layout == "A3 SHEET"
    assert res.pages[0].kind == "dxf"
    # text seen through the viewport is captured, at the right place on the sheet
    from bomx.ingest import iter_pages
    cfg = load_config()
    page = next(iter_pages(cad_samples / "cad2_pivot_bracket.dxf", cfg["dpi"], cfg["max_pixels"],
                           False, 15, cfg))
    det = [w for w in page.native_words if w.text in ("DETAIL", "B")]
    assert len(det) == 2
    h, w = page.image.shape[:2]
    assert all(0.1 * w < x.cx < 0.5 * w and 0.6 * h < x.cy < 0.95 * h for x in det)


def test_attribute_title_block(cad_samples):
    res = process_file(cad_samples / "cad3_attribute_titleblock.dxf", load_config())
    tb = res.title_block
    assert tb["drawing_number"].value == "HX-7710-03" and tb["drawing_number"].confidence == 1.0
    assert tb["date"].normalized == "2025-02-11"
    assert tb["scale"].normalized == "2:1"


def test_cad_model_vs_all_layouts(cad_samples):
    cfg = load_config(overrides={"cad_layouts": "all"})
    res = process_file(cad_samples / "cad2_pivot_bracket.dxf", cfg)
    assert [p.layout for p in res.pages] == ["Model", "A3 SHEET"]


def test_broken_dxf_reports_error(tmp_path):
    bad = tmp_path / "broken.dxf"
    bad.write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n")
    from bomx.cli import main as cli_main
    out = tmp_path / "out"
    assert cli_main(["extract", str(bad), "-o", str(out), "--no-overlay", "-f", "json"]) == 1
    rep = json.loads((out / "batch_report.json").read_text())
    assert rep["errors"] == 1  # reported, not crashed


# ------------------------------------------------------------------ traced CAD

def _trace_to_dxf(png: Path, out: Path) -> None:
    """Raster -> vector trace, like legacy conversions: every glyph and line
    becomes closed outline polylines, no text entities at all."""
    import ezdxf
    g = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    b = (g < 140).astype(np.uint8)
    contours, _ = cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    doc = ezdxf.new("R2000")
    msp = doc.modelspace()
    H = g.shape[0]
    for c in contours:
        if len(c) < 3:
            continue
        pts = [(float(x), float(H - y)) for x, y in c[:, 0, :]]
        msp.add_lwpolyline(pts, close=True)
    doc.saveas(out)


@needs_ocr
def test_traced_dxf_from_scan(tmp_path):
    """A drawing traced to outlines (no text entities) is detected, rendered
    filled and read with OCR. This crude trace (thresholded contours of an
    anti-aliased PNG) breaks the thin table rules, so damaged BOM rows must be
    flagged for review - exact BOM values are checked on the real legacy files."""
    dxf = tmp_path / "gearbox_traced.dxf"
    _trace_to_dxf(GEARBOX_PNG, dxf)
    res = process_file(dxf, load_config())
    assert res.pages[0].kind == "dxf-traced" and res.pages[0].source == "ocr"
    got = _attrs(res)
    for k in ("Drawing Number", "Drawing Title", "Material Callout", "Surface Finish", "Heat Treatment"):
        assert got[k] == GEARBOX[k], k
    assert res.summary["review_required"]


# ------------------------------------------------------------------ scanned PDF

@needs_ocr
def test_scanned_pdf_uses_scan_resolution(tmp_path):
    """An image-only PDF whose page size says nothing about the drawing's
    real size (here a 96-dpi scan on a 25-inch page) must read like the image."""
    pdf = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=1800, height=1269)
    page.insert_image(page.rect, filename=str(GEARBOX_PNG))
    doc.save(pdf)
    res = process_file(pdf, load_config())
    assert res.pages[0].kind == "pdf-scan"
    assert _attrs(res) == GEARBOX
    assert not res.summary["review_required"]


# ------------------------------------------------------------------ your legacy drawings

@needs_ocr
@pytest.mark.skipif(not (LEGACY / "legacy_drawing_4.pdf").exists(), reason="legacy sample absent")
def test_legacy_scanned_pdf():
    res = process_file(LEGACY / "legacy_drawing_4.pdf", load_config())
    assert _attrs(res) == GEARBOX
    assert not res.summary["review_required"]


@needs_ocr
@pytest.mark.skipif(not (LEGACY / "legacy_3.dwg").exists(), reason="legacy sample absent")
@pytest.mark.skipif(not any(dwg_backends().values()), reason="no DWG converter installed")
def test_legacy_traced_dwg():
    """R14 DWG of the gearbox traced to 2 794 outline polylines (LibreDWG's DXF
    writer drops most of them; they are restored from its JSON dump). The
    trace destroyed the revision letter, so revision must be flagged, not guessed."""
    res = process_file(LEGACY / "legacy_3.dwg", load_config())
    assert res.pages[0].kind == "dwg-traced"
    got = _attrs(res)
    expected = dict(GEARBOX, **{"Revision Level": None})
    assert got == expected
    assert res.summary["review_required"] and "missing revision" in res.summary["review_reasons"]


@needs_ocr
@pytest.mark.skipif(not (LEGACY / "legacy_1.dxf").exists(), reason="legacy sample absent")
def test_legacy_traced_dxf():
    res = process_file(LEGACY / "legacy_1.dxf", load_config())
    assert res.pages[0].kind == "dxf-traced"
    got = _attrs(res)
    assert got["Drawing Number"] == "PMA-ASSY-001"
    assert got["Drawing Title"] == "CENTRIFUGAL PUMP & MOTOR ASSEMBLY"
    assert got["Revision Level"] == "REV B"
    assert got["Author / Date"] == "J. Smith / 2023-10-15"
    assert got["Part Number"].split("\n") == [
        "CP-32-150", "EM-132S-4", "FC-200-38", "CG-PMA-01", "BP-PMA-101", "MS-P-38", "ISO-M16-150",
        "ISO-4014-M12", "ISO-4014-M16", "Gasket-F"]
    assert got["Part Description"].split("\n") == [
        "Centrifugal Pump", "Electric Motor 7.5kW", "Flexible Shaft Coupling", "Coupling Guard",
        "Fabricated Baseplate", "Mechanical Seal", "Foundation Bolt M16", "Motor Mounting Bolt",
        "Pump Mounting Bolt", "Flange Gasket"]
    assert got["Quantity"].split("\n") == ["1", "1", "1", "1", "1", "1", "6", "4", "4", "2"]
    assert got["Material Grade"].split("\n") == [
        "Cast Iron FG260 / SS304", "Cast Iron / Steel", "Cast Iron & Rubber", "Mild Steel IS 2062",
        "Structural Steel A36", "Carbon/Ceramic/Vit", "Mild Steel", "Grade 8.8 Steel",
        "Grade 8.8 Steel", "Non-Asbestos"]
    assert got["Mass / Weight"].split("\n") == [
        "145.0 kg", "85.0 kg", "6.5 kg", "4.2 kg", "62.0 kg", "1.8 kg", "0.85 kg", "0.08 kg",
        "0.15 kg", "0.05 kg"]
    assert got["Material Callout"] == "As indicated in BOM"
    assert got["Surface Finish"].startswith("Prime and paint external surfaces (Aqua Blue/RAL 5021)")
    assert [(r.rev, r.description) for r in res.revisions] == [
        ("A", "Initial Release"), ("B", "Baseplate mounting holes revised")]
    assert len(res.notes) == 8


# ------------------------------------------------------------------ units

def test_dwg_json_supplement_restores_dropped_geometry():
    import ezdxf
    from bomx.dwgjson import supplement
    doc = ezdxf.new("R2000")
    msp = doc.modelspace()
    kept = msp.add_line((0, 0), (10, 0))
    h = int(kept.dxf.handle, 16)
    layer0 = int(doc.layers.get("0").dxf.handle, 16)
    data = {"OBJECTS": [
        {"entity": "", "type": 19, "handle": [0, 1, h], "entmode": 2, "layer": [5, 1, layer0, layer0],
         "start": [0, 0, 0], "end": [10, 0, 0]},  # present in the DXF already
        {"entity": "", "type": 77, "handle": [0, 2, 0x7001], "entmode": 2, "_subclass": "AcDbPolyline",
         "flag": 528, "points": [[0, 0], [10, 0], [10, 10]], "bulges": [0, 0.5, 0]},
        {"entity": "", "type": 17, "handle": [0, 2, 0x7002], "entmode": 2, "center": [5, 5, 0],
         "radius": 2.0, "start_angle": 0.0, "end_angle": 3.14159},
        # a damaged file reusing the line's handle for a different polyline
        {"entity": "LWPOLYLINE", "type": 511, "handle": [0, 1, h], "entmode": 2,
         "flag": 512, "points": [[50, 50], [60, 50], [60, 60]], "bulges": []},
        {"entity": "", "type": 1, "handle": [0, 2, 0x7003], "entmode": 2, "text_value": ""},
    ]}
    st = supplement(doc, data)
    assert st["added"] == 3 and st["text_lost"] == 1
    pls = list(msp.query("LWPOLYLINE"))
    assert len(pls) == 2 and all(p.closed for p in pls)
    assert any(abs(b - 0.5) < 1e-9 for p in pls for *_, b in p.get_points("xyseb"))
    arc = msp.query("ARC").first
    assert abs(arc.dxf.end_angle - 180.0) < 0.01


def test_ocr_confusion_fixes_are_conservative():
    from bomx.textutil import fix_ocr_confusions as f
    assert f("HEX HEAD BOLT M10x4S") == "HEX HEAD BOLT M10x45"
    assert f("Electric Motor 7.SkW") == "Electric Motor 7.5kW"
    assert f("Grade B.8 Steel") == "Grade 8.8 Steel"
    assert f("4.2 kq") == "4.2 kg"
    assert f("1SO-4014-M12") == "ISO-4014-M12"
    assert f("RAL S021") == "RAL 5021"
    for keep in ("PN-5511-B", "EM-132S-4", "SS304", "IS 2062", "AL 6061-T6", "Section A-A",
                 "Gasket-F", "QG-BS-104", "M12x50", "Rev B"):
        assert f(keep) == keep


def test_dashed_rule_repair_only_extends_found_rules():
    from bomx.imaging import bridge_dashed_rules
    dpi = 300
    img = np.zeros((400, 1200), np.uint8)
    img[50:53, 100:1100] = 255  # full rule
    img[100:400, 100:103] = 255
    img[100:400, 1097:1100] = 255
    img[200:203, 100:600] = 255  # a rule found in part ...
    for x in range(620, 1100, 40):  # ... continuing as dashes
        img[200:203, x:x + 20] = 255
    for x in range(110, 1090, 40):  # a rule that survives only as specks
        img[300:303, x:x + 12] = 255
    out, specks = bridge_dashed_rules(img, dpi)
    assert out[201, 610] and out[201, 1050]  # repaired
    assert not out[301, 130]  # not invented
    assert specks[301, 115]  # specks marked for removal before OCR


def test_table_open_at_sheet_edge_is_closed():
    """A parts list running to the sheet edge has no right border: its rules
    all end at the same x. The missing rule is added - but rules of separate
    tables far apart that happen to end at the same x are not joined."""
    from bomx.imaging import close_open_table_sides
    dpi = 300
    hm = np.zeros((2000, 1500), np.uint8)
    vm = np.zeros_like(hm)
    for y in range(100, 500, 60):  # BOM rows, open on the right at x=1400
        hm[y:y + 3, 600:1400] = 255
    vm[100:463, 600:603] = 255
    for y in range(1700, 1950, 60):  # title block far below, closed by its own rule
        hm[y:y + 3, 900:1400] = 255
    vm[1700:1883, 1397:1400] = 255
    _, v2 = close_open_table_sides(hm, vm, dpi)
    assert v2[300, 1398]  # BOM closed
    assert not v2[1000, 1398]  # nothing drawn between the two tables
