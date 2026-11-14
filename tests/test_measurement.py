"""Tests for the canonical Measurement model preserving original units and nominal values."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from bomx.models import BomRow, Dimension, Measurement  # noqa: E402
from bomx.extract import parse_mass_measurement, parse_quantity_measurement, to_kg  # noqa: E402


def test_mass_measurement_preserves_original_grams():
    val_kg, meas, flags = parse_mass_measurement("250 g")
    assert val_kg == pytest.approx(0.25)
    assert meas is not None
    assert isinstance(meas, Measurement)
    assert meas.raw == "250 g"
    assert meas.nominal == 250.0
    assert meas.unit == "g"
    assert meas.canonical_value == pytest.approx(0.25)
    assert meas.canonical_unit == "kg"
    assert meas.measurement_type == "mass"
    assert to_kg("250 g") == pytest.approx(0.25)


def test_mass_measurement_preserves_original_pounds():
    val_kg, meas, flags = parse_mass_measurement("5 lbs")
    assert val_kg == pytest.approx(5.0 * 0.45359237)
    assert meas is not None
    assert isinstance(meas, Measurement)
    assert meas.nominal == 5.0
    assert meas.unit == "lbs"
    assert meas.canonical_value == pytest.approx(5.0 * 0.45359237)
    assert meas.canonical_unit == "kg"
    assert to_kg("5 lbs") == pytest.approx(5.0 * 0.45359237)


def test_parse_quantity_measurement():
    qty_val, qty_meas, flags = parse_quantity_measurement("12 pcs")
    assert qty_val == 12
    assert qty_meas is not None
    assert isinstance(qty_meas, Measurement)
    assert qty_meas.nominal == 12.0
    assert qty_meas.unit == "pcs"
    assert qty_meas.canonical_unit == "count"


def test_bom_row_preserves_original_mass_measurement():
    row = BomRow(mass="500 g", mass_kg=0.5)
    assert row.mass_measurement is not None
    assert row.mass_measurement.nominal == 500.0
    assert row.mass_measurement.unit == "g"
    assert row.mass_measurement.canonical_value == 0.5
    assert row.mass_measurement.canonical_unit == "kg"


def test_bom_row_preserves_quantity_measurement():
    row = BomRow(quantity="12 pcs", quantity_value=12)
    assert row.quantity_measurement is not None
    assert row.quantity_measurement.nominal == 12.0
    assert row.quantity_measurement.unit == "pcs"
    assert row.quantity_measurement.canonical_value == 12.0
    assert row.quantity_measurement.canonical_unit == "count"


def test_dimension_as_measurement():
    dim = Dimension(text="Ø50 ±0.1", nominal=50.0, tolerance="±0.1", dim_type="diameter")
    assert dim.measurement is not None
    assert dim.measurement.nominal == 50.0
    assert dim.measurement.unit == "mm"
    assert dim.measurement.canonical_unit == "mm"
    assert dim.measurement.measurement_type == "diameter"
    assert dim.as_measurement == dim.measurement


def test_table_to_bom_suspicious_mass_flagged_and_original_text_preserved():
    from bomx.layout import Column, Table, TableCellValue
    from bomx.extract import table_to_bom

    col_item = Column(header="ITEM", key="item", x0=0, x1=50)
    col_mass = Column(header="MASS (KG)", key="mass", x0=50, x1=100, unit="KG")
    t = Table(
        kind="bom",
        columns=[col_item, col_mass],
        rows=[
            {
                "item": TableCellValue(text="1", conf=0.95, bbox=(0, 20, 50, 40)),
                "mass": TableCellValue(text="210 kg", conf=0.90, bbox=(50, 20, 100, 40)),
            },
            {
                "item": TableCellValue(text="2", conf=0.95, bbox=(0, 40, 50, 60)),
                "mass": TableCellValue(text="2:10 kg", conf=0.88, bbox=(50, 40, 100, 60)),
            },
        ],
        row_bboxes=[(0, 20, 100, 40), (0, 40, 100, 60)],
        bbox=(0, 0, 100, 60),
        header_bbox=(0, 0, 100, 20),
    )

    rows, warns = table_to_bom(t, page=1, low_conf=0.65)
    assert len(rows) == 2

    # Row 1: "210 kg" is preserved as exact original OCR text, but flagged as ambiguous
    assert rows[0].mass == "210 kg"
    assert "mass_decimal_ambiguous" in rows[0].flags
    assert rows[0].mass_kg is None
    assert rows[0].mass_measurement is None

    # Row 2: "2:10 kg" separator confusion: preserved as exact original OCR text and flagged as ambiguous
    assert rows[1].mass == "2:10 kg"
    assert rows[1].mass_kg is None
    assert rows[1].mass_measurement is None
    assert rows[1].mass_candidate == pytest.approx(2.10)
    assert "mass_decimal_ambiguous" in rows[1].flags


