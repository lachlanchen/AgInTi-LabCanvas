#!/usr/bin/env python3
"""Move the EVK 5 holder group onto the sensor board, centred on the light path.

Source: the user's Shapr3D export ``incubator+thinner.step`` (Shapr3D 26.113, HOOPS
Exchange AP242) of ``Incubator thinner.shapr``. Nothing in the export is edited except
the rigid translation of every solid that belongs to the ``EVK 5 holder`` assembly node.

Rule used for the move (see README):
- optical axis = XY centre of the ``Sensor`` plate under ``NHI in incubator``; it is
  checked to coincide with the ``Diffraction grating`` centre and grating window;
- the holder group's XY bounding-box centre goes onto that axis;
- the holder group's lowest face goes onto the sensor plate's top face.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Plane
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Trsf, gp_Vec

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402

DESIGN_DIR = Path(__file__).resolve().parent
DESIGN_NAME = DESIGN_DIR.name
DEFAULT_SOURCE = Path("/home/lachlan/Downloads/incubator+thinner.step")
SOURCE_SHAPR = Path("/home/lachlan/Nutstore Files/Projects/shapr3d/BACKUP/BATCHEXPORT/Incubator thinner.shapr")
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
HOLDER_NODE = "EVK 5 holder"
PLATE_NODE = "Sensor"
GRATING_NODE = "Diffraction grating"
NHI_NODE = "NHI in incubator"
TOL = 1e-6


# ----------------------------------------------------------------------------- STEP in

def name_of(lbl: TDF_Label) -> str:
    n = TDataStd_Name()
    return n.Get().ToExtString() if lbl.FindAttribute(TDataStd_Name.GetID_s(), n) else ""


def read_step_parts(path: Path) -> list[dict[str, Any]]:
    """Return leaf parts with their assembly path and world-located shape."""
    doc = TDocStd_Document(TCollection_ExtendedString("in"))
    rdr = STEPCAFControl_Reader()
    rdr.SetNameMode(True)
    if rdr.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"cannot read {path}")
    rdr.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    parts: list[dict[str, Any]] = []

    def walk(lbl: TDF_Label, path_names: list[str], loc: TopLoc_Location) -> None:
        nm = name_of(lbl)
        ref = TDF_Label()
        is_ref = st.IsReference_s(lbl)
        if is_ref:
            st.GetReferredShape_s(lbl, ref)
        target = ref if is_ref else lbl
        tname = name_of(target) if is_ref else nm
        loc2 = loc.Multiplied(st.GetLocation_s(lbl)) if is_ref else loc
        label = nm or tname
        if st.IsAssembly_s(target):
            comps = TDF_LabelSequence()
            st.GetComponents_s(target, comps)
            for i in range(1, comps.Length() + 1):
                walk(comps.Value(i), path_names + [label], loc2)
            return
        shape = st.GetShape_s(target)
        if shape.IsNull():
            return
        located = shape.Moved(loc2)
        solids = []
        e = TopExp_Explorer(located, TopAbs_SOLID)
        while e.More():
            solids.append(cq.Solid(e.Current()))
            e.Next()
        if not solids:
            return
        parts.append({"path": path_names + [label], "name": label, "solids": solids})

    free = TDF_LabelSequence()
    st.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), [], TopLoc_Location())
    return parts


# ----------------------------------------------------------------------------- geometry

def bbox(shape: cq.Shape) -> dict[str, float]:
    b = shape.BoundingBox(tolerance=1e-7)
    return {"xmin": b.xmin, "ymin": b.ymin, "zmin": b.zmin, "xmax": b.xmax, "ymax": b.ymax, "zmax": b.zmax}


def centre_xy(b: dict[str, float]) -> tuple[float, float]:
    return (b["xmin"] + b["xmax"]) / 2.0, (b["ymin"] + b["ymax"]) / 2.0


def planar_faces(shape: cq.Shape) -> list[dict[str, Any]]:
    out = []
    e = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while e.More():
        f = TopoDS.Face_s(e.Current())
        e.Next()
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() != GeomAbs_Plane:
            continue
        p = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, p)
        pln = ad.Plane()
        n = pln.Axis().Direction()
        if f.Orientation().name == "TopAbs_REVERSED":
            n = n.Reversed()
        bb = Bnd_Box()
        BRepBndLib.Add_s(f, bb, False)
        x0, y0, z0, x1, y1, z1 = bb.Get()
        out.append({"n": (round(n.X(), 6), round(n.Y(), 6), round(n.Z(), 6)), "area": p.Mass(),
                    "bbox": (x0, y0, z0, x1, y1, z1), "face": cq.Face(f)})
    return out


def grating_window(grating: cq.Solid) -> dict[str, Any]:
    """Smallest square through-opening of the grating holder, from its vertical faces."""
    b = bbox(grating)
    verticals = [f for f in planar_faces(grating) if abs(f["n"][2]) < 1e-6 and f["area"] > 50]
    inner = [f for f in verticals if b["xmin"] + 1 < f["bbox"][0] and f["bbox"][3] < b["xmax"] - 1
             and b["ymin"] + 1 < f["bbox"][1] and f["bbox"][4] < b["ymax"] - 1]
    xs = sorted({round(f["bbox"][0], 3) for f in inner if abs(f["n"][0]) > 0.5})
    ys = sorted({round(f["bbox"][1], 3) for f in inner if abs(f["n"][1]) > 0.5})
    return {"x_faces": xs, "y_faces": ys,
            "innermost_square_mm": [xs[0], ys[0], xs[-1], ys[-1]] if xs and ys else None,
            "centre": [(xs[0] + xs[-1]) / 2, (ys[0] + ys[-1]) / 2] if xs and ys else None}


def contact_area(lower_top_z: float, plate: cq.Solid, moved_holder_solids: list[cq.Solid]) -> float:
    """Area of the holder faces lying on the plate top plane (should be the base footprint)."""
    total = 0.0
    for s in moved_holder_solids:
        for f in planar_faces(s):
            if f["n"][2] < -0.5 and abs(f["bbox"][2] - lower_top_z) < 1e-4:
                total += f["area"]
    return total


# ----------------------------------------------------------------------------- STEP out

import re


def step_body_names(path: Path) -> list[dict[str, Any]]:
    """Read MANIFOLD_SOLID_BREP labels from the STEP text and locate each body by its vertex bbox.

    XCAF sub-shape names crash in this OCP build, so the names are matched to imported
    solids through the exact vertex bounding box (size and position within 0.01 mm).
    """
    txt = path.read_text(errors="ignore")
    data = txt[txt.index("DATA;"):]
    ent: dict[int, tuple[str, str]] = {}
    for m in re.finditer(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*?)\)\s*;", data, re.S):
        ent[int(m.group(1))] = (m.group(2), m.group(3))
    ref_re = re.compile(r"#(\d+)")
    skip = {"CARTESIAN_POINT", "DIRECTION", "AXIS2_PLACEMENT_3D", "PLANE", "CYLINDRICAL_SURFACE", "CIRCLE", "LINE",
            "VECTOR", "B_SPLINE_SURFACE_WITH_KNOTS", "B_SPLINE_CURVE_WITH_KNOTS", "CONICAL_SURFACE",
            "TOROIDAL_SURFACE", "SPHERICAL_SURFACE", "ELLIPSE", "SURFACE_OF_REVOLUTION", "SURFACE_OF_LINEAR_EXTRUSION"}
    out = []
    for eid, (typ, args) in ent.items():
        if typ != "MANIFOLD_SOLID_BREP":
            continue
        name = re.match(r"'([^']*)'", args).group(1)
        seen: set[int] = set()
        stack = [eid]
        pts = []
        while stack:
            e = stack.pop()
            if e in seen or e not in ent:
                continue
            seen.add(e)
            t, a = ent[e]
            if t == "VERTEX_POINT":
                pid = int(ref_re.findall(a)[0])
                nums = re.findall(r"(-?[\d.Ee+-]+)", ent[pid][1].split("(", 1)[1])
                pts.append(tuple(float(x) for x in nums[:3]))
                continue
            if t in skip:
                continue
            stack.extend(int(r) for r in ref_re.findall(a))
        if pts:
            xs, ys, zs = zip(*pts)
            out.append({"name": readable_source_name(name), "bbox": [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]})
    return out


def match_body_name(solid: cq.Solid, catalog: list[dict[str, Any]]) -> str | None:
    b = bbox(solid)
    mine = [b["xmin"], b["ymin"], b["zmin"], b["xmax"], b["ymax"], b["zmax"]]
    for entry in catalog:
        if all(abs(x - y) < 0.01 for x, y in zip(mine, entry["bbox"])):
            return entry["name"]
    return None


def write_named_step(path: Path, groups: list[tuple[str, list[tuple[str, cq.Shape]]]], root_name: str) -> None:
    """Write root -> group -> named part hierarchy (names survive Shapr3D/FreeCAD import)."""
    doc = TDocStd_Document(TCollection_ExtendedString("out"))
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    root = st.NewShape()
    TDataStd_Name.Set_s(root, TCollection_ExtendedString(root_name))
    for group_name, items in groups:
        grp = st.NewShape()
        TDataStd_Name.Set_s(grp, TCollection_ExtendedString(group_name))
        for name, shape in items:
            part = st.AddShape(shape.wrapped, False)
            TDataStd_Name.Set_s(part, TCollection_ExtendedString(name))
            st.AddComponent(grp, part, TopLoc_Location())
        st.AddComponent(root, grp, TopLoc_Location())
    st.UpdateAssemblies()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPCAFControl_Writer()
    w.SetNameMode(True)
    if not w.Transfer(doc, STEPControl_AsIs):
        raise RuntimeError("STEP transfer failed")
    if w.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed: {path}")


def readable_source_name(raw: str) -> str:
    """Repair Shapr's GBK-as-Latin1 vendor names; keep everything else verbatim."""
    try:
        fixed = raw.encode("latin-1").decode("gbk")
        if fixed != raw:
            return fixed
    except Exception:
        pass
    return raw


def role_name(solid: cq.Solid, fallback: str) -> str:
    """Name unnamed enclosure solids by their geometry."""
    b = bbox(solid)
    sx, sy, sz = b["xmax"] - b["xmin"], b["ymax"] - b["ymin"], b["zmax"] - b["zmin"]
    if sx < 6 and sy > 200 and sz > 200:
        return "left wall" if b["xmin"] < 100 else "right wall"
    if sy < 6 and sx > 200 and sz > 200:
        return "back wall"
    if sx > 200 and sy > 200 and sz < 6:
        if sx > 270:
            return "floor plate" if b["zmin"] < 100 else "lid plate"
        return "lower shelf" if b["zmin"] < 150 else "upper shelf with window"
    if sz > 90 and sx < 10 and sy < 10:
        return "vertical rail"
    return fallback


def holder_part_name(solid: cq.Solid, group_bbox: dict[str, float]) -> str:
    b = bbox(solid)
    sx, sy = b["xmax"] - b["xmin"], b["ymax"] - b["ymin"]
    cx, cy = centre_xy(b)
    gx, gy = centre_xy(group_bbox)
    if abs(sx - sy) < 1e-3 and sx > 30:
        return "EVK 5 holder base (camera pocket)"
    if sx > sy:
        return "light dam wall %s" % ("+Y" if cy > gy else "-Y")
    return "light dam side %s" % ("+X" if cx > gx else "-X")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def step_summary(path: Path) -> dict[str, Any]:
    shape = cq.importers.importStep(str(path))
    solids = shape.solids().vals()
    invalid = [i for i, s in enumerate(solids) if not s.isValid()]
    return {"solids": len(solids), "invalid_solid_indices": invalid, "bbox": bbox(cq.Compound.makeCompound(solids))}


# ----------------------------------------------------------------------------- main

def build(source: Path, sync: bool) -> dict[str, Any]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    art = DESIGN_DIR / "artifacts"
    meshes = art / "render_meshes"
    renders = art / "renders"
    for d in (art, meshes, renders):
        d.mkdir(parents=True, exist_ok=True)

    parts = read_step_parts(source)
    holder_parts = [p for p in parts if HOLDER_NODE in p["path"]]
    other_parts = [p for p in parts if HOLDER_NODE not in p["path"]]
    plate_parts = [p for p in parts if p["name"] == PLATE_NODE and NHI_NODE in p["path"]]
    grating_parts = [p for p in parts if p["name"] == GRATING_NODE and NHI_NODE in p["path"]]
    if len(holder_parts) < 1 or len(plate_parts) != 1 or len(grating_parts) != 1:
        raise RuntimeError(f"unexpected structure: holder={len(holder_parts)} plate={len(plate_parts)} grating={len(grating_parts)}")
    holder_solids = [s for p in holder_parts for s in p["solids"]]
    plate = plate_parts[0]["solids"][0]
    grating = grating_parts[0]["solids"][0]
    others = [s for p in other_parts for s in p["solids"]]

    hb = bbox(cq.Compound.makeCompound(holder_solids))
    pb = bbox(plate)
    gb = bbox(grating)
    window = grating_window(grating)
    axis_from_plate = centre_xy(pb)
    axis_from_grating = centre_xy(gb)
    axis_from_window = tuple(window["centre"]) if window["centre"] else axis_from_grating
    axis = axis_from_plate
    hc = centre_xy(hb)
    dx, dy, dz = axis[0] - hc[0], axis[1] - hc[1], pb["zmax"] - hb["zmin"]
    move = cq.Vector(dx, dy, dz)

    moved_solids = [s.translate(move) for s in holder_solids]
    moved_parts = [{"path": p["path"], "name": p["name"], "solids": [s.translate(move) for s in p["solids"]]} for p in holder_parts]
    mb = bbox(cq.Compound.makeCompound(moved_solids))

    # --- checks
    interference = []
    for i, o in enumerate(others):
        for j, m in enumerate(moved_solids):
            inter = m.intersect(o)
            vol = inter.Volume() if inter.isValid() else 0.0
            if vol > TOL:
                interference.append({"holder_solid": j, "other_solid": i, "volume_mm3": vol})
    base_contact = contact_area(pb["zmax"], plate, moved_solids)
    # upper shelf window (the 100x100 opening above the sensor plate) and shelf bottom
    shelf_openings = []
    for o in others:
        ob = bbox(o)
        if ob["zmax"] - ob["zmin"] < 6 and ob["xmax"] - ob["xmin"] > 200 and ob["zmin"] > pb["zmax"] and ob["zmin"] < gb["zmin"]:
            for f in planar_faces(o):
                if f["n"][2] > 0.5 and f["area"] < 5000 and abs(f["bbox"][2] - ob["zmin"] - 1.0) < 2.0:
                    shelf_openings.append({"shelf_z": [ob["zmin"], ob["zmax"]], "opening_bbox": f["bbox"][:2] + f["bbox"][3:5]})
    checks = {
        "plate_and_grating_share_axis": abs(axis_from_plate[0] - axis_from_grating[0]) < 1e-3 and abs(axis_from_plate[1] - axis_from_grating[1]) < 1e-3,
        "grating_window_centred_on_axis": abs(axis_from_window[0] - axis[0]) < 1e-3 and abs(axis_from_window[1] - axis[1]) < 1e-3,
        "holder_centre_on_axis_after_move": abs(centre_xy(mb)[0] - axis[0]) < TOL and abs(centre_xy(mb)[1] - axis[1]) < TOL,
        "holder_base_on_plate_top": abs(mb["zmin"] - pb["zmax"]) < TOL,
        "holder_footprint_inside_plate": mb["xmin"] >= pb["xmin"] and mb["xmax"] <= pb["xmax"] and mb["ymin"] >= pb["ymin"] and mb["ymax"] <= pb["ymax"],
        "holder_below_grating": mb["zmax"] < gb["zmin"],
        "no_interference_with_unchanged_parts": not interference,
        "base_contact_area_positive": base_contact > 500.0,
        "holder_solid_count_unchanged": len(moved_solids) == len(holder_solids),
        "holder_volume_unchanged": abs(sum(s.Volume() for s in moved_solids) - sum(s.Volume() for s in holder_solids)) < 1e-3,
    }
    for so in shelf_openings:
        x0, y0, x1, y1 = so["opening_bbox"]
        so["holder_inside_opening_xy"] = mb["xmin"] >= x0 and mb["xmax"] <= x1 and mb["ymin"] >= y0 and mb["ymax"] <= y1
    if shelf_openings:
        checks["holder_inside_upper_shelf_window_xy"] = all(s["holder_inside_opening_xy"] for s in shelf_openings)

    # --- exports (root -> group -> part, readable names)
    def group_of(p: dict[str, Any]) -> str:
        if p["name"].startswith("=>") or p["name"] in ("COMPOUND", "SOLID"):
            return "Incubator enclosure"
        inner = [x for x in p["path"][1:-1] if x]
        return readable_source_name(inner[-1]) if inner else "Incubator enclosure"

    catalog = step_body_names(source)

    def part_items(parts_list: list[dict[str, Any]], moved: bool = False, untranslate: bool | None = None) -> list[tuple[str, list[tuple[str, cq.Shape]]]]:
        """Name every solid by its STEP body label; add the geometric role for the holder/enclosure."""
        grouped: dict[str, list[tuple[str, cq.Shape]]] = {}
        gb_all = bbox(cq.Compound.makeCompound([s for p in parts_list for s in p["solids"]])) if parts_list else None
        for p in parts_list:
            g = group_of(p)
            raw = readable_source_name(p["name"])
            for k, sol in enumerate(p["solids"]):
                back = moved if untranslate is None else untranslate
                probe = sol.translate(cq.Vector(-dx, -dy, -dz)) if back else sol
                label = match_body_name(probe, catalog)
                if moved:
                    role = holder_part_name(sol, gb_all)
                    nm = f"{label} ({role})" if label else role
                elif raw.startswith("=>") or raw in ("COMPOUND", "SOLID"):
                    role = role_name(sol, f"enclosure part {k + 1}")
                    nm = f"{label} ({role})" if label else role
                else:
                    nm = label or (raw + (f" [{k + 1}]" if len(p["solids"]) > 1 else ""))
                grouped.setdefault(g, []).append((nm, sol))
        return list(grouped.items())

    files: dict[str, Path] = {}
    files["assembly_moved"] = art / f"{DESIGN_NAME}_assembly_moved.step"
    write_named_step(files["assembly_moved"], part_items(other_parts) + [("EVK 5 holder (MOVED onto sensor board)", part_items(moved_parts, moved=True)[0][1])],
                     "Incubator thinner - EVK 5 holder moved onto sensor board")
    files["holder_moved"] = art / "evk5_holder_group_moved.step"
    write_named_step(files["holder_moved"], [("EVK 5 holder (moved)", part_items(moved_parts, moved=True)[0][1])], "EVK 5 holder group moved")
    files["holder_original"] = art / "evk5_holder_group_original_position.step"
    write_named_step(files["holder_original"], [("EVK 5 holder (original export position)", part_items(holder_parts, moved=True, untranslate=False)[0][1])], "EVK 5 holder group original position")
    files["context"] = art / "incubator_context_unchanged.step"
    write_named_step(files["context"], part_items(other_parts), "Incubator thinner - unchanged parts")
    axis_len = gb["zmax"] - pb["zmax"] + 20.0
    axis_proxy = cq.Workplane("XY").circle(0.5).extrude(axis_len).translate(cq.Vector(axis[0], axis[1], pb["zmax"] - 10.0)).val()
    files["axis_reference"] = art / "light_path_axis_reference.step"
    write_named_step(files["axis_reference"], [("reference", [("light path axis reference (not a part)", cq.Solid(axis_proxy.wrapped))])], "light path axis reference")
    files["holder_moved_stl"] = art / "evk5_holder_group_moved.stl"
    exporters.export(cq.Workplane().add(cq.Compound.makeCompound(moved_solids)), str(files["holder_moved_stl"]), tolerance=0.01, angularTolerance=0.1)
    files["holder_moved_3mf"] = art / "evk5_holder_group_moved.3mf"
    export_stl_as_3mf(files["holder_moved_stl"], files["holder_moved_3mf"], title="EVK 5 holder group moved onto sensor board")
    use_this = DESIGN_DIR / f"USE_THIS_{DESIGN_NAME}_assembly_moved.step"
    shutil.copy2(files["assembly_moved"], use_this)

    # render meshes (grouped, coloured by the render script)
    def mesh(name: str, solids: list[cq.Solid]) -> Path:
        p = meshes / f"{name}.stl"
        exporters.export(cq.Workplane().add(cq.Compound.makeCompound(solids)), str(p), tolerance=0.02, angularTolerance=0.2)
        return p
    enclosure = [s for p in other_parts if group_of(p) == "Incubator enclosure" for s in p["solids"]]
    roles = {s: role_name(s, "other") for s in enclosure}
    walls = [s for s in enclosure if roles[s] in ("floor plate", "lid plate", "left wall", "right wall", "back wall")]
    lower_shelf = [s for s in enclosure if roles[s] == "lower shelf"]
    upper_shelf = [s for s in enclosure if roles[s] == "upper shelf with window"]
    stage = [s for p in other_parts if "FSK30" in " ".join(p["path"]) for s in p["solids"]]
    rest = [s for s in others if s not in walls and s not in lower_shelf and s not in upper_shelf and s not in stage and s is not plate and s is not grating]
    mesh_files = {
        "holder_moved": mesh("holder_moved", moved_solids),
        "holder_original": mesh("holder_original", holder_solids),
        "sensor_plate": mesh("sensor_plate", [plate]),
        "grating": mesh("grating", [grating]),
        "walls": mesh("walls", walls),
        "lower_shelf": mesh("lower_shelf", lower_shelf),
        "upper_shelf": mesh("upper_shelf", upper_shelf),
        "stage": mesh("stage", stage) if stage else None,
        "rest": mesh("rest", rest) if rest else None,
        "axis": mesh("axis", [cq.Solid(axis_proxy.wrapped)]),
    }

    manifest = {
        "design": DESIGN_NAME,
        "generated_utc": stamp,
        "source_step": {"path": str(source), "sha256": sha256(source), "bytes": source.stat().st_size},
        "source_shapr": {"path": str(SOURCE_SHAPR), "sha256": sha256(SOURCE_SHAPR) if SOURCE_SHAPR.exists() else None},
        "rule": "translate every solid under assembly node 'EVK 5 holder' so its XY bbox centre lies on the sensor-plate centre (= grating centre = light path) and its lowest face lies on the sensor-plate top face; nothing else changes",
        "translation_mm": {"dx": dx, "dy": dy, "dz": dz},
        "optical_axis_xy_mm": {"from_sensor_plate_centre": axis_from_plate, "from_grating_centre": axis_from_grating, "from_grating_window_centre": axis_from_window},
        "grating_window": {k: v for k, v in window.items()},
        "holder_group": {"solids": len(holder_solids), "parts": [n for n, _ in part_items(moved_parts, moved=True)[0][1]], "bbox_before": hb, "bbox_after": mb,
                          "volume_mm3": sum(s.Volume() for s in holder_solids)},
        "sensor_plate": {"bbox": pb, "top_z": pb["zmax"]},
        "grating": {"bbox": gb, "bottom_z": gb["zmin"]},
        "clearances_mm": {"holder_top_to_grating_bottom": gb["zmin"] - mb["zmax"],
                           "holder_to_plate_edge_x": min(mb["xmin"] - pb["xmin"], pb["xmax"] - mb["xmax"]),
                           "holder_to_plate_edge_y": min(mb["ymin"] - pb["ymin"], pb["ymax"] - mb["ymax"])},
        "upper_shelf_openings": shelf_openings,
        "base_contact_area_mm2": base_contact,
        "interference": interference,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "observations": [
            "The sensor plate top (z=%.3f) sits %.3f mm above the lower shelf top; the holder group is %.3f mm tall. Recorded only; not acted on." % (
                pb["zmax"], pb["zmin"] - max([bbox(s)["zmax"] for s in lower_shelf] or [0]), hb["zmax"] - hb["zmin"]),
            "The export contains no 'EVK 5' camera body: in the archive the 'EVK 5' folder sits under the hidden 'NHI' folder, so Shapr3D skipped it; only the 'EVK 5 holder' folder (with its empty 'Aux' subfolder) was exported.",
        ],
        "files": {k: str(v.relative_to(DESIGN_DIR)) for k, v in files.items()},
        "use_this": str(use_this.relative_to(DESIGN_DIR)),
        "render_meshes": {k: (str(v.relative_to(DESIGN_DIR)) if v else None) for k, v in mesh_files.items()},
        "step_roundtrip": {k: step_summary(v) for k, v in files.items() if v.suffix == ".step"},
        "unchanged_parts": [{"group": g, "parts": [n for n, _ in items]} for g, items in part_items(other_parts)],
        "step_body_labels": [c["name"] for c in catalog],
        "source_validity_note": "STEP round-trip flags one source solid (FSK30 stage part, 796 faces) as invalid in OCCT; it comes from the vendor import in the original export and is copied through unchanged.",
    }
    (art / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps({k: manifest[k] for k in ("translation_mm", "checks", "all_checks_pass", "clearances_mm", "interference")}, indent=2, default=str))
    if not manifest["all_checks_pass"]:
        raise SystemExit("checks failed; not packaging")
    return manifest


def package_run(manifest: dict[str, Any], sync: bool) -> Path:
    run = DESIGN_DIR / "runs" / f"run-1-holder-on-sensor-board-{manifest['generated_utc']}"
    if run.exists():
        shutil.rmtree(run)
    shutil.copytree(DESIGN_DIR / "artifacts", run / "artifacts", ignore=shutil.ignore_patterns("*.blend", "*.blend1", "render_meshes"))
    shutil.copy2(DESIGN_DIR / manifest["use_this"], run / Path(manifest["use_this"]).name)
    for extra in ("README.md", Path(__file__).name, "render_incubator_thinner_evk5_holder_on_sensor_board.py",
                  "render_paper_figure_incubator_thinner_evk5_holder.py", "compose_paper_figure_labels.py"):
        if (DESIGN_DIR / extra).exists():
            shutil.copy2(DESIGN_DIR / extra, run / extra)
    if sync:
        dest = NUTSTORE_ROOT / DESIGN_NAME
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DESIGN_DIR / manifest["use_this"], dest / Path(manifest["use_this"]).name)
        if (dest / run.name).exists():
            shutil.rmtree(dest / run.name)
        shutil.copytree(run, dest / run.name)
        for name in ("README.md",):
            if (DESIGN_DIR / name).exists():
                shutil.copy2(DESIGN_DIR / name, dest / name)
        print("synced to", dest)
    print("run folder", run)
    return run


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--package", action="store_true", help="also create the run folder (and Nutstore mirror unless --no-sync)")
    args = ap.parse_args()
    manifest = build(args.source, sync=not args.no_sync)
    if args.package:
        package_run(manifest, sync=not args.no_sync)


if __name__ == "__main__":
    main()
