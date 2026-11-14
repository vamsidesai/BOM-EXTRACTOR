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
