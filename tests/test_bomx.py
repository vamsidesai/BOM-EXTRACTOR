"""Test suite. Generates sample drawings once per session, then checks
extraction accuracy, exports, edge cases and the CLI.

    pytest -q tests/
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bomx import extract  # noqa: E402
from bomx.cli import main as cli_main  # noqa: E402
from bomx.extract import parse_date, to_kg  # noqa: E402
from bomx.specs import find_specs  # noqa: E402
import evaluate  # noqa: E402
import make_samples  # noqa: E402


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    make_samples.main(str(d))
    return d


@pytest.fixture(scope="session")
def truth(samples):
    return {t["file"]: t for t in json.loads((samples / "ground_truth.json").read_text())}


# ------------------------------------------------------------------ unit tests

@pytest.mark.parametrize("text,iso", [
    ("2024-08-15", "2024-08-15"), ("15/08/2024", "2024-08-15"), ("08/15/2024", "2024-08-15"),
    ("05 AUG 2024", "2024-08-05"), ("03-JUN-2023", "2023-06-03"), ("Aug 15, 2024", "2024-08-15"),
    ("12.09.25", "2025-09-12"), ("not a date", None)])
def test_parse_date(text, iso):
    assert parse_date(text) == iso


def test_mass_units():
    assert to_kg("1.45 kg") == 1.45
    assert to_kg("1450 g") == pytest.approx(1.45)
    assert to_kg("2 lb") == pytest.approx(0.907, abs=1e-3)
    assert to_kg("0.5", default_unit="KG") == 0.5


@pytest.mark.parametrize("text,cat,value", [
    ("MATERIAL: ASTM A36 STRUCTURAL STEEL", "material", "ASTM A36 STRUCTURAL STEEL"),
    ("Stainless Steel 316L", "material", "STAINLESS STEEL 316L"),
    ("SS304", "material", "STAINLESS STEEL 304"),
    ("AL 6061-T6", "material", "ALUMINIUM 6061-T6"),
    ("EN8", "material", "EN8"),
    ("ANODIZED CLEAR", "surface_finish", "ANODIZED CLEAR"),
    ("SURFACE ROUGHNESS Ra 1.6 um", "surface_finish", "Ra 1.6 µm"),
    ("QUENCHED & TEMPERED TO 55 HRC", "heat_treatment", "QUENCHED & TEMPERED"),
    ("QUENCHED & TEMPERED TO 55 HRC", "heat_treatment", "55 HRC"),
    ("CASE CARBURIZED, CASE DEPTH 0.8-1.2 MM", "heat_treatment", "CASE CARBURIZED, CASE DEPTH 0.8-1.2 MM"),
    ("TOLERANCES PER ISO 2768-mK", "standard", "ISO 2768-mK"),
])
def test_spec_patterns(text, cat, value):
    vals = [s.value for s in find_specs(text, "notes") if s.category == cat]
    assert value in vals, vals


def test_no_false_material_in_plain_text():
    assert not [s for s in find_specs("REMOVE ALL BURRS. DIMENSIONS IN MM.", "notes")
                if s.category == "material"]


# ------------------------------------------------------------------ accuracy

NATIVE = ["drawing1_shaft_assembly", "drawing2_pivot_bracket", "drawing3_lineless_bom"]
SCANS = ["drawing1_scan_skewed", "drawing2_scan_rotated", "drawing4_scanned_two_sheets"]
EXT = {"drawing1_scan_skewed": ".tif", "drawing2_scan_rotated": ".png"}


def _run(samples, name):
    f = samples / f"{name}{EXT.get(name, '.pdf')}"
    return extract(f)


@pytest.mark.parametrize("name", NATIVE)
def test_native_pdf_exact(samples, truth, name):
    res = _run(samples, name)
    assert {p.source for p in res.pages} == {"native"}
    sc = evaluate.score(truth[name], json.loads(json.dumps(res.to_dict(), default=str)))
    assert sc["accuracy"] == 1.0, sc["failures"]


@pytest.mark.parametrize("name", SCANS)
def test_scanned_accuracy(samples, truth, name):
    res = _run(samples, name)
    assert {p.source for p in res.pages} == {"ocr"}
    sc = evaluate.score(truth[name], json.loads(json.dumps(res.to_dict(), default=str)))
    assert sc["accuracy"] >= 0.95, sc["failures"]


def test_sow_sample_values(samples):
    """The exact example outputs listed in the SOW attribute table."""
    s = _run(samples, "drawing1_shaft_assembly").summary
    assert s["drawing_number"] == "DWG-2026-8891-R2"
    assert s["drawing_title"] == "MAIN DRIVE SHAFT ASSEMBLY"
    assert s["revision"] == "C"
    assert s["author_date"] == "J. DOE / 2024-08-15"
    assert "ASTM A36" in s["material_callout"] and "STRUCTURAL STEEL" in s["material_callout"]
    assert "ANODIZED CLEAR" in s["surface_finish"] and "Ra 1.6" in s["surface_finish"]
    assert "QUENCHED & TEMPERED" in s["heat_treatment"] and "55 HRC" in s["heat_treatment"]
    assert s["projection"] == "THIRD ANGLE" and s["scale"] == "1:2"


def test_bom_normalisation(samples):
    res = _run(samples, "drawing1_shaft_assembly")
    r1 = res.bom[0]
    assert (r1.item, r1.part_number, r1.description) == ("01", "PN-4402-A", "HEX HEAD BOLT M12x50")
    assert r1.quantity_value == 4 and r1.mass_kg == pytest.approx(0.06)
    assert [r.item for r in res.bom] == [f"{i:02d}" for i in range(1, 9)]  # bottom-header BOM reordered
    assert res.summary["bom_total_quantity"] == 18
    assert [r.rev for r in res.revisions] == ["A", "B", "C"]


def test_multipage_bom_has_page_numbers(samples):
    res = _run(samples, "drawing4_scanned_two_sheets")
    assert len(res.pages) == 2
    assert {r.page for r in res.bom} == {1, 2}


# ------------------------------------------------------------------ outputs & CLI

def test_cli_batch_outputs(samples, tmp_path):
    out = tmp_path / "out"
    files = [str(samples / "drawing1_shaft_assembly.pdf"), str(samples / "drawing3_lineless_bom.pdf")]
    assert cli_main(["extract", *files, "-o", str(out)]) == 0
    d1 = out / "drawing1_shaft_assembly"
    for suffix in (".json", ".xlsx", "_bom.csv", "_title_block.csv", "_specs.csv", "_revisions.csv",
                   "_notes.csv", "_p1_overlay.png"):
        assert (d1 / f"drawing1_shaft_assembly{suffix}").exists(), suffix
    assert not (out / "consolidated.xlsx").exists()  # one Excel per drawing, never merged
    for f in ("consolidated_bom.csv", "consolidated_summary.csv", "batch_report.json"):
        assert (out / f).exists(), f

    wb = load_workbook(d1 / "drawing1_shaft_assembly.xlsx")
    assert wb.sheetnames == ["Extraction", "Summary", "BOM", "Title Block", "Material & Specs", "Revisions", "Notes",
                             "Warnings"]
    assert wb["BOM"].max_row == 1 + 8  # only this drawing's rows
    with open(out / "consolidated_bom.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["part_number"] == "PN-4402-A" and rows[0]["drawing_number"] == "DWG-2026-8891-R2"
    rep = json.loads((out / "batch_report.json").read_text())
    assert rep["files"] == 2 and rep["errors"] == 0


def test_cli_formats_and_config(samples, tmp_path):
    cfg = tmp_path / "vocab.yaml"
    assert cli_main(["dump-config", str(cfg)]) == 0
    out = tmp_path / "o"
    assert cli_main(["extract", str(samples / "drawing2_pivot_bracket.pdf"), "-o", str(out),
                     "-f", "json", "-c", str(cfg), "--no-overlay"]) == 0
    assert (out / "drawing2_pivot_bracket.json").exists()
    assert not (out / "drawing2_pivot_bracket.xlsx").exists()


# ------------------------------------------------------------------ robustness

def test_blank_and_corrupt_inputs(tmp_path):
    blank = tmp_path / "blank.png"
    from PIL import Image
    Image.fromarray(np.full((1200, 1700), 255, np.uint8)).save(blank, dpi=(150, 150))
    res = extract(blank)
    assert res.bom == [] and res.summary["review_required"]

    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(tmp_path / "empty.pdf"))
    res = extract(tmp_path / "empty.pdf")
    assert res.bom == []

    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4 garbage")
    out = tmp_path / "out"
    rc = cli_main(["extract", str(bad), str(blank), "-o", str(out), "--no-overlay"])
    rep = json.loads((out / "batch_report.json").read_text())
    assert rep["errors"] == 1 and rc == 0  # batch continues past the bad file


def test_ui_end_to_end(samples, tmp_path):
    """Run the Streamlit UI headlessly: extract a folder, open a drawing, verify it."""
    st_testing = pytest.importorskip("streamlit.testing.v1")
    import shutil
    d = tmp_path / "in"
    d.mkdir()
    shutil.copy(samples / "drawing1_shaft_assembly.pdf", d)
    (d / "broken.pdf").write_bytes(b"%PDF-1.4 junk")
    at = st_testing.AppTest.from_file(str(ROOT / "bomx" / "ui_app.py"), default_timeout=300)
    at.run()
    at.sidebar.text_input[0].set_value(str(d)).run()
    at.sidebar.button[0].click().run()
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Drawings"] == "2" and m["Errors ❌"] == "1" and m["BOM rows"] == "8"
    key = [k for k in at.session_state.results if "drawing1" in k][0]
    at.selectbox[0].set_value(key).run()
    at.toggle[0].set_value(True).run()
    assert not at.exception
    assert {x.label: x.value for x in at.metric}["Verified ✅"] == "1"


GEARBOX = Path(__file__).parent / "data" / "gearbox_casing_legacy.png"


@pytest.mark.skipif(not GEARBOX.exists(), reason="legacy sample not present")
def test_legacy_gearbox_drawing_exact():
    """Raster legacy drawing with 96-dpi screen metadata, hand-drawn style
    tables whose rules stop short, combined DRAWN BY / DATE label and an
    underlined TECHNICAL NOTES heading."""
    from bomx.config import load_config
    from bomx.export import attribute_records, bom_records
    from bomx.pipeline import process_file
    res = process_file(GEARBOX, load_config())
    got = {r["target_field_name"]: r["extracted_output"]
           for r in attribute_records(res.summary, bom_records(res))}
    assert got == {
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
    assert not res.summary["review_required"]
    assert [n["text"] for n in res.notes][-2:] == ["UNLESS OTHERWISE SPECIFIED, DIMENSIONS ARE IN MM",
                                                   "REMOVE ALL BURRS AND SHARP EDGES"]


# ------------------------------------------------------------------ regression tests

def test_title_block_with_rev_drawn_by_date_not_detected_as_revision_table():
    """Case 1: A title block with REV, DRAWN BY, and DATE must not be detected as a revision table."""
    from bomx.layout import _is_header
    # REV, DATE, and DRAWN BY (which maps to approved)
    flds = {"rev", "date", "approved"}
    assert not _is_header(flds, "revision")
    # Even when combined with scale and sheet
    assert not _is_header({"rev", "date", "approved", "scale", "sheet"}, "revision")


def test_revision_row_without_identifier_discarded():
    """Case 2: A revision row with an empty rev and only approved populated must be discarded."""
    from bomx.extract import table_to_revisions
    from bomx.layout import Column, Table, TableCellValue

    col_rev = Column(header="REV", key="rev", x0=0, x1=50)
    col_app = Column(header="APPROVED", key="approved", x0=50, x1=200)
    t = Table(
        kind="revision",
        columns=[col_rev, col_app],
        rows=[
            {
                "rev": TableCellValue(text="", conf=0.9),
                "approved": TableCellValue(text="J. DOE / 2024-08-15", conf=0.95),
            }
        ],
        row_bboxes=[(0, 20, 200, 40)],
        bbox=(0, 0, 200, 40),
        header_bbox=(0, 0, 200, 20),
    )
    rows = table_to_revisions(t, page=1, date_order="dmy")
    assert len(rows) == 0


def test_genuine_revision_row_extracted():
    """Case 3: A genuine revision row with rev, description, and date must still be extracted."""
    from bomx.layout import _is_header, Column, Table, TableCellValue
    from bomx.extract import table_to_revisions

    assert _is_header({"rev", "description", "date"}, "revision")
    assert _is_header({"rev", "ecn", "date"}, "revision")

    col_rev = Column(header="REV", key="rev", x0=0, x1=40)
    col_desc = Column(header="DESCRIPTION", key="description", x0=40, x1=200)
    col_date = Column(header="DATE", key="date", x0=200, x1=300)
    col_app = Column(header="APPROVED", key="approved", x0=300, x1=400)
    t = Table(
        kind="revision",
        columns=[col_rev, col_desc, col_date, col_app],
        rows=[
            {
                "rev": TableCellValue(text="1", conf=0.95),
                "description": TableCellValue(text="INITIAL RELEASE", conf=0.95),
                "date": TableCellValue(text="15/08/2024", conf=0.95),
                "approved": TableCellValue(text="R. KUMAR", conf=0.95),
            }
        ],
        row_bboxes=[(0, 20, 400, 40)],
        bbox=(0, 0, 400, 40),
        header_bbox=(0, 0, 400, 20),
    )
    rows = table_to_revisions(t, page=1, date_order="dmy")
    assert len(rows) == 1
    assert rows[0].rev == "1"
    assert rows[0].description == "INITIAL RELEASE"
    assert rows[0].date == "15/08/2024"
    assert rows[0].extra.get("date_iso") == "2024-08-15"
    assert rows[0].approved == "R. KUMAR"


def test_combined_drawn_by_date_field_populates_author_and_date():
    """Case 4: A combined DRAWN BY / DATE field must populate both author and date."""
    from bomx.extract import parse_title_block
    from bomx.models import Cell, Word
    from bomx.config import DEFAULT_CONFIG

    words = [
        Word("DRAWN", 0, 0, 40, 15, 0.95),
        Word("BY", 42, 0, 60, 15, 0.95),
        Word("/", 62, 0, 68, 15, 0.95),
        Word("DATE:", 70, 0, 100, 15, 0.95),
        Word("J.", 105, 0, 115, 15, 0.95),
        Word("DOE", 118, 0, 140, 15, 0.95),
        Word("/", 142, 0, 148, 15, 0.95),
        Word("2024-08-15", 150, 0, 220, 15, 0.95),
    ]
    cell = Cell(0, 0, 220, 15, words=words, id=1)
    tb = parse_title_block([cell], DEFAULT_CONFIG["title_labels"], 300.0, "")
    assert tb.get("drawn_by") is not None
    assert tb["drawn_by"].value == "J. DOE"
    assert tb.get("date") is not None
    assert tb["date"].value == "2024-08-15" or tb["date"].normalized == "2024-08-15"


def test_reduction_gearbox_screenshot_regression_fixture():
    """Regression fixture matching the screenshot's drawing:
    drawing_number: DWG-2026-8895-R2
    drawing_title: REDUCTION GEARBOX SHAFT ASSEMBLY
    revision: 1
    drawn_by: J. DOE
    date: 2024-08-15
    revisions: No author/date-only row
    """
    from bomx.extract import parse_title_block, table_to_revisions
    from bomx.layout import Column, Table, TableCellValue, title_block_cells
    from bomx.models import Cell, Word
    from bomx.config import DEFAULT_CONFIG

    c_title = Cell(300, 500, 600, 530, words=[
        Word("REDUCTION", 305, 505, 380, 525, 0.95),
        Word("GEARBOX", 385, 505, 460, 525, 0.95),
        Word("SHAFT", 465, 505, 520, 525, 0.95),
        Word("ASSEMBLY", 525, 505, 595, 525, 0.95),
    ], id=1)
    c_dwg = Cell(300, 530, 520, 560, words=[
        Word("DRAWING", 305, 535, 360, 555, 0.95),
        Word("NO:", 365, 535, 385, 555, 0.95),
        Word("DWG-2026-8895-R2", 390, 535, 515, 555, 0.95),
    ], id=2)
    c_rev = Cell(520, 530, 600, 560, words=[
        Word("REV:", 525, 535, 555, 555, 0.95),
        Word("1", 565, 535, 580, 555, 0.95),
    ], id=3)
    c_drawn = Cell(300, 560, 480, 580, words=[
        Word("DRAWN", 305, 565, 340, 575, 0.95),
        Word("BY", 342, 565, 355, 575, 0.95),
        Word("/", 357, 565, 362, 575, 0.95),
        Word("DATE:", 364, 565, 395, 575, 0.95),
        Word("J.", 398, 565, 408, 575, 0.95),
        Word("DOE", 410, 565, 430, 575, 0.95),
        Word("/", 432, 565, 437, 575, 0.95),
        Word("2024-08-15", 440, 565, 478, 575, 0.95),
    ], id=4)
    c_scale = Cell(480, 560, 540, 580, words=[
        Word("SCALE:", 485, 565, 520, 575, 0.95),
        Word("1:1", 522, 565, 538, 575, 0.95),
    ], id=5)
    c_sheet = Cell(540, 560, 600, 580, words=[
        Word("SHEET:", 545, 565, 575, 575, 0.95),
        Word("1", 578, 565, 583, 575, 0.95),
        Word("OF", 585, 565, 592, 575, 0.95),
        Word("1", 594, 565, 598, 575, 0.95),
    ], id=6)

    tb_group = [c_title, c_dwg, c_rev, c_drawn, c_scale, c_sheet]
    selected_cells = title_block_cells([tb_group], used=set(), title_vocab=DEFAULT_CONFIG["title_labels"])
    assert len(selected_cells) == len(tb_group)

    tb = parse_title_block(selected_cells, DEFAULT_CONFIG["title_labels"], 300.0, "")
    assert tb.get("drawing_number") is not None
    assert tb["drawing_number"].value == "DWG-2026-8895-R2"
    assert tb.get("drawing_title") is not None
    assert tb["drawing_title"].value == "REDUCTION GEARBOX SHAFT ASSEMBLY"
    assert tb.get("revision") is not None
    assert tb["revision"].value == "1"
    assert tb["revision"].normalized == "1"  # explicitly 1, not R2
    assert tb.get("drawn_by") is not None
    assert tb["drawn_by"].value == "J. DOE"
    assert tb.get("date") is not None
    assert tb["date"].value == "2024-08-15" or tb["date"].normalized == "2024-08-15"

    rev_cols = [
        Column(header="DRAWN BY / DATE", key="approved", x0=300, x1=480),
        Column(header="SCALE", key="scale", x0=480, x1=540),
        Column(header="SHEET", key="sheet", x0=540, x1=600),
    ]
    rev_table = Table(
        kind="revision",
        columns=rev_cols,
        rows=[{"approved": TableCellValue("J. DOE / 2024-08-15", 0.95)}],
        row_bboxes=[(300, 560, 600, 580)],
        bbox=(300, 560, 600, 580),
        header_bbox=(300, 560, 600, 570),
    )
    revs = table_to_revisions(rev_table, page=1, date_order="dmy")
    assert len(revs) == 0  # No author/date-only row in revisions

