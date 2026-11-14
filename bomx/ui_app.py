"""bomx web UI (Streamlit).

Start it with:   python -m bomx ui
It opens in your browser at http://localhost:8501
"""
from __future__ import annotations

import atexit
import io
import json
import shutil
import sys
import tempfile
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# make `import bomx` work when Streamlit runs this file directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from PIL import Image  # noqa: E402

from bomx import __version__  # noqa: E402
from bomx import export as ex  # noqa: E402
from bomx.config import load_config  # noqa: E402
from bomx.ingest import SUPPORTED_EXT, discover_inputs  # noqa: E402
from bomx.pipeline import process_file  # noqa: E402

Image.MAX_IMAGE_PIXELS = 100_000_000
st.set_page_config(page_title="bomx · Drawing BOM Extractor", page_icon="📐", layout="wide")

def _cleanup_workdir(path: str):
    try:
        if path and Path(path).exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

ss = st.session_state
ss.setdefault("results", {})   # key -> {"res": DrawingResult|None, "error": str|None, "path": str}
ss.setdefault("edited", {})    # key -> {table: DataFrame}  (latest edits)
ss.setdefault("base", {})      # key -> {table: DataFrame}  (snapshot fed to the editors)
ss.setdefault("nonce", {})     # key -> int  (fresh editor widgets each time a drawing is opened)
ss.setdefault("verified", {})  # key -> bool
ss.setdefault("current", None)
ss.setdefault("seq", 0)        # running input counter (stable ordering across runs)
if "workdir" not in ss:
    wd_temp = tempfile.mkdtemp(prefix="bomx_ui_")
    ss["workdir"] = wd_temp
    atexit.register(_cleanup_workdir, wd_temp)

TABLES = ["title_block", "bom", "specs", "revisions", "notes"]
TITLE_KEYS = ["drawing_number", "drawing_title", "revision", "drawn_by", "date", "scale", "projection", "sheet"]


# ======================================================================
# helpers
# ======================================================================

def _run_one(path: Path, cfg: dict, force_ocr: bool, out_dir: Path):
    try:
        res = process_file(path, cfg, force_ocr=force_ocr, overlay_dir=out_dir)
        for p in res.pages:
            for r in p.regions:
                r.cells = []
        return res, None
    except Exception as e:  # keep the batch going
        return None, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}"


def _records(res, table: str) -> list[dict]:
    return {"title_block": ex.title_records, "bom": ex.bom_records, "specs": ex.spec_records,
            "revisions": ex.revision_records, "notes": ex.note_records}[table](res)


def _original_df(res, table: str) -> pd.DataFrame:
    recs = _records(res, table)
    df = pd.DataFrame(recs)
    if table == "bom":
        if df.empty:
            df = pd.DataFrame(columns=["drawing_number"] + ex.BOM_STD)
        df.insert(0, "check", ["⚠" if f else "" for f in df.get("flags", pd.Series([None] * len(df)))])
    if table == "title_block" and df.empty:
        df = pd.DataFrame(columns=["drawing_number", "field", "value", "normalized", "confidence"])
    return df


def _clean(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df.drop(columns=[c for c in ("check",) if c in df.columns])
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict("records")


def _table(key: str, table: str) -> pd.DataFrame:
    """Current (possibly edited) table for a drawing."""
    if table in ss.edited.get(key, {}):
        return ss.edited[key][table]
    return _original_df(ss.results[key]["res"], table)


def _summary(key: str) -> dict:
    """Summary row with manual title-block corrections applied."""
    entry = ss.results[key]
    res = entry["res"]
    if res is None:
        return {"file": Path(entry["path"]).name, "status": "error", "review_reasons": entry["error"].splitlines()[0]}
    s = dict(res.summary)
    if "title_block" in ss.edited.get(key, {}):
        orig = {r["field"]: r["value"] for r in ex.title_records(res)}
        for r in _clean(ss.edited[key]["title_block"]):
            f, v = r.get("field"), r.get("value")
            if f in TITLE_KEYS and v != orig.get(f):
                s[f] = v
        s["author_date"] = " / ".join(x for x in (s.get("drawn_by"), s.get("date")) if x) or None
    if ss.verified.get(key):
        s["status"] = "verified"
    else:
        s["status"] = "review" if s.get("review_required") else "ok"
    return s


def _status_icon(status: str) -> str:
    return {"verified": "✅", "ok": "🟢", "review": "⚠️", "error": "❌"}.get(status, "")


def _build_xlsx(keys: list[str]) -> bytes:
    summ, bom, tb, specs, revs, notes, warns = [], [], [], [], [], [], []
    extraction = []
    for k in keys:
        s = _summary(k)
        summ.append(s)
        res = ss.results[k]["res"]
        if res is None:
            continue
        dn = s.get("drawing_number") or Path(res.source_file).stem
        for name, target in (("bom", bom), ("title_block", tb), ("specs", specs), ("revisions", revs),
                             ("notes", notes)):
            for r in _clean(_table(k, name)):
                r["drawing_number"] = dn
                target.append(r)
        warns += [{"source_file": Path(res.source_file).name, "warning": w} for w in res.warnings]
        extraction.append((s, [r for r in bom if r.get("drawing_number") == dn]))
    bom_cols = ["drawing_number", "item", "part_number", "description", "quantity", "quantity_value", "material",
                "mass", "mass_kg", "remarks"]
    bom_cols += [c for r in bom for c in r if c not in bom_cols and c not in ("confidence", "flags", "page",
                                                                              "source_file")]
    bom_cols = list(dict.fromkeys(bom_cols)) + ["confidence", "flags", "page", "source_file"]
    buf = io.BytesIO()
    ex.write_sheets_xlsx([
        ("Summary", summ, ex.SUMMARY_COLS, "review_required"),
        ("BOM", bom, bom_cols, "flags"),
        ("Title Block", tb, ["drawing_number", "field", "value", "normalized", "confidence"], None),
        ("Material & Specs", specs, ["drawing_number", "category", "subtype", "value", "source", "context", "page",
                                     "confidence"], None),
        ("Revisions", revs, ["drawing_number", "rev", "description", "date", "date_iso", "approved", "page",
                             "confidence"], None),
        ("Notes", notes, ["drawing_number", "page", "number", "text", "confidence"], None),
        ("Warnings", warns, ["source_file", "warning"], None),
    ], buf, extraction=extraction)
    return buf.getvalue()


def _bom_csv(keys: list[str]) -> bytes:
    rows = []
    for k in keys:
        if ss.results[k]["res"] is None:
            continue
        dn = _summary(k).get("drawing_number")
        for r in _clean(_table(k, "bom")):
            r["drawing_number"] = dn
            rows.append(r)
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def _json(keys: list[str]) -> bytes:
    out = []
    for k in keys:
        res = ss.results[k]["res"]
        if res is None:
            out.append({"file": ss.results[k]["path"], "error": ss.results[k]["error"]})
            continue
        d = res.to_dict()
        d["summary"] = _summary(k)
        d["bom"] = _clean(_table(k, "bom"))
        d["title_block_edited"] = _clean(_table(k, "title_block"))
        d["verified"] = bool(ss.verified.get(k))
        out.append(d)
    return json.dumps(out, indent=2, default=str, ensure_ascii=False).encode("utf-8")


def _excel_name(key: str, used: set[str]) -> str:
    """One Excel per drawing, named after the drawing file."""
    res = ss.results[key]["res"]
    stem = Path(res.source_file if res else ss.results[key]["path"]).stem
    name, i = f"{stem}.xlsx", 2
    while name.lower() in used:
        name, i = f"{stem}_{i}.xlsx", i + 1
    used.add(name.lower())
    return name


def _per_drawing_xlsx(keys: list[str]) -> list[tuple[str, bytes]]:
    used: set[str] = set()
    return [(_excel_name(k, used), _build_xlsx([k])) for k in keys if ss.results[k]["res"] is not None]


def _excels_zip(keys: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in _per_drawing_xlsx(keys):
            z.writestr(name, data)
    return buf.getvalue()


def _zip(keys: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in _per_drawing_xlsx(keys):
            z.writestr(f"excel/{name}", data)
        z.writestr("bom.csv", _bom_csv(keys))
        z.writestr("results.json", _json(keys))
        for k in keys:
            res = ss.results[k]["res"]
            for p in (res.pages if res else []):
                if p.overlay_path and Path(p.overlay_path).exists():
                    z.write(p.overlay_path, f"overlays/{Path(p.overlay_path).name}")
    return buf.getvalue()


# ======================================================================
# sidebar: inputs & settings
# ======================================================================
with st.sidebar:
    st.markdown(f"## 📐 bomx\nDrawing BOM & spec extractor · v{__version__}")
    uploads = st.file_uploader("Upload drawings", accept_multiple_files=True,
                               type=sorted(e.strip(".") for e in SUPPORTED_EXT),
                               help="Digital or scanned PDF, TIFF, PNG, JPG, DWG, DXF")
    folder = st.text_input("…or a folder / file path on this computer", placeholder=r"D:\Drawings\Legacy")

    with st.expander("⚙️ Settings"):
        dpi = st.select_slider("Scan resolution (DPI)", [200, 250, 300, 400], value=300)
        workers = st.slider("Drawings in parallel", 1, 8, 2)
        cell_ocr = st.checkbox("Per-cell re-OCR (slower, more accurate on scans)", value=True)
        force_ocr = st.checkbox("Force OCR (ignore PDF text layer)")
        date_order = st.radio("Read 05/08/2024 as", ["dmy", "mdy"], horizontal=True,
                              format_func=lambda x: "5 Aug (DD/MM)" if x == "dmy" else "May 8 (MM/DD)")
        lang = st.text_input("OCR language(s)", "eng", help="e.g. eng or eng+deu")
        tess = st.text_input("Tesseract path (only if not on PATH)",
                             placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        vocab = st.file_uploader("Custom vocabulary (YAML)", type=["yaml", "yml"],
                                 help="Create one with: python -m bomx dump-config my_vocab.yaml")
    with st.expander("📐 CAD (DWG / DXF)"):
        cad_layouts = st.radio("Layouts to read", ["auto", "model", "paper", "all"], horizontal=True,
                               help="auto: paper-space sheets if the drawing has them, else model space")
        oda = st.text_input("ODA File Converter path (if not found automatically)",
                            placeholder=r"C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe")
        libredwg = st.text_input("LibreDWG folder or dwgread path (if not on PATH)",
                                 placeholder=r"C:\Tools\libredwg")
        from bomx.cad import dwg_backends
        _b = dwg_backends({"oda_converter": oda.strip().strip('"') or None,
                           "libredwg_path": libredwg.strip().strip('"') or None})
        if _b["oda"] or _b["libredwg"]:
            st.caption("DWG reader: " + ("ODA File Converter ✓" if _b["oda"] else "LibreDWG ✓"))
        else:
            st.caption("No DWG reader found - DXF works; for DWG install the free ODA File Converter "
                       "or LibreDWG.")

    import pytesseract
    from bomx.imaging import find_tesseract
    found = find_tesseract(tess.strip().strip('"') or None)
    try:
        tv = str(pytesseract.get_tesseract_version())
        st.caption(f"OCR engine: Tesseract {tv} ✓")
    except Exception:
        st.warning("Tesseract not found - scanned drawings can't be read. Digital PDFs still work.\n\n"
                   "Install it (Windows: search 'UB Mannheim Tesseract'), then restart the UI. "
                   "If installed in an unusual folder, paste the full path to tesseract.exe in ⚙️ Settings.")

    run = st.button("▶ Extract", type="primary", width="stretch",
                    disabled=not (uploads or folder.strip()))
    if ss.results and st.button("🗑 Clear all results", width="stretch"):
        for k in ("results", "edited", "base", "nonce", "verified"):
            ss[k] = {}
        ss.zip_bytes = None
        ss.current = None
        st.rerun()

# ======================================================================
# run extraction
# ======================================================================
if run:
    wd = Path(ss.workdir)
    inputs: list[Path] = []
    for up in uploads or []:
        d = wd / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        target_name = Path(up.name).name
        stem = Path(target_name).stem
        ext = Path(target_name).suffix
        p = d / target_name
        counter = 1
        while p.exists() or p in inputs:
            p = d / f"{stem}_{counter}{ext}"
            counter += 1
        p.write_bytes(up.getbuffer())
        inputs.append(p)
    if folder.strip():
        try:
            inputs += discover_inputs([folder.strip().strip('"')])
        except FileNotFoundError:
            st.error(f"Path not found: {folder}")
    if not inputs:
        st.warning("No supported drawings found.")
    else:
        vocab_path = None
        if vocab is not None:
            vocab_path = wd / "vocab.yaml"
            vocab_path.write_bytes(vocab.getbuffer())
        ui_overrides = {"dpi": dpi, "cell_ocr": cell_ocr, "date_order": date_order,
                        "ocr_lang": lang.strip() or "eng",
                        "tesseract_cmd": tess.strip() or None,
                        "cad_layouts": cad_layouts,
                        "oda_converter": oda.strip().strip('"') or None,
                        "libredwg_path": libredwg.strip().strip('"') or None}
        if workers > 1:
            ui_overrides["_parallel"] = True
            ui_overrides["ocr_workers"] = 1
        cfg = load_config(vocab_path, ui_overrides)
        bar = st.progress(0.0, text=f"Processing {len(inputs)} drawing(s)…")
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {}
            for i, f in enumerate(inputs):
                key = f.name if f.name not in ss.results else f"{f.stem}_{i}{f.suffix}"
                out = wd / "overlays" / f"{i}_{f.stem}"
                futs[pool.submit(_run_one, f, cfg, force_ocr, out)] = (key, f)
            for fut in as_completed(futs):
                key, f = futs[fut]
                res, err = fut.result()
                ss.results[key] = {"res": res, "error": err, "path": str(f),
                                   "order": ss.seq + inputs.index(f)}
                ss.edited.pop(key, None)
                ss.verified.pop(key, None)
                done += 1
                bar.progress(done / len(inputs), text=f"{done}/{len(inputs)} done · {f.name}")
        ss.seq += len(inputs)
        bar.empty()
        st.toast(f"Finished {len(inputs)} drawing(s)", icon="✅")

# ======================================================================
# main area
# ======================================================================
if not ss.results:
    st.title("Drawing BOM & Material Extractor")
    st.markdown("""
**1.** Upload drawings in the sidebar (or type a folder path) → **2.** press **▶ Extract** →
**3.** check each drawing against its highlighted overlay, correct anything wrong directly in the tables,
tick **Verified** → **4.** download the Excel / CSV / JSON.

Works with digital PDFs, scanned PDFs, TIFF/PNG/JPG scans, and 2D CAD drawings (DWG, DXF). Extracts title block, BOM,
revisions, notes and material / surface finish / heat treatment callouts.
""")
    st.stop()

keys = sorted(ss.results, key=lambda k: ss.results[k].get("order", 0))  # stable input order
summaries = {k: _summary(k) for k in keys}

# overview + downloads are filled in at the end of the script so they always
# include the corrections made in the editors during this run
overview_box = st.container()
st.divider()

# ---------------- single drawing review
labels = {k: f"{_status_icon(summaries[k]['status'])}  {k}  ·  {summaries[k].get('drawing_number') or '—'}"
          for k in keys}
key = st.selectbox("Review drawing", keys, format_func=lambda k: labels[k])
entry = ss.results[key]
res = entry["res"]

if res is None:
    first = entry["error"].splitlines()[0]
    hint = ("The file looks damaged or is not a real PDF/image - try re-exporting or re-scanning it."
            if any(t in first for t in ("FileDataError", "cannot identify", "Failed to open", "UnidentifiedImage"))
            else "" if "Tesseract" in first
            else "Send the technical details below if you need help with this file.")
    st.error(f"Could not process **{key}**. {hint or first}")
    with st.expander("Technical details"):
        st.code(entry["error"])

if res is not None:
    # fresh editor widgets whenever a drawing is (re)opened, seeded with its latest edits
    if ss.current != key:
        ss.current = key
        ss.base[key] = {t: _table(key, t).copy() for t in TABLES}
        ss.nonce[key] = ss.nonce.get(key, 0) + 1
    base = ss.base[key]
    nonce = ss.nonce[key]
    s = summaries[key]

    h1, h2 = st.columns([3, 1])
    h1.markdown(f"### {s.get('drawing_number') or key} — {s.get('drawing_title') or ''}")
    h1.caption(f"Rev {s.get('revision') or '?'} · {s.get('author_date') or ''} · Scale {s.get('scale') or '?'} · "
               f"{s.get('projection') or ''} · {s['pages']} page(s) · {s['input_type']} · "
               f"{res.processing_seconds:.1f}s")
    ss.verified[key] = h2.toggle("✅ Verified", value=ss.verified.get(key, False),
                                 help="Tick after checking this drawing against the overlay")
    if s.get("review_reasons") and not ss.verified.get(key):
        st.warning(f"Check: {s['review_reasons']}")

    left, right = st.columns([1.05, 1])

    with left:
        pages = [p for p in res.pages if p.overlay_path and Path(p.overlay_path).exists()]
        if pages:
            pc1, pc2 = st.columns(2)
            pi = pc1.selectbox("Page", range(len(pages)), format_func=lambda i: f"Page {pages[i].index + 1}") \
                if len(pages) > 1 else 0
            page = pages[pi]
            kinds = ["Full page"] + list(dict.fromkeys(r.kind for r in page.regions))
            names = {"title_block": "Title block", "bom": "BOM", "revision": "Revisions", "notes": "Notes"}
            zoom = pc2.selectbox("Zoom to", kinds, format_func=lambda k: names.get(k, k))
            img = Image.open(page.overlay_path)
            if zoom != "Full page":
                sc = img.width / page.width
                boxes = [r.bbox for r in page.regions if r.kind == zoom]
                x0 = min(b[0] for b in boxes) * sc
                y0 = min(b[1] for b in boxes) * sc
                x1 = max(b[2] for b in boxes) * sc
                y1 = max(b[3] for b in boxes) * sc
                m = 40
                img = img.crop((max(0, x0 - m), max(0, y0 - m * 2), min(img.width, x1 + m), min(img.height, y1 + m)))
            st.image(img, width="stretch")
            st.caption("Blue = title block · Green = BOM · Orange = revisions · Purple = notes · "
                       "boxed text = material / finish / heat-treatment callouts · CHECK = BOM row to verify")
        if res.warnings:
            with st.expander(f"Warnings ({len(res.warnings)})"):
                for w in res.warnings:
                    st.write("• " + w)

    with right:
        t_tb, t_bom, t_spec, t_rev, t_notes = st.tabs(["Title block", f"BOM ({len(base['bom'])})", "Material & specs",
                                                       "Revisions", "Notes"])
        conf_col = st.column_config.ProgressColumn("confidence", min_value=0.0, max_value=1.0, format="%.2f")

        def editor(tab, table, **kw):
            df = base[table]
            hide = [c for c in ("drawing_number", "source_file") if c in df.columns]
            out = tab.data_editor(
                df, key=f"ed_{table}_{key}_{nonce}", width="stretch", hide_index=True,
                column_order=[c for c in df.columns if c not in hide],
                column_config={"confidence": conf_col, **kw.pop("column_config", {})}, **kw)
            ss.edited.setdefault(key, {})[table] = out
            return out

        with t_tb:
            st.caption("Edit the **value** column to correct a field.")
            editor(t_tb, "title_block", disabled=["field", "normalized", "confidence"])
        with t_bom:
            st.caption("Click any cell to correct it. Add / delete rows with the table toolbar. "
                       "Clear **flags** once a ⚠ row is checked.")
            editor(t_bom, "bom", num_rows="dynamic", disabled=["check", "confidence", "page"],
                   column_config={"check": st.column_config.TextColumn("", width="small"),
                                  "quantity_value": st.column_config.NumberColumn("qty (num)"),
                                  "mass_kg": st.column_config.NumberColumn("mass kg", format="%.3f")})
        with t_spec:
            summ = {"Material": s.get("material_callout"), "Surface finish": s.get("surface_finish"),
                    "Heat treatment": s.get("heat_treatment"), "Standards": s.get("standards")}
            for k_, v_ in summ.items():
                st.markdown(f"**{k_}:** {v_ or '—'}")
            editor(t_spec, "specs", num_rows="dynamic", disabled=["confidence", "page"])
        with t_rev:
            editor(t_rev, "revisions", num_rows="dynamic", disabled=["confidence", "page"])
        with t_notes:
            editor(t_notes, "notes", num_rows="dynamic", disabled=["confidence", "page"])


# ======================================================================
# overview & downloads (rendered into the top container, after edits)
# ======================================================================
summaries = {k: _summary(k) for k in keys}
with overview_box:
    n_rev = sum(1 for x in summaries.values() if x["status"] == "review")
    n_err = sum(1 for x in summaries.values() if x["status"] == "error")
    n_ver = sum(1 for x in summaries.values() if x["status"] == "verified")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Drawings", len(keys))
    c2.metric("Verified ✅", n_ver)
    c3.metric("Need review ⚠️", n_rev)
    c4.metric("Errors ❌", n_err)
    c5.metric("BOM rows", sum(len(_table(k, "bom")) for k in keys if ss.results[k]["res"]))

    with st.expander("📋 All drawings", expanded=len(keys) > 1):
        ov = pd.DataFrame([{"": _status_icon(x["status"]), **{c: ("" if x.get(c) is None else str(x.get(c))) for c in
                            ["file", "drawing_number", "drawing_title", "revision", "author_date",
                             "material_callout", "bom_items", "review_reasons"]}} for x in summaries.values()])
        st.dataframe(ov, hide_index=True, width="stretch")

    d1, d2, d3, d4 = st.columns(4)
    xl = _per_drawing_xlsx(keys)
    if len(xl) == 1:  # one drawing -> its own Excel
        d1.download_button("⬇ Excel (with corrections)", xl[0][1], xl[0][0],
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch", type="primary")
    elif xl:  # several drawings -> one Excel per drawing, delivered together in a ZIP
        d1.download_button(f"⬇ {len(xl)} Excels, one per drawing (ZIP)", _excels_zip(keys),
                           "bomx_excels.zip", "application/zip", width="stretch", type="primary")
    d2.download_button("⬇ BOM CSV", _bom_csv(keys), "bomx_bom.csv", "text/csv", width="stretch")
    d3.download_button("⬇ JSON", _json(keys), "bomx_results.json", "application/json", width="stretch")
    if d4.button("📦 Prepare ZIP (incl. overlays)", width="stretch"):
        ss.zip_bytes = _zip(keys)
    if ss.get("zip_bytes"):
        d4.download_button("⬇ Download ZIP", ss.zip_bytes, "bomx_results.zip", "application/zip",
                           width="stretch")
