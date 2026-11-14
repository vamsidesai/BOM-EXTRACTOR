"""Tests for configuration validation and loading, including malformed YAML handling."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from bomx.config import DEFAULT_CONFIG, load_config, validate_config  # noqa: E402


def test_default_config_valid():
    cfg = validate_config(DEFAULT_CONFIG.copy())
    assert cfg["dpi"] == 300
    assert cfg["date_order"] == "dmy"


def test_reject_unknown_keys():
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["unknown_custom_key"] = 123
    with pytest.raises(ValueError, match="Unknown configuration key"):
        validate_config(bad_cfg)


@pytest.mark.parametrize("dpi_val", [20, 2000, "300", True, None])
def test_invalid_dpi(dpi_val):
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["dpi"] = dpi_val
    with pytest.raises(ValueError, match="dpi"):
        validate_config(bad_cfg)


@pytest.mark.parametrize("date_order", ["invalid", 123, "dmy_extra"])
def test_invalid_date_order(date_order):
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["date_order"] = date_order
    with pytest.raises(ValueError, match="date_order"):
        validate_config(bad_cfg)


@pytest.mark.parametrize("converter", ["invalid_converter", "autoo", 99])
def test_invalid_dwg_converter(converter):
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["dwg_converter"] = converter
    with pytest.raises(ValueError, match="dwg_converter"):
        validate_config(bad_cfg)


def test_invalid_vocabulary_not_dict():
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["bom_headers"] = ["item", "qty"]
    with pytest.raises(ValueError, match="bom_headers.*dictionary"):
        validate_config(bad_cfg)


def test_invalid_vocabulary_value_not_list():
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["title_labels"] = {"drawing_number": "DWG NO"}  # string instead of list
    with pytest.raises(ValueError, match="must be a list"):
        validate_config(bad_cfg)


def test_invalid_vocabulary_empty_string_in_list():
    bad_cfg = DEFAULT_CONFIG.copy()
    bad_cfg["revision_headers"] = {"rev": ["REV", "", "ISSUE"]}  # empty string in list
    with pytest.raises(ValueError, match="non-empty strings"):
        validate_config(bad_cfg)


def test_load_config_non_existent_file(tmp_path):
    missing_file = tmp_path / "non_existent.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing_file)


def test_load_config_malformed_yaml_syntax(tmp_path):
    bad_yaml = tmp_path / "syntax_error.yaml"
    bad_yaml.write_text("dpi: [unclosed list\nmax_pixels: 500000", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_config(bad_yaml)


def test_load_config_malformed_yaml_not_mapping(tmp_path):
    bad_yaml = tmp_path / "list_not_dict.yaml"
    bad_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a YAML mapping/dictionary"):
        load_config(bad_yaml)


def test_load_config_with_valid_yaml_and_overrides(tmp_path):
    custom_yaml = tmp_path / "valid.yaml"
    custom_yaml.write_text("dpi: 400\ndate_order: ymd\n", encoding="utf-8")
    cfg = load_config(custom_yaml, overrides={"dpi": 600})
    assert cfg["dpi"] == 600
    assert cfg["date_order"] == "ymd"

