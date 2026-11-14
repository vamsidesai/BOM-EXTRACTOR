"""Tests for independent confidence aggregation and lowest-confidence row review decisions."""
from __future__ import annotations

import pytest

from bomx.models import BomRow, DrawingResult, FieldValue
from bomx.pipeline import build_summary
from bomx.config import DEFAULT_CONFIG


def test_confidence_separation_independent_text_and_structure():
    res = DrawingResult(source_file="dummy.pdf")
    res.title_block = {
        "drawing_number": FieldValue(value="DRG-001", confidence=0.95),
        "drawing_title": FieldValue(value="Test Part", confidence=0.90),
        "revision": FieldValue(value="A", confidence=0.85),
    }
    # 2 rows with high text conf, 1 row with lower structural conf
    res.bom = [
        BomRow(item="1", part_number="P1", description="Part 1", quantity="1",
               confidence=0.98, structural_confidence=1.0),
        BomRow(item="2", part_number="P2", description="Part 2", quantity="2",
               confidence=0.92, structural_confidence=0.80),
    ]

    summary = build_summary(res, DEFAULT_CONFIG)
    assert summary["text_confidence"] is not None
    assert summary["structural_confidence"] == pytest.approx(0.90)
    # text_confidence averages only text sources (0.95, 0.90, 0.85, 0.98, 0.92)
    assert summary["text_confidence"] == pytest.approx((0.95 + 0.90 + 0.85 + 0.98 + 0.92) / 5, abs=1e-3)
    assert summary["mean_confidence"] != summary["text_confidence"]


def test_review_decision_catches_single_bad_row_hidden_by_high_average():
    res = DrawingResult(source_file="dummy.pdf")
    res.title_block = {
        "drawing_number": FieldValue(value="DRG-002", confidence=0.99),
        "drawing_title": FieldValue(value="Flange Assembly", confidence=0.99),
        "revision": FieldValue(value="B", confidence=0.99),
    }
    # 9 rows with perfect structural confidence (1.0), 1 row with low structural confidence (0.40)
    # Average structural confidence is (9*1.0 + 0.40)/10 = 0.94, which is well above low_conf_threshold (0.65)
    rows = [
        BomRow(item=str(i), part_number=f"PN-{i}", description=f"Item {i}", quantity="1",
               confidence=0.95, structural_confidence=1.0)
        for i in range(1, 10)
    ]
    rows.append(
        BomRow(item="10", part_number="PN-10", description="Suspicious Item", quantity="1",
               confidence=0.95, structural_confidence=0.40)
    )
    res.bom = rows

    summary = build_summary(res, DEFAULT_CONFIG)
    # High average must NOT hide the bad row:
    assert summary["structural_confidence"] > DEFAULT_CONFIG["low_conf_threshold"]
    assert summary["min_structural_confidence"] == 0.40
    assert summary["review_required"] is True
    assert "low structural / column assignment confidence on row" in summary["review_reasons"]

