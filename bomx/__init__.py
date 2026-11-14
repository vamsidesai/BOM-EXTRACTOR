"""bomx - automated BOM & material property extraction from 2D engineering drawings."""
__version__ = "1.1.1"


def extract(path, config=None, force_ocr=False, overlay_dir=None, **overrides):
    """Python API: process one drawing and return a DrawingResult.

    >>> from bomx import extract
    >>> res = extract("drawing.pdf")
    >>> res.summary["drawing_number"], len(res.bom)
    """
    from pathlib import Path
    from .config import load_config
    from .pipeline import process_file
    cfg = load_config(config, overrides)
    return process_file(path, cfg, force_ocr=force_ocr,
                        overlay_dir=Path(overlay_dir) if overlay_dir else None)
