"""Command-line interface.

    bomx extract drawings/ -o results/                 # whole folder
    bomx extract a.pdf b.tif -o out --formats xlsx,json
    bomx dump-config my_vocab.yaml                      # editable vocabulary
    bomx extract plan.dwg layout.dxf -o out --cad-layouts all
    bomx check                                          # environment check
    bomx ui                                             # web interface in the browser
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .config import dump_default, load_config
from .export import bom_records, write_csv, write_csvs, write_json, write_xlsx, SUMMARY_COLS
from .ingest import discover_inputs
from .models import DrawingResult
from .pipeline import process_file

log = logging.getLogger("bomx")


def _work(args):
    path, cfg, out_root, formats, overlay, force_ocr, flat = args
    path = Path(path)
    out_dir = Path(out_root) if flat else Path(out_root) / _safe(path.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        res = process_file(path, cfg, force_ocr=force_ocr, overlay_dir=out_dir if overlay else None)
        for p in res.pages:
            for r in p.regions:
                r.cells = []  # keep pickles small
        stem = _safe(path.stem)
        if "json" in formats:
            write_json(res, out_dir / f"{stem}.json")
        if "csv" in formats:
            write_csvs(res, out_dir, stem)
        if "xlsx" in formats:
            write_xlsx([res], out_dir / f"{stem}.xlsx")
        return str(path), res, None
    except Exception as e:  # keep the batch going
        return str(path), None, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"


def _safe(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)


def cmd_extract(a) -> int:
    overrides = {"dpi": a.dpi, "ocr_lang": a.lang, "date_order": a.date_order,
                 "tesseract_cmd": a.tesseract}
    if a.no_cell_ocr:
        overrides["cell_ocr"] = False
    if a.no_deskew:
        overrides["deskew"] = False
    if a.no_rotate:
        overrides["auto_rotate"] = False
    overrides.update({"cad_layouts": a.cad_layouts, "dwg_converter": a.dwg_converter,
                      "oda_converter": a.oda, "libredwg_path": a.libredwg})
    cfg = load_config(a.config, overrides)
    formats = {f.strip().lower() for f in a.formats.split(",") if f.strip()}
    bad = formats - {"xlsx", "csv", "json"}
    if bad:
        print(f"unknown format(s): {', '.join(sorted(bad))}", file=sys.stderr)
        return 2
    files = discover_inputs(a.inputs, recursive=not a.no_recursive)
    if not files:
        print("no supported drawings found (pdf, dwg, dxf, tif, tiff, png, jpg, bmp)", file=sys.stderr)
        return 1
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    flat = len(files) == 1 and not a.subfolders
    jobs = [(str(f), cfg, str(out), formats, not a.no_overlay, a.force_ocr, flat) for f in files]

    t0 = time.time()
    results: list[DrawingResult] = []
    report = []
    statuses = {}
    print(f"bomx {__version__}: processing {len(files)} drawing(s) -> {out}")

    def handle(path, res, err):
        if err:
            print(f"  ✗ {Path(path).name}: {err.splitlines()[0]}")
            report.append({"file": path, "status": "error", "error": err})
            statuses[path] = "error"
            return
        s = res.summary
        mark = "!" if s.get("review_required") else "✓"
        print(f"  {mark} {Path(path).name}: DWG {s.get('drawing_number') or '?'} rev "
              f"{s.get('revision') or '?'} | {s['bom_items']} BOM rows | "
              f"{len(res.specs)} spec callouts | {res.processing_seconds:.1f}s")
        if s.get("review_required") and a.verbose:
            print(f"      review: {s['review_reasons']}")
        results.append(res)
        statuses[path] = "review" if s.get("review_required") else "ok"
        report.append({"file": path, "status": statuses[path], "summary": s, "warnings": res.warnings})

    if a.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(_work, j) for j in jobs]
            for f in as_completed(futs):
                handle(*f.result())
    else:
        for j in jobs:
            handle(*_work(j))

    order = {str(f): i for i, f in enumerate(files)}
    results.sort(key=lambda r: order.get(r.source_file, 0))
    if len(files) > 1 or a.subfolders:
        # Excel stays one workbook per drawing (written above) - no merged workbook
        if "csv" in formats:
            write_csv([rec for r in results for rec in bom_records(r)], out / "consolidated_bom.csv")
            summ = [dict(r.summary, status=statuses.get(r.source_file)) for r in results]
            write_csv(summ, out / "consolidated_summary.csv", SUMMARY_COLS)
    (out / "batch_report.json").write_text(json.dumps(
        {"version": __version__, "files": len(files), "ok": sum(1 for r in report if r["status"] == "ok"),
         "review": sum(1 for r in report if r["status"] == "review"),
         "errors": sum(1 for r in report if r["status"] == "error"),
         "seconds": round(time.time() - t0, 1), "results": report}, indent=2, default=str), encoding="utf-8")
    n_err = sum(1 for r in report if r["status"] == "error")
    print(f"done in {time.time() - t0:.1f}s - {len(results)} ok/review, {n_err} error(s)")
    return 1 if n_err and not results else 0


def cmd_check(a) -> int:
    from .imaging import find_tesseract, tesseract_available
    path = find_tesseract(getattr(a, "tesseract", None))
    if path:
        print(f"found      {path}")
    import cv2, pymupdf
    v = tesseract_available()
    print(f"bomx       {__version__}")
    print(f"python     {sys.version.split()[0]}")
    print(f"opencv     {cv2.__version__}")
    print(f"pymupdf    {pymupdf.VersionBind}")
    print(f"tesseract  {v or 'NOT FOUND - install tesseract-ocr (needed for scanned drawings)'}")
    if v:
        import pytesseract
        langs = pytesseract.get_languages(config="")
        print(f"languages  {', '.join(langs)}")
        if "osd" not in langs:
            print("           (no 'osd' data: automatic 90/180/270 rotation disabled)")
    try:
        import ezdxf
        print(f"ezdxf      {ezdxf.__version__}  (DXF: native text + traced drawings)")
    except ImportError:
        print("ezdxf      NOT FOUND - pip install ezdxf (needed for DXF and DWG)")
    from .cad import dwg_backends
    b = dwg_backends({"oda_converter": getattr(a, "oda", None), "libredwg_path": getattr(a, "libredwg", None)})
    if b["oda"]:
        print(f"DWG        ODA File Converter: {b['oda']}")
    if b["libredwg"]:
        print(f"DWG        LibreDWG dwgread: {b['libredwg']}")
    if b["aspose"]:
        print("DWG        aspose-cad installed (render-only fallback; unlicensed copies add a watermark)")
    if not any(b.values()):
        print("DWG        NO CONVERTER - DWG files can't be read. Install the free ODA File Converter "
              "(opendesign.com/guestfiles/oda_file_converter) or LibreDWG "
              "(github.com/LibreDWG/libredwg/releases). DXF, PDF and scans work without one.")
    return 0 if v else 1


def cmd_ui(a) -> int:
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("The UI needs Streamlit:  pip install streamlit pandas", file=sys.stderr)
        return 1
    import subprocess
    app = Path(__file__).with_name("ui_app.py")
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(a.port),
           "--browser.gatherUsageStats", "false", "--server.maxUploadSize", "1000"]
    if a.no_browser:
        cmd += ["--server.headless", "true"]
    print(f"Starting bomx UI at http://localhost:{a.port}  (Ctrl+C to stop)")
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):  # never crash on consoles without UTF-8
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="bomx", description="Extract BOM, title block, revisions, notes and "
                                "material/finish/heat-treatment specs from 2D engineering drawings.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="process drawings")
    e.add_argument("inputs", nargs="+", help="files and/or folders (pdf, tif, tiff, png, jpg, bmp, dwg, dxf)")
    e.add_argument("-o", "--output", default="bomx_output", help="output folder")
    e.add_argument("-f", "--formats", default="xlsx,csv,json", help="comma list of xlsx,csv,json")
    e.add_argument("-c", "--config", help="YAML vocabulary/settings override (see dump-config)")
    e.add_argument("--dpi", type=int, help="render/OCR resolution (default 300)")
    e.add_argument("--lang", help="tesseract language(s), e.g. eng or eng+deu")
    e.add_argument("--tesseract", help="path to tesseract executable if not on PATH")
    e.add_argument("--date-order", choices=["dmy", "mdy"], help="ambiguous numeric dates (default dmy)")
    e.add_argument("--force-ocr", action="store_true", help="OCR even when a PDF has a text layer")
    e.add_argument("--no-overlay", action="store_true", help="skip validation overlay images")
    e.add_argument("--no-cell-ocr", action="store_true", help="faster: skip per-cell re-OCR on scans")
    e.add_argument("--no-deskew", action="store_true")
    e.add_argument("--no-rotate", action="store_true", help="disable 90/180/270 auto-orientation")
    e.add_argument("--no-recursive", action="store_true", help="don't descend into sub-folders")
    e.add_argument("--subfolders", action="store_true", help="always write one sub-folder per drawing")
    e.add_argument("--cad-layouts", choices=["auto", "model", "paper", "all"],
                   help="DWG/DXF: which layouts to read (default auto: paper-space sheets, else model space)")
    e.add_argument("--dwg-converter", choices=["auto", "oda", "libredwg", "aspose"],
                   help="DWG reader to use (default auto)")
    e.add_argument("--oda", help="path to ODAFileConverter if not found automatically")
    e.add_argument("--libredwg", help="LibreDWG folder or dwgread path if not on PATH")
    e.add_argument("-w", "--workers", type=int, default=1, help="parallel processes for batches")
    e.add_argument("-v", "--verbose", action="store_true")
    e.set_defaults(fn=cmd_extract)

    d = sub.add_parser("dump-config", help="write the default vocabulary/settings to a YAML file")
    d.add_argument("path")
    d.set_defaults(fn=lambda a: (dump_default(a.path), print(f"wrote {a.path}"), 0)[-1])

    c = sub.add_parser("check", help="verify OCR engine, CAD readers and libraries")
    c.add_argument("--tesseract", help="path to tesseract executable if not on PATH")
    c.add_argument("--oda", help="path to ODAFileConverter if not found automatically")
    c.add_argument("--libredwg", help="LibreDWG folder or dwgread path if not on PATH")
    c.set_defaults(fn=cmd_check)

    u = sub.add_parser("ui", help="open the web interface in your browser")
    u.add_argument("--port", type=int, default=8501)
    u.add_argument("--no-browser", action="store_true", help="don't open a browser tab automatically")
    u.set_defaults(fn=cmd_ui)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if getattr(a, "verbose", False):
        logging.getLogger("bomx").setLevel(logging.DEBUG)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
