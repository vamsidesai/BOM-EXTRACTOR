"""Generate synthetic engineering drawings (vector PDF + degraded scans) with
known ground truth, for testing and demos.

    python tests/make_samples.py samples/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter

MM = 72 / 25.4
A3 = (420 * MM, 297 * MM)
A4L = (297 * MM, 210 * MM)


class Sheet:
    def __init__(self, size):
        self.doc = pymupdf.open()
        self.page = self.doc.new_page(width=size[0], height=size[1])
        self.W, self.H = size[0] / MM, size[1] / MM

    def line(self, x0, y0, x1, y1, w=0.5):
        self.page.draw_line((x0 * MM, y0 * MM), (x1 * MM, y1 * MM), width=w * MM / 2.5)

    def rect(self, x0, y0, x1, y1, w=0.5):
        self.page.draw_rect(pymupdf.Rect(x0 * MM, y0 * MM, x1 * MM, y1 * MM), width=w * MM / 2.5)

    def circle(self, cx, cy, r, w=0.5):
        self.page.draw_circle((cx * MM, cy * MM), r * MM, width=w * MM / 2.5)

    def text(self, x, y, s, size=2.5, bold=False):
        """x,y = left/baseline in mm; size = text height in mm."""
        self.page.insert_text((x * MM, y * MM), s, fontsize=size * MM * 1.35,
                              fontname="hebo" if bold else "helv")

    def ctext(self, x0, x1, y, s, size=2.5, bold=False):
        fs = size * MM * 1.35
        w = pymupdf.get_text_length(s, fontname="hebo" if bold else "helv", fontsize=fs) / MM
        self.text((x0 + x1) / 2 - w / 2, y, s, size, bold)

    def frame(self, zones=True):
        W, H = self.W, self.H
        self.rect(5, 5, W - 5, H - 5, 0.35)
        self.rect(15, 10, W - 10, H - 10, 0.7)
        if zones:
            nx, ny = 8, 6
            for i in range(nx + 1):
                x = 15 + (W - 25) * i / nx
                self.line(x, 5, x, 10, 0.35)
                self.line(x, H - 10, x, H - 5, 0.35)
                if i < nx:
                    xm = 15 + (W - 25) * (i + 0.5) / nx
                    self.ctext(xm - 2, xm + 2, 8.8, str(i + 1), 2.5)
                    self.ctext(xm - 2, xm + 2, H - 6.2, str(i + 1), 2.5)
            for j in range(ny + 1):
                y = 10 + (H - 20) * j / ny
                self.line(5, y, 15, y, 0.35)
                self.line(W - 10, y, W - 5, y, 0.35)
                if j < ny:
                    ym = 10 + (H - 20) * (j + 0.5) / ny
                    self.ctext(5, 15, ym + 1.2, "ABCDEFGH"[j], 2.5)
                    self.ctext(W - 10, W - 5, ym + 1.2, "ABCDEFGH"[j], 2.5)

    def table(self, x0, y0, col_w, row_h, rows, size=2.5, header_rows=(), aligns=None):
        """Grid table; rows = list of lists of strings (top to bottom)."""
        x1 = x0 + sum(col_w)
        y = y0
        self.line(x0, y0, x1, y0)
        for r, row in enumerate(rows):
            h = row_h[r] if isinstance(row_h, list) else row_h
            xs = x0
            for c, s in enumerate(row):
                w = col_w[c]
                bold = r in header_rows
                if s:
                    if aligns and aligns[c] == "l" and not bold:
                        self.text(xs + 1.5, y + h / 2 + size * 0.45, s, size, bold)
                    else:
                        self.ctext(xs, xs + w, y + h / 2 + size * 0.45, s, size, bold)
                xs += w
            y += h
            self.line(x0, y, x1, y)
        xs = x0
        for w in [0] + col_w:
            xs += w
            self.line(xs, y0, xs, y)
        return y

    def save(self, path):
        self.doc.save(str(path))
        self.doc.close()


def part_view(s: Sheet, x, y):
    """A simple shaft-like part with dimensions (to act as drawing clutter)."""
    s.rect(x, y + 10, x + 40, y + 30, 0.7)
    s.rect(x + 40, y + 5, x + 110, y + 35, 0.7)
    s.rect(x + 110, y + 12, x + 150, y + 28, 0.7)
    s.line(x - 5, y + 20, x + 155, y + 20, 0.25)
    s.line(x, y + 45, x + 150, y + 45, 0.25)
    s.ctext(x, x + 150, y + 43.5, "250", 3.5)
    s.text(x + 58, y + 3, "Ø40 h6", 3.5)
    s.text(x + 112, y + 9, "Ø25 k6", 3.5)
    s.circle(x + 200, y + 20, 18, 0.7)
    s.circle(x + 200, y + 20, 8, 0.7)
    s.text(x + 222, y + 6, "Ra 0.8", 3.0)


# ======================================================================
def drawing_1(out: Path):
    s = Sheet(A3)
    s.frame()
    W, H = s.W, s.H
    part_view(s, 40, 60)

    s.text(25, 22, "NOTES:", 3.5, bold=True)
    notes = ["1. MATERIAL: ASTM A36 STRUCTURAL STEEL UNLESS OTHERWISE SPECIFIED.",
             "2. SHAFT ITEM 02 TO BE QUENCHED & TEMPERED TO 55 HRC.",
             "3. HOUSINGS: ANODIZED CLEAR TYPE II PER MIL-A-8625.",
             "4. SURFACE ROUGHNESS Ra 1.6 um ON BEARING SEATS UNLESS STATED.",
             "5. GENERAL TOLERANCES AS PER ISO 2768-mK.",
             "6. REMOVE ALL BURRS AND BREAK SHARP EDGES 0.5 x 45°."]
    for i, n in enumerate(notes):
        s.text(25, 29 + i * 5.2, n, 2.8)

    # revision table, top right
    rx = W - 10 - 150
    s.table(rx, 10, [12, 90, 25, 23], 6,
            [["REV", "DESCRIPTION", "DATE", "APPROVED"],
             ["A", "INITIAL RELEASE", "2024-03-02", "RK"],
             ["B", "BEARING HOUSING MATERIAL UPDATED", "2024-05-19", "RK"],
             ["C", "SHAFT HEAT TREATMENT ADDED", "2024-08-15", "RK"]],
            header_rows=(0,), aligns=["c", "l", "c", "c"])

    # title block, bottom right (180 wide)
    tx0, tx1 = W - 10 - 180, W - 10
    ty1 = H - 10
    s.rect(tx0, ty1 - 56, tx1, ty1, 0.7)
    # row 1: company
    s.line(tx0, ty1 - 48, tx1, ty1 - 48)
    s.text(tx0 + 2, ty1 - 51, "ACME DRIVE SYSTEMS PVT LTD", 3.5, bold=True)
    # row 2: title
    s.line(tx0, ty1 - 34, tx1, ty1 - 34)
    s.text(tx0 + 2, ty1 - 44.5, "TITLE:", 2.0)
    s.text(tx0 + 25, ty1 - 38.5, "MAIN DRIVE SHAFT ASSEMBLY", 5.0, bold=True)
    # rows 3-5: people grid + dwg no / rev
    for k, (lab, name, date) in enumerate([("DRAWN BY", "J. DOE", "2024-08-15"),
                                           ("CHECKED", "A. SMITH", "2024-08-20"),
                                           ("APPROVED", "R. KUMAR", "2024-08-22")]):
        y0 = ty1 - 34 + k * 8
        s.line(tx0, y0 + 8, tx0 + 90, y0 + 8)
        s.text(tx0 + 2, y0 + 5.3, lab, 2.5)
        s.text(tx0 + 27, y0 + 5.3, name, 2.5)
        s.text(tx0 + 62, y0 + 5.3, date, 2.5)
    for x in (tx0 + 25, tx0 + 60, tx0 + 90):
        s.line(x, ty1 - 34, x, ty1 - 10)
    s.line(tx0 + 90, ty1 - 22, tx1, ty1 - 22)
    s.line(tx0 + 155, ty1 - 34, tx0 + 155, ty1 - 22)
    s.text(tx0 + 92, ty1 - 31, "DWG NO.", 2.0)
    s.text(tx0 + 96, ty1 - 24.5, "DWG-2026-8891-R2", 4.0, bold=True)
    s.text(tx0 + 157, ty1 - 31, "REV", 2.0)
    s.text(tx0 + 164, ty1 - 24.5, "C", 4.5, bold=True)
    s.line(tx0 + 130, ty1 - 22, tx0 + 130, ty1 - 10)
    s.text(tx0 + 92, ty1 - 14.5, "SCALE 1:2", 2.8)
    s.text(tx0 + 132, ty1 - 14.5, "SHEET 1 OF 1", 2.8)
    # bottom row
    s.line(tx0, ty1 - 10, tx1, ty1 - 10)
    s.line(tx0 + 60, ty1 - 10, tx0 + 60, ty1)
    s.line(tx0 + 110, ty1 - 10, tx0 + 110, ty1)
    s.text(tx0 + 2, ty1 - 3.5, "THIRD ANGLE PROJECTION", 2.5)
    s.text(tx0 + 62, ty1 - 3.5, "SIZE A3", 2.5)
    s.text(tx0 + 112, ty1 - 3.5, "WEIGHT: 18.6 kg", 2.5)

    # BOM above title block, header at the bottom (ISO 7573 style)
    bom = [
        ["01", "PN-4402-A", "HEX HEAD BOLT M12x50", "4", "Stainless Steel 316L", "0.06", "ISO 4017"],
        ["02", "PN-1001-S", "MAIN DRIVE SHAFT", "1", "EN19", "4.20", "Q&T 55 HRC"],
        ["03", "PN-2210-H", "BEARING HOUSING", "2", "AL 6061-T6", "1.45", "ANODIZED"],
        ["04", "SKF-6205-2RS", "DEEP GROOVE BALL BEARING", "2", "", "0.13", "BOUGHT OUT"],
        ["05", "PN-3300-K", "PARALLEL KEY 8x7x40", "1", "C45", "0.02", ""],
        ["06", "PN-4410-W", "PLAIN WASHER M12", "4", "SS304", "0.01", "ISO 7089"],
        ["07", "PN-5520-C", "END COVER", "2", "ASTM A36", "0.85", "POWDER COATED"],
        ["08", "PN-6001-G", "GASKET", "2", "NBR", "0.01", ""],
    ]
    header = ["ITEM", "PART NO.", "DESCRIPTION", "QTY", "MATERIAL", "MASS (kg)", "REMARKS"]
    cw = [12, 26, 52, 10, 32, 16, 32]
    rows = list(reversed(bom)) + [header]
    rh = 6.5
    y0 = ty1 - 56 - rh * len(rows)
    s.table(tx0, y0, cw, rh, rows, size=2.5, header_rows=(len(rows) - 1,),
            aligns=["c", "l", "l", "c", "l", "c", "l"])
    s.save(out / "drawing1_shaft_assembly.pdf")

    return {
        "file": "drawing1_shaft_assembly",
        "title_block": {"drawing_number": "DWG-2026-8891-R2", "drawing_title": "MAIN DRIVE SHAFT ASSEMBLY",
                        "revision": "C", "drawn_by": "J. DOE", "date": "2024-08-15", "scale": "1:2",
                        "projection": "THIRD ANGLE", "sheet": "1 OF 1"},
        "bom": [dict(zip(["item", "part_number", "description", "quantity", "material", "mass", "remarks"], r))
                for r in bom],
        "revisions": ["A", "B", "C"],
        "specs": {"material_callout": "ASTM A36", "surface_finish": ["ANODIZED", "Ra 1.6"],
                  "heat_treatment": ["QUENCHED & TEMPERED", "55 HRC"]},
    }


# ======================================================================
def drawing_2(out: Path):
    """Different conventions: header-at-top BOM, label/value columns, Indian grades."""
    s = Sheet(A3)
    s.frame(zones=False)
    W, H = s.W, s.H
    part_view(s, 30, 120)

    # BOM top right, header at top
    bom = [
        ["1", "QG-BR-101", "MOUNTING BRACKET", "2", "IS 2062 E250", "1.20"],
        ["2", "QG-PL-102", "BASE PLATE 10 THK", "1", "IS 2062 E250", "3.85"],
        ["3", "QG-PN-103", "PIVOT PIN DIA 20", "2", "EN8", "0.25"],
        ["4", "QG-BS-104", "BUSH", "2", "PHOSPHOR BRONZE", "0.08"],
        ["5", "QG-CV-105", "SHEET METAL COVER", "1", "CRCA 1.6", "0.62"],
        ["6", "M10x30-8.8", "HEX BOLT M10x30 GR 8.8", "8", "", "0.03"],
    ]
    header = ["SR NO", "PART NUMBER", "PART NAME", "QTY", "MATL", "WT (KG)"]
    cw = [14, 30, 48, 12, 40, 16]
    bx = W - 10 - sum(cw)
    s.table(bx, 18, cw, 7, [["BILL OF MATERIALS", "", "", "", "", ""]][:0] + [header] + bom,
            size=2.5, header_rows=(0,), aligns=["c", "l", "l", "c", "l", "c"])

    s.text(25, 22, "GENERAL NOTES", 3.5, bold=True)
    notes = ["1. ALL WELDS TO BE CONTINUOUS FILLET 6 MM UNLESS NOTED.",
             "2. PIVOT PIN: CASE CARBURIZED, CASE DEPTH 0.8-1.2 MM, 58-62 HRC.",
             "3. FINISH: ZINC PLATED 8-12 MICRONS WITH YELLOW PASSIVATION.",
             "4. ALL DIMENSIONS ARE IN MM."]
    for i, n in enumerate(notes):
        s.text(25, 29 + i * 5.5, n, 2.8)

    # title block: separate label cells and value cells
    tx0, tx1 = W - 10 - 170, W - 10
    ty0, ty1 = H - 10 - 48, H - 10
    rows = [["", "NAME", "DATE", "TITLE"],
            ["DRAWN", "M. KUMAR", "12/09/2025", ""],
            ["CHECKED", "S. RAO", "15/09/2025", ""],
            ["APPROVED", "P. SINGH", "18/09/2025", ""]]
    cw2 = [22, 30, 28]
    s.table(tx0, ty0, cw2, 8, [r[:3] for r in rows], size=2.5)
    # right part: title, dwg no, rev, scale
    s.rect(tx0 + 80, ty0, tx1, ty0 + 32)
    s.text(tx0 + 82, ty0 + 4, "TITLE", 2.0)
    s.text(tx0 + 84, ty0 + 14, "PIVOT BRACKET WELDMENT", 4.5, bold=True)
    s.rect(tx0, ty0 + 32, tx1, ty1)
    s.line(tx0 + 60, ty0 + 32, tx0 + 60, ty1)
    s.line(tx0 + 130, ty0 + 32, tx0 + 130, ty1)
    s.line(tx0 + 150, ty0 + 32, tx0 + 150, ty1)
    s.text(tx0 + 2, ty0 + 36, "DRG NO", 2.0)
    s.text(tx0 + 4, ty0 + 44, "QG-WLD-2025-014", 3.5, bold=True)
    s.text(tx0 + 62, ty0 + 36, "MATERIAL", 2.0)
    s.text(tx0 + 64, ty0 + 44, "IS 2062 E250", 3.0)
    s.text(tx0 + 132, ty0 + 36, "SCALE", 2.0)
    s.text(tx0 + 134, ty0 + 44, "1:5", 3.0)
    s.text(tx0 + 152, ty0 + 36, "REV", 2.0)
    s.text(tx0 + 156, ty0 + 44, "02", 3.0)
    s.text(25, H - 14, "FIRST ANGLE PROJECTION", 3.0)
    s.save(out / "drawing2_pivot_bracket.pdf")

    return {
        "file": "drawing2_pivot_bracket",
        "title_block": {"drawing_number": "QG-WLD-2025-014", "drawing_title": "PIVOT BRACKET WELDMENT",
                        "revision": "02", "drawn_by": "M. KUMAR", "date": "2025-09-12", "scale": "1:5",
                        "projection": "FIRST ANGLE"},
        "bom": [dict(zip(["item", "part_number", "description", "quantity", "material", "mass"], r)) for r in bom],
        "revisions": [],
        "specs": {"material_callout": "IS 2062 E250", "surface_finish": ["ZINC PLATED"],
                  "heat_treatment": ["CASE CARBURIZED", "58-62 HRC"]},
    }


# ======================================================================
def drawing_3(out: Path):
    """BOM without ruling lines (text columns only), A4 landscape."""
    s = Sheet(A4L)
    s.frame(zones=False)
    W, H = s.W, s.H
    s.rect(40, 40, 120, 90, 0.7)
    s.circle(80, 65, 12, 0.7)
    x = [150, 162, 192, 240, 252]
    y = 30
    for xx, h in zip(x, ["ITEM", "PART NO", "DESCRIPTION", "QTY", "MATERIAL"]):
        s.text(xx, y, h, 2.5, bold=True)
    s.line(148, y + 1.5, 287, y + 1.5, 0.35)
    data = [["1", "VB-110", "VALVE BODY", "1", "SS316"],
            ["2", "VB-120", "BONNET", "1", "SS316"],
            ["3", "VB-130", "STEM", "1", "17-4 PH H1150"],
            ["4", "VB-140", "O-RING 20x2", "2", "VITON"]]
    for i, row in enumerate(data):
        for xx, v in zip(x, row):
            s.text(xx, y + 7 + i * 5.5, v, 2.5)
    # simple title block
    tx0, ty0 = W - 10 - 120, H - 10 - 24
    s.table(tx0, ty0, [60, 60], 8, [["DWG NO: VB-ASSY-300", "REV: A"],
                                     ["TITLE: BALL VALVE ASSY", "SCALE: 1:1"],
                                     ["DRAWN BY: L. CHEN", "DATE: 03-JUN-2023"]], size=2.5,
            aligns=["l", "l"])
    s.save(out / "drawing3_lineless_bom.pdf")
    return {
        "file": "drawing3_lineless_bom",
        "title_block": {"drawing_number": "VB-ASSY-300", "drawing_title": "BALL VALVE ASSY", "revision": "A",
                        "drawn_by": "L. CHEN", "date": "2023-06-03", "scale": "1:1"},
        "bom": [dict(zip(["item", "part_number", "description", "quantity", "material"], r)) for r in data],
        "revisions": [],
        "specs": {},
    }


# ======================================================================
def drawing_4(out: Path):
    """Held-out conventions: 2-page sheet set, caption row, QTY before DESCRIPTION,
    POS / PART # / WEIGHT headers, DRG. NO. label, '05 AUG 2024' dates."""
    doc = pymupdf.open()
    truth_bom = []
    pages = [
        [["1", "2", "SUPPORT LEG", "HC-210", "S355JR", "6.4"],
         ["2", "1", "TOP FRAME WELDMENT", "HC-220", "S355JR", "21.0"],
         ["3", "4", "LEVELLING FOOT M16", "STD-LF-16", "ZINC PLATED STEEL", "0.35"],
         ["4", "1", "GUARD PANEL", "HC-240", "AL 5052-H32", "2.9"]],
        [["5", "8", "SOCKET HEAD CAP SCREW M8x25", "ISO 4762", "CLASS 12.9", "0.02"],
         ["6", "2", "LIFTING EYE", "HC-260", "C45", "0.6"],
         ["7", "1", "NAME PLATE", "HC-270", "SS304", "0.05"]],
    ]
    for pg, rows in enumerate(pages, 1):
        s = Sheet.__new__(Sheet)
        s.doc = doc
        s.page = doc.new_page(width=A3[0], height=A3[1])
        s.W, s.H = A3[0] / MM, A3[1] / MM
        s.frame(zones=False)
        W, H = s.W, s.H
        if pg == 1:
            part_view(s, 40, 70)
            s.text(25, 24, "NOTES:", 3.5, bold=True)
            for i, n in enumerate(["1. FRAME MATERIAL S355JR TO EN 10025-2.",
                                   "2. FRAME TO BE SHOT BLASTED AND POWDER COATED RAL 7035, 80 MICRONS DFT.",
                                   "3. GUARD PANEL CLEAR ANODISED 15 MICRONS.",
                                   "4. LIFTING EYE NORMALISED."]):
                s.text(25, 31 + i * 5.5, n, 2.8)
        header = ["POS", "QTY", "DESCRIPTION", "PART #", "MATERIAL", "WEIGHT (KG)"]
        cw = [12, 12, 62, 28, 42, 24]
        bx = W - 10 - sum(cw)
        tbl = [["BILL OF MATERIALS", "", "", "", "", ""], header] + rows
        # caption row: one merged cell
        y = 10
        s.rect(bx, y, bx + sum(cw), y + 7)
        s.ctext(bx, bx + sum(cw), y + 4.8, "BILL OF MATERIALS", 3.0, bold=True)
        s.table(bx, y + 7, cw, 7, [header] + rows, size=2.5, header_rows=(0,),
                aligns=["c", "c", "l", "l", "l", "c"])
        for r in rows:
            truth_bom.append({"item": r[0], "quantity": r[1], "description": r[2], "part_number": r[3],
                              "material": r[4], "mass": r[5]})
        # title block
        tx0, ty0 = W - 10 - 180, H - 10 - 30
        s.table(tx0, ty0, [60, 60, 60], 10,
                [["DRG. NO.  HC-FRAME-7781", "TITLE: HEAVY DUTY CART FRAME", f"SHEET {pg} OF 2"],
                 ["DRAWN: T. NAKAMURA", "DATE: 05 AUG 2024", "SCALE: 1:10"],
                 ["REV: D", "CHECKED: B. OKAFOR", "THIRD ANGLE PROJECTION"]], size=2.5,
                aligns=["l", "l", "l"])
    vec = out / "_drawing4_vector.pdf"
    doc.save(str(vec))
    doc.close()

    # make it an image-only (scanned) PDF at 200 dpi
    rng = np.random.default_rng(7)
    src = pymupdf.open(str(vec))
    dst = pymupdf.open()
    for i, page in enumerate(src):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(200 / 72, 200 / 72), colorspace=pymupdf.csGRAY)
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples).filter(ImageFilter.GaussianBlur(0.6))
        im = im.rotate(-0.5 if i == 0 else 0.3, resample=Image.BICUBIC, fillcolor=255)
        a = np.asarray(im).astype(np.float32) * 0.9 + 15 + rng.normal(0, 12, (im.height, im.width))
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        p = out / f"_tmp_{i}.jpg"
        im.save(str(p), quality=80)  # scanned PDFs are normally JPEG-compressed
        np_ = dst.new_page(width=page.rect.width, height=page.rect.height)
        np_.insert_image(np_.rect, filename=str(p))
        p.unlink()
    dst.save(str(out / "drawing4_scanned_two_sheets.pdf"))
    src.close()
    vec.unlink()
    return {
        "file": "drawing4_scanned_two_sheets",
        "title_block": {"drawing_number": "HC-FRAME-7781", "drawing_title": "HEAVY DUTY CART FRAME",
                        "revision": "D", "drawn_by": "T. NAKAMURA", "date": "2024-08-05", "scale": "1:10",
                        "projection": "THIRD ANGLE", "sheet": "1 OF 2"},
        "bom": truth_bom,
        "revisions": [],
        "specs": {"material_callout": "S355JR", "surface_finish": ["POWDER COAT", "ANODISED"],
                  "heat_treatment": ["NORMALISED"]},
    }


# ======================================================================
def scan(pdf: Path, out: Path, dpi=200, angle=0.0, rot90=0, noise=10, seed=0):
    """Degrade a vector PDF into a 'scanned' raster: blur, skew, noise, speckle."""
    rng = np.random.default_rng(seed)
    d = pymupdf.open(str(pdf))
    pix = d[0].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), colorspace=pymupdf.csGRAY)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    im = im.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    a = np.asarray(im).astype(np.float32)
    a = a * 0.92 + 12  # greyish paper
    a += rng.normal(0, noise, a.shape)
    sp = rng.random(a.shape)
    a[sp < 0.0006] = 30
    a[sp > 0.9994] = 255
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if rot90:
        im = im.rotate(rot90, expand=True)
    im.save(str(out), dpi=(dpi, dpi), **({"compression": "tiff_lzw"} if out.suffix == ".tif" else {}))
    d.close()


def stress(out_dir="samples_stress", samples_dir="samples"):
    """Harsher, unseen degradations of the vector samples (for robustness checks)."""
    out, src = Path(out_dir), Path(samples_dir)
    out.mkdir(parents=True, exist_ok=True)
    gt = {t["file"]: t for t in json.loads((src / "ground_truth.json").read_text())}
    cases = [("drawing1_shaft_assembly", "s1_200dpi_skew-1.5", 200, -1.5, 0, 16, 11),
             ("drawing2_pivot_bracket", "s2_150dpi_noisy", 150, 0.6, 0, 18, 12),
             ("drawing1_shaft_assembly", "s3_300dpi_upsidedown", 300, 0.3, 180, 10, 13),
             ("drawing2_pivot_bracket", "s4_200dpi_rot270", 200, -0.9, 270, 14, 14)]
    truths = []
    for srcname, name, dpi, ang, rot, noise, seed in cases:
        scan(src / f"{srcname}.pdf", out / f"{name}.png", dpi=dpi, angle=ang, rot90=rot, noise=noise, seed=seed)
        truths.append(dict(gt[srcname], file=name))
    (out / "ground_truth.json").write_text(json.dumps(truths, indent=2))
    print(f"wrote stress samples to {out}")


def main(out_dir="samples"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    truths = [drawing_1(out), drawing_2(out), drawing_3(out), drawing_4(out)]
    scan(out / "drawing1_shaft_assembly.pdf", out / "drawing1_scan_skewed.tif", dpi=250, angle=0.8, seed=1)
    scan(out / "drawing2_pivot_bracket.pdf", out / "drawing2_scan_rotated.png", dpi=300, angle=-0.4,
         rot90=90, seed=2)
    t1 = dict(truths[0], file="drawing1_scan_skewed")
    t2 = dict(truths[1], file="drawing2_scan_rotated")
    (out / "ground_truth.json").write_text(json.dumps(truths + [t1, t2], indent=2))
    print(f"wrote samples to {out}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "samples")
    if "--stress" in sys.argv:
        stress(args[1] if len(args) > 1 else "samples_stress", args[0] if args else "samples")
