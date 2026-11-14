"""Generate native CAD (DXF, and DWG when LibreDWG's dxf2dwg is available)
versions of the synthetic drawings in make_samples.py, with the same ground
truth, plus CAD-specific cases:

  cad1_shaft_assembly.dxf     model space, TEXT entities, mm
  cad1_shaft_assembly.dwg     same, converted with dxf2dwg (if installed)
  cad2_pivot_bracket.dxf      paper-space sheet, MTEXT entities, a model-space
                              detail seen through a viewport, a stray object far away
  cad3_attribute_titleblock.dxf
                              title-block values held only as block ATTRIBs
                              (no label text next to them), inches, BOM as a block

    python tests/make_cad_samples.py samples_cad/
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

sys.path.insert(0, str(Path(__file__).parent))
import make_samples as ms  # noqa: E402


class CadSheet(ms.Sheet):
    """Same drawing interface as make_samples.Sheet (mm, y down), written as
    DXF entities (y up)."""

    mtext = False
    paper = False

    def __init__(self, size):
        self.W, self.H = size[0] / ms.MM, size[1] / ms.MM
        self.doc = ezdxf.new("R2010", setup=True, units=ezdxf.units.MM)
        self.doc.styles.add("BOLD", font="DejaVuSans-Bold.ttf")
        self.doc.styles.add("NORMAL", font="DejaVuSans.ttf")
        if self.paper:
            lay = self.doc.layouts.new("A3 SHEET")
            lay.page_setup(size=(self.W, self.H), margins=(0, 0, 0, 0), units="mm")
            self.sp = lay
        else:
            self.sp = self.doc.modelspace()

    def _y(self, y):
        return self.H - y

    def line(self, x0, y0, x1, y1, w=0.5):
        self.sp.add_line((x0, self._y(y0)), (x1, self._y(y1)), dxfattribs={"lineweight": int(w * 100)})

    def rect(self, x0, y0, x1, y1, w=0.5):
        pts = [(x0, self._y(y0)), (x1, self._y(y0)), (x1, self._y(y1)), (x0, self._y(y1))]
        self.sp.add_lwpolyline(pts, close=True, dxfattribs={"lineweight": int(w * 100)})

    def circle(self, cx, cy, r, w=0.5):
        self.sp.add_circle((cx, self._y(cy)), r)

    def text(self, x, y, s, size=2.5, bold=False):
        style = "BOLD" if bold else "NORMAL"
        if self.mtext:
            m = self.sp.add_mtext(s, dxfattribs={"style": style, "char_height": size})
            m.set_location((x, self._y(y) + size), attachment_point=1)  # top-left
        else:
            self.sp.add_text(s, height=size, dxfattribs={"style": style}).set_placement(
                (x, self._y(y)), align=TextEntityAlignment.LEFT)

    def ctext(self, x0, x1, y, s, size=2.5, bold=False):
        style = "BOLD" if bold else "NORMAL"
        if self.mtext:
            m = self.sp.add_mtext(s, dxfattribs={"style": style, "char_height": size})
            m.set_location(((x0 + x1) / 2, self._y(y) + size), attachment_point=2)  # top-center
        else:
            self.sp.add_text(s, height=size, dxfattribs={"style": style}).set_placement(
                ((x0 + x1) / 2, self._y(y)), align=TextEntityAlignment.BOTTOM_CENTER)

    def save(self, path):
        path = Path(path).with_suffix(".dxf")
        if self.paper:
            self._detail_viewport()
        self.doc.saveas(path)

    def _detail_viewport(self):
        """A flange detail drawn in model space at 1:1 and shown at 1:2 on the sheet."""
        msp = self.doc.modelspace()
        msp.add_circle((1000, 1000), 60)
        msp.add_circle((1000, 1000), 25)
        for a in range(0, 360, 60):
            import math
            msp.add_circle((1000 + 45 * math.cos(math.radians(a)), 1000 + 45 * math.sin(math.radians(a))), 5)
        msp.add_text("DETAIL B", height=8).set_placement((1000, 920), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_point((90000, -50000))  # a stray far away (must not shrink the sheet)
        vp = self.sp.add_viewport(center=(120, self.H - 220), size=(160, 70),
                                  view_center_point=(1000, 990), view_height=140)
        vp.dxf.status = 2


def _with(cls_attrs, fn, out):
    old = ms.Sheet
    ms.Sheet = type("S", (CadSheet,), cls_attrs)
    try:
        return fn(out)
    finally:
        ms.Sheet = old


def drawing_attr(out: Path) -> dict:
    """Inch drawing: title block is a block whose values are ATTRIBs only."""
    doc = ezdxf.new("R2010", setup=True, units=ezdxf.units.IN)
    msp = doc.modelspace()
    W, H = 17.0, 11.0
    msp.add_lwpolyline([(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)], close=True)
    # a part
    msp.add_lwpolyline([(2, 5), (8, 5), (8, 8), (2, 8)], close=True)
    msp.add_circle((5, 6.5), 0.75)
    msp.add_text("NOTES:", height=0.14).set_placement((1, 3.4))
    for i, n in enumerate(["1. MATERIAL: AL 6061-T6.", "2. FINISH: ANODIZED BLACK.",
                           "3. BREAK ALL SHARP EDGES."]):
        msp.add_text(n, height=0.11).set_placement((1, 3.15 - i * 0.22))

    tb = doc.blocks.new("TITLEBLOCK")
    tb.add_lwpolyline([(0, 0), (6, 0), (6, 2), (0, 2)], close=True)
    tb.add_line((0, 1), (6, 1))
    tb.add_line((4, 0), (4, 1))
    tb.add_line((5, 0), (5, 1))
    tags = [("DWG_NO", (0.1, 0.4), 0.2), ("TITLE", (0.1, 1.4), 0.2), ("REV", (5.2, 0.4), 0.2),
            ("SCALE", (4.1, 0.4), 0.12), ("DRAWN", (0.1, 1.1), 0.1), ("DATE", (2.5, 1.1), 0.1)]
    for tag, pos, h in tags:
        tb.add_attdef(tag, pos, dxfattribs={"height": h})
    ins = msp.add_blockref("TITLEBLOCK", (W - 6.6, 0.6))
    ins.add_auto_attribs({"DWG_NO": "HX-7710-03", "TITLE": "HEAT SINK PLATE", "REV": "D",
                          "SCALE": "2:1", "DRAWN": "K. NAIR", "DATE": "2025-02-11"})

    # BOM drawn inside a block (lines + text), inserted once
    bom = [["1", "HX-101", "PLATE", "1", "AL 6061-T6"],
           ["2", "HX-102", "STANDOFF", "4", "SS303"],
           ["3", "HX-103", "SCREW M3x8", "4", "A2-70"]]
    blk = doc.blocks.new("BOM_TABLE")
    cw = [0.5, 1.2, 1.8, 0.5, 1.4]
    rh = 0.3
    rows = [["ITEM", "PART NO", "DESCRIPTION", "QTY", "MATERIAL"]] + bom
    x1 = sum(cw)
    for r in range(len(rows) + 1):
        blk.add_line((0, -r * rh), (x1, -r * rh))
    xs = 0
    for w in [0] + cw:
        xs += w
        blk.add_line((xs, 0), (xs, -len(rows) * rh))
    for r, row in enumerate(rows):
        xs = 0
        for c, s in enumerate(row):
            blk.add_text(s, height=0.11).set_placement((xs + 0.06, -r * rh - rh / 2 - 0.055))
            xs += cw[c]
    msp.add_blockref("BOM_TABLE", (W - 6.6, H - 0.7))
    doc.saveas(out / "cad3_attribute_titleblock.dxf")
    return {
        "file": "cad3_attribute_titleblock",
        "title_block": {"drawing_number": "HX-7710-03", "drawing_title": "HEAT SINK PLATE",
                        "revision": "D", "drawn_by": "K. NAIR", "date": "2025-02-11", "scale": "2:1"},
        "bom": [dict(zip(["item", "part_number", "description", "quantity", "material"], r)) for r in bom],
        "revisions": [],
        "specs": {"material_callout": "AL 6061-T6", "surface_finish": ["ANODIZED"]},
    }


def main(out_dir="samples_cad"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t1 = _with({}, ms.drawing_1, out)
    (out / "drawing1_shaft_assembly.dxf").rename(out / "cad1_shaft_assembly.dxf")
    t1 = dict(t1, file="cad1_shaft_assembly")
    t2 = _with({"mtext": True, "paper": True}, ms.drawing_2, out)
    (out / "drawing2_pivot_bracket.dxf").rename(out / "cad2_pivot_bracket.dxf")
    t2 = dict(t2, file="cad2_pivot_bracket")
    t3 = drawing_attr(out)
    truths = [t1, t2, t3]
    dxf2dwg = shutil.which("dxf2dwg")
    if dxf2dwg:
        dwg = out / "cad1_shaft_assembly_dwg.dwg"
        r = subprocess.run([dxf2dwg, "-y", "-o", str(dwg), str(out / "cad1_shaft_assembly.dxf")],
                           capture_output=True)
        if dwg.exists() and dwg.stat().st_size:
            truths.append(dict(t1, file="cad1_shaft_assembly_dwg"))
        else:
            print("dxf2dwg failed:", r.stderr.decode()[-300:])
    (out / "ground_truth.json").write_text(json.dumps(truths, indent=2))
    print(f"wrote CAD samples to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "samples_cad")
