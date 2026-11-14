"""Complete a DXF document converted from DWG by LibreDWG with geometry from
LibreDWG's JSON dump.

Why both: LibreDWG's two writers fail in different ways.
  * the DXF writer keeps every string (text, layer and block names) but can
    stop following an entity chain early, silently dropping most of a
    drawing (seen on R14 files: 387 of 2 794 entities written);
  * the JSON writer lists every object but (0.13.x) can blank code-page
    strings.
So the DXF output is the base document and every graphical entity that is
in the JSON but missing from the DXF is added, matched by DWG handle. Only
text cannot be recovered this way, and the caller reports how much was lost.
"""
from __future__ import annotations

import codecs
import json
import logging
import math
from typing import Any, Optional

log = logging.getLogger(__name__)

# DWG fixed object types (ODA spec) for entities
_TYPES = {
    1: "TEXT", 2: "ATTRIB", 3: "ATTDEF", 4: "BLOCK", 5: "ENDBLK", 6: "SEQEND", 7: "INSERT",
    8: "MINSERT", 10: "VERTEX_2D", 11: "VERTEX_3D", 12: "VERTEX_MESH", 13: "VERTEX_PFACE",
    14: "VERTEX_PFACE_FACE", 15: "POLYLINE_2D", 16: "POLYLINE_3D", 17: "ARC", 18: "CIRCLE",
    19: "LINE", 20: "DIMENSION", 21: "DIMENSION", 22: "DIMENSION", 23: "DIMENSION",
    24: "DIMENSION", 25: "DIMENSION", 26: "DIMENSION", 27: "POINT", 28: "3DFACE",
    29: "POLYLINE_PFACE", 30: "POLYLINE_MESH", 31: "SOLID", 32: "TRACE", 33: "SHAPE",
    34: "VIEWPORT", 35: "ELLIPSE", 36: "SPLINE", 37: "REGION", 38: "3DSOLID", 39: "BODY",
    40: "RAY", 41: "XLINE", 44: "MTEXT", 45: "LEADER", 46: "TOLERANCE", 47: "MLINE",
    77: "LWPOLYLINE", 78: "HATCH",
}
_SUBCLASS = {
    "AcDbPolyline": "LWPOLYLINE", "AcDbLine": "LINE", "AcDbCircle": "CIRCLE", "AcDbArc": "ARC",
    "AcDbEllipse": "ELLIPSE", "AcDbSpline": "SPLINE", "AcDbText": "TEXT", "AcDbMText": "MTEXT",
    "AcDbBlockReference": "INSERT", "AcDbHatch": "HATCH", "AcDbPoint": "POINT",
    "AcDbLeader": "LEADER", "AcDb2dPolyline": "POLYLINE_2D", "AcDb3dPolyline": "POLYLINE_3D",
    "AcDb2dVertex": "VERTEX_2D", "AcDb3dPolylineVertex": "VERTEX_3D", "AcDbFace": "3DFACE",
    "AcDbRotatedDimension": "DIMENSION", "AcDbAlignedDimension": "DIMENSION",
    "AcDbOrdinateDimension": "DIMENSION", "AcDbRadialDimension": "DIMENSION",
    "AcDbDiametricDimension": "DIMENSION", "AcDb3PointAngularDimension": "DIMENSION",
    "AcDb2LineAngularDimension": "DIMENSION", "AcDbArcDimension": "DIMENSION",
    "AcDbRadialDimensionLarge": "DIMENSION", "AcDbAttribute": "ATTRIB",
    "AcDbAttributeDefinition": "ATTDEF", "AcDbRasterImage": "IMAGE", "AcDbWipeout": "WIPEOUT",
}
TEXTUAL = {"TEXT", "MTEXT", "ATTRIB", "TOLERANCE"}


def _cp_fallback(err: UnicodeDecodeError):
    bad = err.object[err.start:err.end]
    return bad.decode("cp1252", errors="replace"), err.end


codecs.register_error("bomx_cp1252", _cp_fallback)


def load_json(raw: bytes) -> dict:
    """dwgread JSON may mix UTF-8 with raw code-page bytes (R14 and older)."""
    return json.loads(raw.decode("utf-8", errors="bomx_cp1252"), strict=False)


def _h(o: dict) -> Optional[str]:
    h = o.get("handle")
    if isinstance(h, list) and len(h) >= 3:
        return format(int(h[2]), "X")
    return None


def _ref(v) -> Optional[str]:
    """[code, size, value, absolute] -> absolute handle as hex."""
    if isinstance(v, list) and v:
        a = v[-1] if len(v) >= 4 else v[-1]
        try:
            a = int(a)
        except (TypeError, ValueError):
            return None
        return format(a, "X") if a else None
    return None


def kind(o: dict) -> Optional[str]:
    if "entmode" not in o:
        return None
    n = o.get("entity") or o.get("dxfname")
    if n:
        return {"POLYLINE_2D": "POLYLINE_2D"}.get(n, n)
    t = o.get("type")
    try:
        t = int(t)
    except (TypeError, ValueError):
        t = None
    if t is not None and t < 500 and t in _TYPES:
        return _TYPES[t]
    return _SUBCLASS.get(o.get("_subclass") or "")


def _xy(p, default=(0.0, 0.0)):
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return float(p[0]), float(p[1])
    return default


def supplement(doc, data: dict) -> dict[str, int]:
    """Add graphical entities present in the JSON dump but missing from
    `doc`. Returns statistics."""
    db = doc.entitydb
    objs = data.get("OBJECTS") or []
    by_handle = {h: o for o in objs if (h := _h(o))}
    stats = {"json_entities": 0, "added": 0, "text_lost": 0, "skipped": 0}

    # owner block of each block-owned entity: BLOCK_HEADER handle -> layout
    block_layouts: dict[str, Any] = {}
    for o in objs:
        if o.get("object") == "BLOCK_HEADER" or o.get("type") == 49:
            h = _h(o)
            rec = db.get(h) if h else None
            if rec is not None and rec.dxftype() == "BLOCK_RECORD":
                try:
                    block_layouts[h] = doc.blocks.get(rec.dxf.name)
                except Exception:
                    pass
            elif h:  # block missing from the DXF: create a stand-in
                try:
                    blk = doc.blocks.new(f"_DWG_{h}")
                    block_layouts[h] = blk
                except Exception:
                    pass

    msp, psp = doc.modelspace(), doc.paperspace()
    # handles actually placed in a layout or block (an entity can exist in the
    # DXF's database yet be attached to nothing, and then never renders)
    placed: dict[str, Any] = {}
    for lay in [*doc.layouts, *doc.blocks]:
        for e in lay:
            placed[e.dxf.handle] = e
    layer_names = {}

    def layer_of(o):
        ref = _ref(o.get("layer"))
        if ref is None:
            return "0"
        if ref not in layer_names:
            ent = db.get(ref)
            layer_names[ref] = ent.dxf.name if ent is not None and ent.dxftype() == "LAYER" else "0"
        return layer_names[ref]

    def block_name(ref) -> Optional[str]:
        if not ref:
            return None
        rec = db.get(ref)
        if rec is not None and rec.dxftype() == "BLOCK_RECORD":
            return rec.dxf.name
        blk = block_layouts.get(ref)
        return blk.name if blk is not None else None

    for o in objs:
        k = kind(o)
        if not k or k in ("BLOCK", "ENDBLK", "SEQEND", "VERTEX_2D", "VERTEX_3D", "VERTEX_MESH",
                          "VERTEX_PFACE", "VERTEX_PFACE_FACE", "ATTDEF", "VIEWPORT"):
            continue
        stats["json_entities"] += 1
        h = _h(o)
        if h and h in placed and _same(placed[h], k, o):
            continue  # (damaged files can reuse a handle: then compare geometry)
        mode = o.get("entmode")
        if mode == 2:
            space = msp
        elif mode == 1:
            space = psp
        else:
            owner = _ref(o.get("ownerhandle"))
            space = block_layouts.get(owner) if owner else None
            if space is None:
                continue  # attribs / vertices of other entities
        if k in TEXTUAL or k == "ATTRIB":
            stats["text_lost"] += 1
            continue
        attribs = {"layer": layer_of(o)}
        try:
            if _add(space, k, o, attribs, by_handle, block_name, doc):
                stats["added"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:  # malformed record: skip it, keep the rest
            log.debug("skip %s %s: %s", k, h, e)
            stats["skipped"] += 1
    return stats


def _same(ent, k: str, o: dict) -> bool:
    """Is DXF entity `ent` the JSON record `o`?"""
    t = ent.dxftype()
    try:
        if k == "LWPOLYLINE":
            if t != "LWPOLYLINE":
                return False
            p = (o.get("points") or [[None, None]])[0]
            q = next(iter(ent.get_points("xy")), None)
            return q is not None and abs(q[0] - p[0]) < 1e-6 and abs(q[1] - p[1]) < 1e-6 \
                and len(ent) == len(o.get("points") or [])
        if k == "LINE":
            return t == "LINE" and abs(ent.dxf.start.x - o["start"][0]) < 1e-6 \
                and abs(ent.dxf.start.y - o["start"][1]) < 1e-6
        if k in ("CIRCLE", "ARC"):
            return t == k and abs(ent.dxf.center.x - o["center"][0]) < 1e-6 \
                and abs(ent.dxf.radius - o["radius"]) < 1e-6
        if k == "POLYLINE_2D" or k == "POLYLINE_3D":
            return t == "POLYLINE"
        if k == "DIMENSION":
            return t == "DIMENSION"
        return t == k or (k in ("SOLID", "TRACE") and t in ("SOLID", "TRACE"))
    except Exception:
        return True


def _extr(o, attribs):
    ex = o.get("extrusion")
    if isinstance(ex, list) and len(ex) == 3 and abs(float(ex[2]) - 1.0) > 1e-9:
        attribs["extrusion"] = tuple(float(v) for v in ex)


def _add(space, k, o, attribs, by_handle, block_name, doc) -> bool:
    if k == "LINE":
        space.add_line(tuple(o["start"][:3]), tuple(o["end"][:3]), dxfattribs=attribs)
    elif k == "CIRCLE":
        _extr(o, attribs)
        space.add_circle(tuple(o["center"][:3]), float(o["radius"]), dxfattribs=attribs)
    elif k == "ARC":
        _extr(o, attribs)
        space.add_arc(tuple(o["center"][:3]), float(o["radius"]),
                      math.degrees(float(o["start_angle"])), math.degrees(float(o["end_angle"])),
                      dxfattribs=attribs)
    elif k == "ELLIPSE":
        ratio = max(min(float(o.get("axis_ratio", 1.0)), 1.0), 1e-6)
        space.add_ellipse(tuple(o["center"][:3]), tuple(o["sm_axis"][:3]), ratio,
                          float(o.get("start_angle", 0.0)), float(o.get("end_angle", math.tau)),
                          dxfattribs=attribs)
    elif k == "LWPOLYLINE":
        pts = o.get("points") or []
        if len(pts) < 2:
            return False
        bul = o.get("bulges") or []
        flag = int(o.get("flag", 0) or 0)
        closed = bool(flag & 512)  # DWG LWPLINE flag bit 512 = closed
        _extr(o, attribs)
        verts = [(float(p[0]), float(p[1]), 0.0, 0.0, float(bul[i]) if i < len(bul) else 0.0)
                 for i, p in enumerate(pts)]
        if doc.dxfversion <= "AC1009":
            pl = space.add_polyline2d([v[:2] for v in verts], close=closed, dxfattribs=attribs)
            for v, vert in zip(verts, pl.vertices):
                vert.dxf.bulge = v[4]
        else:
            space.add_lwpolyline(verts, format="xyseb", close=closed, dxfattribs=attribs)
    elif k in ("POLYLINE_2D", "POLYLINE_3D"):
        refs = o.get("vertex") or []
        verts = []
        if refs:
            for r in refs:
                v = by_handle.get(_ref(r))
                if v is not None:
                    verts.append(v)
        else:  # R13-R2000: first/last vertex, chained by handle order
            first, last = _ref(o.get("first_vertex")), _ref(o.get("last_vertex"))
            if first and last:
                a, b = int(first, 16), int(last, 16)
                for hv in range(a, b + 1):
                    v = by_handle.get(format(hv, "X"))
                    if v is not None and str(kind(v) or "").startswith("VERTEX"):
                        verts.append(v)
        pts = [(*_xy(v.get("point")), 0.0, 0.0, float(v.get("bulge", 0.0) or 0.0)) for v in verts
               if not int(v.get("flag", 0) or 0) & 16]  # skip spline frame points
        if len(pts) < 2:
            return False
        closed = bool(int(o.get("flag", 0) or 0) & 1)
        space.add_lwpolyline(pts, format="xyseb", close=closed, dxfattribs=attribs)
    elif k in ("SOLID", "TRACE", "3DFACE"):
        c = [_xy(o.get(f"corner{i}")) for i in range(1, 5)]
        if k == "3DFACE":
            space.add_lwpolyline(c, close=True, dxfattribs=attribs)
        else:
            space.add_solid(c, dxfattribs=attribs)
    elif k == "POINT":
        space.add_point((float(o.get("x", 0)), float(o.get("y", 0))), dxfattribs=attribs)
    elif k == "SPLINE":
        pts = o.get("fit_pts") or []
        if not pts:
            cps = o.get("ctrl_pts") or []
            pts = [c.get("xyz") if isinstance(c, dict) else c for c in cps]
        pts = [tuple(float(x) for x in p[:3]) for p in pts if p]
        if len(pts) < 2:
            return False
        if o.get("fit_pts"):
            space.add_spline(fit_points=pts, dxfattribs=attribs)
        else:
            deg = int(o.get("degree", 3) or 3)
            if len(pts) <= deg:
                space.add_lwpolyline([p[:2] for p in pts], dxfattribs=attribs)
            else:
                space.add_open_spline(pts, degree=deg, dxfattribs=attribs)
    elif k == "LEADER":
        pts = [_xy(p) for p in (o.get("points") or [])]
        if len(pts) < 2:
            return False
        space.add_lwpolyline(pts, dxfattribs=attribs)
    elif k in ("INSERT", "MINSERT"):
        name = block_name(_ref(o.get("block_header")))
        if not name:
            return False
        sc = o.get("scale") or [1.0, 1.0, 1.0]
        attribs.update(xscale=float(sc[0]), yscale=float(sc[1]), zscale=float(sc[2]) if len(sc) > 2 else 1.0,
                       rotation=math.degrees(float(o.get("rotation", 0.0) or 0.0)))
        _extr(o, attribs)
        space.add_blockref(name, tuple(o.get("ins_pt", [0, 0, 0])[:3]), dxfattribs=attribs)
    elif k == "DIMENSION":
        name = block_name(_ref(o.get("block")))
        if not name:
            return False
        space.add_blockref(name, (0, 0, 0), dxfattribs=attribs)
    else:
        return False
    return True
