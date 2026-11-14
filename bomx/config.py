"""Default vocabulary and tunables. Everything here can be overridden with a
YAML file passed via ``--config`` (see ``bomx dump-config``)."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    # -------------------------------------------------- rendering / OCR
    "dpi": 300,
    "max_pixels": 80_000_000,  # cap for very large sheets (A0 etc.)
    "ocr_lang": "eng",
    "tesseract_cmd": None,  # full path to tesseract(.exe) if it is not on PATH
    "min_word_conf": 25,  # tesseract confidence floor (0-100)
    "cell_ocr": True,  # re-OCR table cells individually (more accurate on scans)
    "native_min_words": 15,  # fewer extractable words than this -> treat PDF page as scanned
    "deskew": True,
    "auto_rotate": True,  # use tesseract OSD to fix 90/180/270 scans
    "date_order": "dmy",  # how to read ambiguous dates like 05/08/2024: dmy | mdy
    "low_conf_threshold": 0.65,

    # -------------------------------------------------- 2D CAD (DXF / DWG)
    "cad_layouts": "auto",  # auto (smart layout selection based on content & text) | model | paper | all
    "dwg_converter": "auto",  # auto | oda | libredwg | aspose  (auto tries them in priority order)
    "oda_converter": None,  # path to ODAFileConverter(.exe) if not found automatically
    "libredwg_path": None,  # LibreDWG folder or path to dwgread(.exe) if not on PATH
    "cad_traced_dpi": 400,  # render resolution for traced (outline-only) CAD drawings
    "cad_timeout": 600,  # seconds allowed for one DWG conversion
    # block-attribute tags that hold title-block values (added to the built-in list);
    # e.g. {"drawing_number": ["ZEICHNUNGSNR"], "revision": ["AEND"]}
    "cad_attribute_tags": {},

    # -------------------------------------------------- BOM header vocabulary
    "bom_headers": {
        "item": ["ITEM", "ITEM NO", "ITEM NUMBER", "ITM", "SR NO", "SL NO", "S NO", "SNO",
                 "POS", "POS NO", "POSITION", "FIND NO", "BALLOON", "REF NO", "NO",
                 "DET", "DETAIL", "MARK", "TEIL", "POS.", "REP", "REPERE", "ELEMENT", "PIEZA"],
        "part_number": ["PART NO", "PART NUMBER", "PART #", "P/N", "PN", "PART CODE",
                        "ITEM CODE", "CODE", "DRG NO", "DWG NO", "DRAWING NO", "STOCK NO",
                        "CAT NO", "CATALOGUE NO", "CATALOG NO", "PART ID", "MATERIAL CODE",
                        "SACHNUMMER", "TEILENUMMER", "ZEICHNUNGSNUMMER", "REFERENCE", "REF",
                        "NUMERO DE PIECE", "CODICE", "ART NO", "ART-NR"],
        "description": ["DESCRIPTION", "DESC", "PART DESCRIPTION", "PART NAME", "NAME",
                        "NOMENCLATURE", "COMPONENT", "DESIGNATION", "TITLE",
                        "BENENNUNG", "BEZEICHNUNG", "DENOMINATION", "BESCHREIBUNG",
                        "DESCRIZIONE", "DESCRIPCION"],
        "quantity": ["QTY", "QUANTITY", "QTY/ASSY", "QTY PER ASSY", "NOS", "NO OFF",
                     "NO OF", "OFF", "QNTY", "QTY REQD", "REQD",
                     "STK", "STUECK", "MENGE", "ANZAHL", "QTE", "QUANTITE", "CANTIDAD", "QTA", "PZ"],
        "material": ["MATERIAL", "MATL", "MATERIAL GRADE", "MATERIAL SPEC", "MAT", "GRADE",
                     "SPECIFICATION", "SPEC", "MATERIAL & SPEC",
                     "WERKSTOFF", "MATIERE", "MATERIALE", "MATERIAAL"],
        "mass": ["MASS", "WEIGHT", "WT", "UNIT WT", "UNIT WEIGHT", "UNIT MASS", "TOTAL WT",
                 "TOTAL WEIGHT", "TOTAL MASS", "WT/PC", "NET WT",
                 "GEWICHT", "MASSE", "POIDS", "PESO"],
        "remarks": ["REMARKS", "REMARK", "COMMENTS", "COMMENT", "NOTES", "NOTE",
                    "BEMERKUNG", "BEMERKUNGEN", "OBSERVATIONS", "REMARQUES", "NOTAS", "ANMERKUNG"],
        "supplier": ["SUPPLIER", "VENDOR", "MAKE", "MANUFACTURER", "MFR", "SOURCE",
                     "LIEFERANT", "FOURNISSEUR", "FORNITORE", "PROVEEDOR"],
        "finish": ["FINISH", "SURFACE FINISH", "COATING", "TREATMENT",
                   "OBERFLAECHE", "REVETEMENT", "TRATAMIENTO", "FINITURA"],
        "size": ["SIZE", "STOCK SIZE", "DIMENSIONS", "DIMENSION", "CUT LENGTH", "LENGTH",
                 "ABMESSUNG", "ABMESSUNGEN", "DIMENSIONES", "DIMENSIONI"],
    },

    # -------------------------------------------------- revision table vocabulary
    "revision_headers": {
        "rev": ["REV", "REVISION", "REV NO", "ISSUE", "REV LEVEL", "LTR",
                "AEND", "AENDERUNG", "AENDERUNGSSTAND", "VERSION", "EDITION", "INDICE", "IND"],
        "description": ["DESCRIPTION", "DESC", "CHANGE", "REVISION DESCRIPTION",
                        "DETAILS", "CHANGE DESCRIPTION",
                        "AENDERUNGSTEXT", "MODIFICATION", "MOTIF", "MODIFICA"],
        "date": ["DATE", "REV DATE", "DATUM"],
        "approved": ["APPROVED", "APPD", "APPR", "APPROVED BY", "APP", "BY", "CHKD",
                     "GEPR", "GEPRUEFT", "VISA", "VISTO"],
        "zone": ["ZONE"],
        "ecn": ["ECN", "ECO", "ECN NO", "ECO NO", "CR NO"],
    },

    # -------------------------------------------------- title block labels
    "title_labels": {
        "drawing_number": ["DWG NO", "DWG NUMBER", "DRAWING NO", "DRAWING NUMBER", "DRG NO",
                           "DRG NUMBER", "DOCUMENT NO", "DOC NO", "DWG #", "DRAWING #",
                           "ZEICHNUNGSNUMMER", "ZEICHNUNGS-NR", "ZEICHNUNG NR", "ZCHG-NR",
                           "NUMERO DE DESSIN", "NUMERO DE PIECE", "NO PLAN", "N PLAN", "DOCUMENTO", "N. DIS."],
        "drawing_title": ["TITLE", "DRAWING TITLE", "DWG TITLE", "PART NAME",
                          "BENENNUNG", "BEZEICHNUNG", "TITRE", "TITOLO", "TITULO"],
        "revision": ["REV", "REVISION", "REV NO", "REV LEVEL", "ISSUE",
                     "AEND", "AENDERUNG", "AENDERUNGSSTAND", "VERSION", "EDITION", "INDICE"],
        "drawn_by": ["DRAWN BY", "DRAWN", "DRN BY", "DRN", "DRAFTER", "AUTHOR",
                     "DESIGNED BY", "DESIGNED", "DESIGNER", "CREATED BY", "PREPARED BY",
                     "GEZEICHNET", "GEZ", "DESSINE", "DIBUJADO", "DISEGNATORE"],
        "checked_by": ["CHECKED BY", "CHECKED", "CHKD", "CHK", "CHECKER", "REVIEWED BY",
                       "GEPRUEFT", "GEPR", "VERIFIE", "COMPROBADO", "CONTROLLATO"],
        "approved_by": ["APPROVED BY", "APPROVED", "APPD", "APPR", "APPROVER",
                        "FREIGEGEBEN", "GENEHMIGT", "APPROUVE", "APPROVATO"],
        "date": ["DATE", "DRAWN DATE", "DATE DRAWN", "DATUM", "DATA"],
        "scale": ["SCALE", "SCL", "MASSSTAB", "ECHELLE", "ESCALA", "SCALA"],
        "projection": ["PROJECTION", "PROJ", "PROJECTION TYPE", "PROJEKTION"],
        "sheet": ["SHEET", "SHT", "SHEET NO", "BLATT", "FEUILLE", "FOGLIO", "HOJA"],
        "size": ["SIZE", "SHEET SIZE", "PAPER SIZE", "FORMAT"],
        "material": ["MATERIAL", "MATL", "MAT", "WERKSTOFF", "MATIERE", "MATERIALE"],
        "finish": ["FINISH", "SURFACE FINISH", "SURFACE TREATMENT", "COATING", "OBERFLAECHE", "FINITURA"],
        "heat_treatment": ["HEAT TREATMENT", "HEAT TREAT", "H/T", "HT",
                           "WAERMEBEHANDLUNG", "TRAITEMENT THERMIQUE", "TRATTAMENTO TERMICO"],
        "weight": ["WEIGHT", "MASS", "WT", "TOTAL WEIGHT", "NET WT", "GEWICHT", "MASSE", "POIDS", "PESO"],
        "tolerance": ["GENERAL TOLERANCE", "TOLERANCES", "TOLERANCE", "UNLESS OTHERWISE SPECIFIED",
                      "ALLGEMEINTOLERANZEN", "TOLERANZEN", "TOLERANCES GENERALES"],
        "units": ["UNITS", "UNIT", "DIMENSIONS IN", "MASSEINHEIT", "UNITE"],
        "company": ["COMPANY", "CUSTOMER", "CLIENT", "FIRMA", "HERSTELLER", "SOCIETE"],
        "part_number": ["PART NO", "PART NUMBER", "P/N", "SACHNUMMER", "TEILENUMMER"],
    },
}


def _validate_vocab(cfg: dict, key: str) -> None:
    val = cfg.get(key)
    if not isinstance(val, dict):
        raise ValueError(f"Invalid config '{key}': must be a dictionary mapping field names to lists of synonyms/labels.")
    for field_name, items in val.items():
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError(f"Invalid config '{key}': field name must be a non-empty string, got {field_name!r}.")
        if not isinstance(items, list):
            raise ValueError(f"Invalid config '{key}' entry for '{field_name}': value must be a list of strings, got {type(items).__name__}.")
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"Invalid config '{key}' entry for '{field_name}': list items must be non-empty strings, got {item!r}.")


def validate_config(cfg: dict) -> dict:
    """Validate configuration schema, data types, vocabularies, and allowed ranges."""
    if not isinstance(cfg, dict):
        raise ValueError(f"Configuration must be a dictionary, got {type(cfg).__name__}.")

    # 1. Reject unknown configuration keys
    known_keys = set(DEFAULT_CONFIG.keys())
    unknown = set(cfg.keys()) - known_keys
    if unknown:
        raise ValueError(f"Unknown configuration key(s): {', '.join(sorted(unknown))}")

    # 2. Numeric ranges
    if isinstance(cfg.get("dpi"), bool) or not isinstance(cfg.get("dpi"), (int, float)) or not (50 <= cfg["dpi"] <= 1200):
        raise ValueError(f"Invalid config 'dpi': {cfg.get('dpi')}. Must be a number between 50 and 1200.")
    if isinstance(cfg.get("max_pixels"), bool) or not isinstance(cfg.get("max_pixels"), (int, float)) or cfg["max_pixels"] <= 100_000:
        raise ValueError(f"Invalid config 'max_pixels': {cfg.get('max_pixels')}. Must be a number >= 100,000.")
    if isinstance(cfg.get("min_word_conf"), bool) or not isinstance(cfg.get("min_word_conf"), (int, float)) or not (0 <= cfg["min_word_conf"] <= 100):
        raise ValueError(f"Invalid config 'min_word_conf': {cfg.get('min_word_conf')}. Must be a number in range 0..100.")
    if isinstance(cfg.get("low_conf_threshold"), bool) or not isinstance(cfg.get("low_conf_threshold"), (int, float)) or not (0.0 <= cfg["low_conf_threshold"] <= 1.0):
        raise ValueError(f"Invalid config 'low_conf_threshold': {cfg.get('low_conf_threshold')}. Must be a number in range 0.0..1.0.")
    if isinstance(cfg.get("cad_traced_dpi"), bool) or not isinstance(cfg.get("cad_traced_dpi"), (int, float)) or not (50 <= cfg["cad_traced_dpi"] <= 1200):
        raise ValueError(f"Invalid config 'cad_traced_dpi': {cfg.get('cad_traced_dpi')}. Must be a number between 50 and 1200.")
    if isinstance(cfg.get("cad_timeout"), bool) or not isinstance(cfg.get("cad_timeout"), (int, float)) or cfg["cad_timeout"] <= 0:
        raise ValueError(f"Invalid config 'cad_timeout': {cfg.get('cad_timeout')}. Must be a positive number.")
    if isinstance(cfg.get("native_min_words"), bool) or not isinstance(cfg.get("native_min_words"), int) or cfg["native_min_words"] < 0:
        raise ValueError(f"Invalid config 'native_min_words': {cfg.get('native_min_words')}. Must be a non-negative integer.")

    # 3. Boolean settings
    for b_key in ("cell_ocr", "deskew", "auto_rotate"):
        if not isinstance(cfg.get(b_key), bool):
            raise ValueError(f"Invalid config '{b_key}': must be a boolean (true/false), got {type(cfg.get(b_key)).__name__}.")

    # 4. String and optional string paths
    if not isinstance(cfg.get("ocr_lang"), str) or not cfg["ocr_lang"].strip():
        raise ValueError(f"Invalid config 'ocr_lang': {cfg.get('ocr_lang')!r}. Must be a non-empty string.")
    for p_key in ("tesseract_cmd", "oda_converter", "libredwg_path"):
        val = cfg.get(p_key)
        if val is not None and (not isinstance(val, str) or not val.strip()):
            raise ValueError(f"Invalid config '{p_key}': must be null or a non-empty file path string, got {val!r}.")

    # 5. Enumerated choices
    date_order = str(cfg.get("date_order", "")).lower()
    if date_order not in ("dmy", "mdy", "ymd"):
        raise ValueError(f"Invalid config 'date_order': '{cfg.get('date_order')}'. Allowed: 'dmy', 'mdy', 'ymd'.")
    cad_layouts = str(cfg.get("cad_layouts", "")).lower()
    if cad_layouts not in ("auto", "model", "paper", "all"):
        raise ValueError(f"Invalid config 'cad_layouts': '{cfg.get('cad_layouts')}'. Allowed: 'auto', 'model', 'paper', 'all'.")
    dwg_converter = str(cfg.get("dwg_converter", "")).lower()
    if dwg_converter not in ("auto", "oda", "libredwg", "aspose"):
        raise ValueError(f"Invalid config 'dwg_converter': '{cfg.get('dwg_converter')}'. Allowed: 'auto', 'oda', 'libredwg', 'aspose'.")

    # 6. Vocabularies
    _validate_vocab(cfg, "bom_headers")
    _validate_vocab(cfg, "title_labels")
    _validate_vocab(cfg, "revision_headers")
    _validate_vocab(cfg, "cad_attribute_tags")

    return cfg


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(p, "r", encoding="utf-8") as fh:
            user = yaml.safe_load(fh)
        if user is None:
            user = {}
        elif not isinstance(user, dict):
            raise ValueError(f"Config file '{path}' must contain a YAML mapping/dictionary, got {type(user).__name__}.")
        _merge(cfg, user)
    if overrides:
        _merge(cfg, {k: v for k, v in overrides.items() if v is not None})
    return validate_config(cfg)


def _merge(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def dump_default(path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(DEFAULT_CONFIG, fh, sort_keys=False, allow_unicode=True)
