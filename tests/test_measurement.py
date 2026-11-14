"""Tests for the canonical Measurement model preserving original units and nominal values."""
from __future__ import annotations

import pytest

from bomx.models import BomRow, Dimension, Measurement
from bomx.extract import parse_mass_measurement, parse_quantity_measurement, to_kg


def test_mass_measurement_preserves_original_grams():
    val_kg, meas, flags = parse_mass_measurement("250 g")
    assert val_kg == pytest.approx(0.25)
    assert meas is not None
    assert meas.raw == "250 g"
    assert meas.nominal == 250.0
    assert meas.unit == "g"
    assert meas.canonical_value == pytest.approx(0.25)
    assert meas.canonical_unit == "kg"
    assert meas.measurement_type == "mass"


def test_mass_measurement_preserves_original_pounds():
    val_kg, meas, flags = parse_mass_measurement("5 lbs")
    assert val_kg == pytest.approx(5.0 * 0.45359237)
    assert meas is not None
    assert meas.nominal == 5.0
    assert meas.unit == "lbs"
    assert meas.canonical_value == pytest.approx(5.0 * 0.45359237)
    assert meas.canonical_unit == "kg"


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

