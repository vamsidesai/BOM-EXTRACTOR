# bomx — Automated BOM & Engineering Drawing Data Extractor

A Python tool that reads legacy 2D engineering drawings (**DWG, DXF**, digital PDFs, scanned
PDFs, TIFF/PNG/JPG scans) and extracts **Bill of Materials tables, title-block metadata,
revision tables, general notes, and material / surface-finish / heat-treatment / standards
callouts**. Output goes to **Excel, CSV and JSON**, plus **visual validation overlays** that
highlight what was read and where, for human verification.

Regions are found automatically from the drawing's ruling-line structure and the
vocabulary printed on it. No pixel coordinates or per-template setup are needed.

---

## 1. SOW traceability

| SOW requirement | Where / how it is met |
|---|---|
| **2D CAD formats**: DWG and DXF | `cad.py`, `dwgjson.py`. See section 2b. |
| **Multi-format support**: scanned paper drawings and native digital PDFs | `ingest.py`. Image-only (scanned) PDF pages are read at the scan's own resolution and their scale is judged from the lettering, as for TIFF/PNG. Digital PDFs use the vector text layer (exact text, confidence 1.0). Scanned PDFs, TIFF (incl. multi-page), PNG, JPG and BMP go through OCR. A PDF page whose text is vectorised (SHX strokes) is detected and sent to OCR automatically. |
| **Automatic region detection** with no hard-coded coordinates | `layout.py`. Ruling lines are isolated morphologically and enclosed cells are found and grouped into tables. BOM and revision tables are recognised by their **header vocabulary** and grown row by row. The title block is the remaining cell cluster that carries title-block labels. Notes are found from a `NOTES` / `GENERAL NOTES` heading. Border zone markers are excluded. BOMs **without ruling lines** are handled by a text-alignment fallback. |
| **BOM table extraction**: Item, Part No, Description, Qty, Material, Mass, Remarks | `layout.py` + `extract.py`. Header synonyms (`SR NO`, `POS`, `P/N`, `PART #`, `NOMENCLATURE`, `MATL`, `WT (KG)` …) map to canonical fields. Units in headers are captured. Header-at-bottom (ISO) BOMs are re-ordered. Unknown columns are kept (`supplier`, `finish`, `size` …) or inferred from content. Quantities and masses are normalised (`4 NOS` → 4; `1450 g` → 1.45 kg). |
| **Material & spec extraction** (SS304, Al 6061-T6, A36, surface treatments, heat treatment, ASTM/ISO) | `specs.py`. Pattern library covering stainless, aluminium, carbon/alloy (ASTM, AISI/SAE, EN, IS 2062, C45, S355…), tool steel, cast iron, copper alloys, Ti, polymers and elastomers. Also anodising, plating, coatings, blasting, Ra/Rz/N-grade roughness, Q&T, case hardening, nitriding, normalising, annealing, HRC/HB/HV hardness, and ASTM/ISO/DIN/EN/SAE/ASME/JIS/BS/IS/MIL standards. Sources searched: notes, title-block fields, BOM material column, and loose drawing text. |
| **Title block & metadata**: Drawing No, Title, Revision, Drawn By, Date, Scale, Projection | `extract.parse_title_block`. Supports `LABEL value`, `LABEL: value`, a label cell with its value in the next cell to the right or below, and several labels in one cell. Also picks up checked/approved by + dates, sheet, size, weight, material, finish, tolerance, units and company. Dates are normalised to ISO. The title-block revision is cross-checked against the latest revision-table row. |
| **Flexible outputs**: xlsx, CSV, JSON + overlays | `export.py`, `overlay.py`. One folder (and one Excel) per drawing, plus `consolidated_bom.csv` / `consolidated_summary.csv` / `batch_report.json` for batches. |
| **Section 3 target attributes** (DWG-2026-8891-R2, MAIN DRIVE SHAFT ASSEMBLY, REV C, J. DOE / 2024-08-15, PN-4402-A, HEX HEAD BOLT M12x50, 4, Stainless Steel 316L, ASTM A36 Structural Steel, Anodized Clear / Ra 1.6 µm, Quenched & Tempered 55 HRC) | All of these are reproduced exactly from the sample drawing, asserted in `tests/test_bomx.py::test_sow_sample_values`. |

Beyond the SOW: **confidence scores** on every field and row; **review flags** (missing part
number, non-numeric quantity, duplicate or missing item numbers, low OCR confidence,
title/revision mismatch) so uncertain data is surfaced rather than silently imported;
automatic **deskew** and **90°/180°/270° orientation** correction; **parallel batch
processing**; editable **YAML vocabulary**; and a Python API.

---

## 2. Installation

**Python 3.10+** and the **Tesseract OCR engine** (needed for scanned drawings; digital
PDFs work without it).

```bash
pip install -r requirements.txt        # or:  pip install .   (installs the `bomx` command)
```

Tesseract:
- **Windows**: install from the UB-Mannheim build (github.com/UB-Mannheim/tesseract/wiki).
  Either add it to PATH or pass `--tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe"`.
- **Ubuntu/Debian**: `sudo apt install tesseract-ocr`
- **macOS**: `brew install tesseract`

Check the setup with `bomx check` (or `python -m bomx check`).

---

## 2b. DWG and DXF drawings

**What happens to a CAD file**

| Drawing contains | How it is read | Confidence |
|---|---|---|
| Real text entities (TEXT, MTEXT, block attributes, dimension text, tables) | Words come straight from the CAD entities with exact positions. No OCR. | 1.0 |
| Title block stored as block attributes (`DWG_NO`, `TITLE`, `REV`, `DRAWN`, `DATE`, `SCALE` ...) | Tags are mapped to title-block fields. They fill anything the layout analysis did not find. A disagreement is reported in Warnings. | 1.0 |
| No text at all: a raster scan traced to vector outlines (common for legacy archives) | Detected automatically (`dxf-traced` / `dwg-traced`), rendered **filled** at 400 dpi from the vectors, then OCR'd like a scan. Faint rules that the trace reduced to dashes are repaired, and their specks are kept away from OCR. | OCR |

- **Layouts.** By default (`--cad-layouts auto`) paper-space sheets are read if the drawing has
  them (text seen through viewports included). Otherwise model space is read. Use `model`, `paper`
  or `all` to override. Each layout becomes one page.
- **Units and scale** don't matter. The render resolution comes from the drawing's own lettering,
  so a drawing in mm, inches or scanner pixels gives the same result.
- Far-away stray objects (a block left at the origin, a construction line miles off) are ignored
  when framing the sheet.

**DWG converters** (DXF needs none). bomx uses the first one it finds:

1. **ODA File Converter** (free, best fidelity). Install from opendesign.com
   (`guestfiles/oda_file_converter`). It is found automatically in `C:\Program Files\ODA\...`;
   otherwise pass `--oda PATH`.
2. **LibreDWG** (free, open source). Download the Windows zip from
   github.com/LibreDWG/libredwg/releases and pass the folder with `--libredwg PATH` (or put
   `dwgread` on PATH). LibreDWG's DXF export can silently drop most of an older drawing (seen
   on R14 files), so bomx also reads its JSON dump and restores every missing entity by handle.
3. **aspose-cad** (commercial, optional). Render-only fallback: text is OCR'd. Unlicensed copies
   stamp an evaluation watermark.

`bomx check` lists what is installed. Without a converter, a DWG fails with a clear message. You
can also save it as DXF from your CAD program.

Extra title-block attribute tags can be added in the vocabulary file under `cad_attribute_tags`.

---

## 3. Usage

```bash
# one drawing
bomx extract drawing.pdf -o results/

# a whole folder (recursive), 4 parallel processes
bomx extract D:/legacy_drawings -o results/ -w 4

# only Excel + JSON, no overlay images, US date order
bomx extract scans/ -o out -f xlsx,json --no-overlay --date-order mdy
```

| Option | Meaning |
|---|---|
| `-o DIR` | output folder (default `bomx_output`) |
| `-f xlsx,csv,json` | output formats |
| `-w N` | parallel worker processes for batches |
| `-c vocab.yaml` | custom vocabulary/settings (see §5) |
| `--dpi 300` | render/OCR resolution |
| `--lang eng+deu` | Tesseract language packs |
| `--force-ocr` | ignore a PDF's text layer and OCR the image |
| `--no-cell-ocr` | faster, slightly less accurate on scans |
| `--no-deskew`, `--no-rotate` | disable skew / orientation correction |
| `--tesseract PATH` | Tesseract executable if not on PATH |
| `--cad-layouts auto\|model\|paper\|all` | which DWG/DXF layouts to read |
| `--dwg-converter auto\|oda\|libredwg\|aspose` | force a DWG reader |
| `--oda PATH`, `--libredwg PATH` | DWG converter locations |

Python API:

```python
from bomx import extract
res = extract("drawing.pdf", overlay_dir="out")
print(res.summary["drawing_number"], res.summary["material_callout"])
for row in res.bom:
    print(row.item, row.part_number, row.description, row.quantity_value, row.mass_kg, row.flags)
```

---

## 3b. Web interface

```bash
python -m bomx ui          # opens http://localhost:8501 in your browser
```

- **Sidebar**: upload drawings (or type a folder path on this computer), adjust settings, press **▶ Extract**.
- **Top**: counts (verified / need review / errors), a table of all drawings, and download buttons
  (Excel, BOM CSV, JSON, ZIP with overlays). Downloads **include your manual corrections**.
- **Review drawing**: pick a drawing. The left side shows the highlighted overlay (zoom to BOM / title
  block / revisions / notes). The right side has editable tabs for title block, BOM, material & specs,
  revisions and notes. Fix any cell, add or delete rows, clear a row's `flags` once checked, and
  toggle **✅ Verified**.
- Stop the UI with `Ctrl+C` in the terminal.

Everything runs locally. Drawings are not sent anywhere.

## 4. Outputs

Per drawing (`out/<drawing>/`; a single input writes directly into `out/`):

| File | Content |
|---|---|
| `<name>.xlsx` | Sheets: **Extraction** (the SOW attribute table: Attribute Category · Target Field Name · Description · Extracted Output; BOM attributes list every line, one per item) · **Summary · BOM · Title Block · Material & Specs · Revisions · Notes · Warnings**. Flagged rows are shaded yellow and low-confidence cells red. Headers are frozen and filters on. |
| `<name>_bom.csv` | ERP-ready BOM: `drawing_number, item, part_number, description, quantity, material, mass, remarks, quantity_value, mass_kg, <extra columns>, confidence, flags` |
| `<name>_title_block.csv`, `_specs.csv`, `_revisions.csv`, `_notes.csv` | the other record types |
| `<name>.json` | everything, including bounding boxes and per-page processing info |
| `<name>_p<N>_overlay.png` | validation overlay. Colours: title block blue, BOM green, revisions orange, notes purple, material/finish/heat-treatment callouts boxed, flagged BOM rows marked **CHECK**. |

Each drawing always gets its own Excel; drawings are never merged into one workbook. In the web
interface, several drawings download as a ZIP of per-drawing Excels. For batches the output folder
also gets `consolidated_bom.csv`, `consolidated_summary.csv` and `batch_report.json`
(status per file: `ok` / `review` / `error`). One unreadable file doesn't stop the batch.

**Review policy:** a drawing is marked `review_required` when a key title field is missing,
a title field has low confidence, any BOM row is flagged, or no BOM was found. Filter on
that column before importing into ERP/PLM.

---

## 5. Customising the vocabulary

Every company writes its headers differently. Dump the defaults, edit them, and pass them back:

```bash
bomx dump-config my_vocab.yaml
# e.g. add "BAUTEIL" to bom_headers.description, or "ZEICHNUNGSNR" to title_labels.drawing_number
bomx extract drawings/ -o out -c my_vocab.yaml
```

A list in your YAML replaces the default list for that field. Settings such as `dpi`,
`min_word_conf`, `low_conf_threshold` and `date_order` live in the same file.

---

## 6. How it works

1. **Ingest**: PDF pages are rendered (PyMuPDF). If the page has a real text layer, those
   words are used directly. Otherwise the page is treated as a scan.
2. **Pre-process (scans)**: Tesseract OSD orientation (with an OCR-quality fallback when
   OSD is unsure), then deskew from the long ruling lines, then adaptive binarisation.
3. **Ruling lines and cells**: horizontal and vertical lines are isolated morphologically.
   Short segments are kept only if they meet a perpendicular rule, so the strokes of large
   lettering aren't mistaken for lines. Enclosed rectangles become cells. The drawing frame
   is found, and zone-marker strips outside it are ignored.
4. **OCR (scans)**: lines are erased, then the page is OCR'd. Each table cell is then
   re-read individually (ink-cropped, single-line, sparse or single-character mode as
   appropriate). Numeric columns are re-read with a digit whitelist when needed.
5. **Region classification**: BOM and revision headers are matched (fuzzy, unit-aware and
   OCR-confusion-tolerant). Tables grow row by row from the header; row rules lost in a
   scan are reconstructed. The title block is the remaining labelled cluster. Notes come
   from the NOTES heading.
6. **Field extraction and normalisation**: label/value pairing, ISO dates, scale, projection,
   quantity/mass parsing, spec pattern matching, and validation flags.
7. **Export and overlays.**

---

## 7. Measured accuracy

`tests/make_samples.py` generates drawings with known ground truth. `tests/evaluate.py`
scores every title-block field, every BOM cell, the revision list and the headline specs.

| Sample | Type | Fields correct |
|---|---|---|
| drawing1_shaft_assembly | digital PDF, ISO bottom-header BOM attached to title block | 68 / 68 |
| drawing2_pivot_bracket | digital PDF, top-header BOM, label/value grid title block, IS grades | 48 / 48 |
| drawing3_lineless_bom | digital PDF, BOM **without ruling lines** | 28 / 28 |
| drawing4_scanned_two_sheets | **image-only 2-page PDF, 200 dpi**, caption row, reordered columns (held out during development) | 56 / 56 |
| drawing1_scan_skewed | TIFF, 250 dpi, 0.8° skew, noise | 68 / 68 |
| drawing2_scan_rotated | PNG, rotated 90°, noise | 48 / 48 |
| **Stress set** (`--stress`): 150–300 dpi, 1.5° skew, 180°/270° rotation, heavy noise | | 228 / 232 (98.3%) |

The remaining stress-set errors are character-level OCR misreads (e.g. `SSS304`, scale
`1:35`). They are flagged as low-confidence for review, not passed through silently.

Run it yourself:

```bash
python tests/make_samples.py samples --stress
bomx extract samples -o results -w 4 && python tests/evaluate.py samples results
pytest -q tests/
```

> These are synthetic drawings. Before production, run a pilot on 30–50 of your own
> drawings and extend the vocabulary file with your company's header and label wording.
> That's where real-world accuracy is won.

---

### Legacy raster drawings (screenshots, phone photos, exported PNG/JPG)

- Images that carry a screen resolution (72/96 dpi) or no DPI at all are measured from the size of
  their lettering, and the drawing's real scale is used instead (logged in Warnings).
- Ruling lines that stop a little short of the line they should meet (hand-drawn or faded
  tables) are bridged, so adjacent cells such as REV / SCALE / SHEET are read separately.
- Combined labels such as `DRAWN BY / DATE: J. DOE / 2024-08-15` are split into name and date.
- Notes headings `TECHNICAL NOTES`, `GENERAL NOTES` etc. are recognised even when the underline
  splits the heading. Unnumbered notes after a numbered list are kept as their own notes.
- A note or title-block field that is labelled `MATERIAL` / `MATERIAL CALLOUT`, `SURFACE FINISH`
  / `FINISH`, or `HEAT TREATMENT` is reported **as written** in the summary. Pattern matching
  is used only when no labelled callout exists. The individual recognised specs are still
  listed in the Material & Specs sheet.

### Damaged tables (faint scans, traced drawings)

- A row whose separating rule was lost entirely is split when its item cell holds several stacked
  item numbers. A cell whose column rule was lost is shared between the columns by word
  position. A cell whose rules are all missing is filled from the text inside the row × column box.
  Every reconstructed cell is then re-read with OCR as its exact box.
- Text that overflows its cell (long CAD text, substituted fonts) stays with the cell it starts in.
- A title block whose rules are too broken to form cells is read from the text layout:
  label (`DRAWING NO:`) plus the value on its line or directly below.
- Letter/digit confusions that only make sense one way are repaired in OCR'd tables and notes:
  thread sizes (`M10x4S` → `M10x45`), decimals with units (`7.SkW` → `7.5kW`), `kq` → `kg`,
  `1SO-` → `ISO-`, RAL colour codes. Part numbers and words are not touched.
- List numbers set in their own column (`1.` `2.` ...) are recovered with a block-mode re-read
  of the notes.

## 8. Known limitations

- **CAD text exploded into lines or traced outlines** is read by OCR, so it is only as good as the
  lettering. A glyph destroyed by the trace (for example, the REV letter in the sample
  `tests/data/legacy/legacy_3.dwg`) is reported missing and flagged for review, never guessed.
- **CAD fonts**: SHX fonts are replaced by a TrueType font when rendering. Words keep their exact
  text; only the drawn glyph shapes in the overlay differ.
- **ACIS solids, 3D views, proxy objects without graphics** are not drawn (2D drawings only).

- **Projection symbol**: projection is read from text (`THIRD ANGLE PROJECTION`, or a
  `PROJECTION` label). The truncated-cone symbol alone isn't interpreted, and the field is
  then left empty.
- **Handwriting** and very poor scans (< 150 dpi, heavy bleed-through) reduce OCR accuracy.
  Such fields are flagged low-confidence.
- **Two-level (stacked) BOM headers** are read using the lower header row.
- **GD&T frames and weld symbols** are not interpreted. Roughness is captured only where
  written as text (`Ra 1.6`).
- **Lineless BOMs** use alignment heuristics. They're flagged in Warnings so the column
  assignment gets a quick check.
- Non-English drawings need the matching Tesseract language pack (`--lang`) and
  vocabulary entries.

---

## 9. Project layout

```
bomx/
  cli.py        command line (extract / dump-config / check), batch + parallelism
  pipeline.py   per-page orchestration, multi-page merge, summary & review logic
  ingest.py     PDF / image / CAD loading, native text layer detection, scanned-PDF resolution
  cad.py        DXF/DWG: layout choice, rendering, exact CAD text, traced-drawing detection,
                block-attribute title blocks, DWG converters (ODA / LibreDWG / aspose)
  dwgjson.py    restores entities LibreDWG's DXF export drops, from its JSON dump
  imaging.py    orientation, deskew, binarisation, ruling lines, Tesseract wrappers
  layout.py     cells, grouping, BOM/revision table detection, lineless tables, notes
  extract.py    title-block pairing, BOM/revision normalisation, dates, units
  specs.py      material / finish / heat-treatment / standards pattern library
  export.py     xlsx / csv / json writers
  overlay.py    validation overlay rendering
  config.py     default vocabulary & settings (YAML-overridable)
  models.py     data classes
tests/
  make_samples.py   synthetic drawings + ground truth (+ --stress set)
  make_cad_samples.py  the same drawings as native DXF (model/paper space, MTEXT, block attributes)
  test_cad.py       DWG / DXF / scanned-PDF tests, including the legacy samples in data/legacy/
  evaluate.py       accuracy scoring
  test_bomx.py      pytest suite
```
