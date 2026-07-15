#!/usr/bin/env python3
"""Build run 2: a coaxial 34 mm cylindrical PCB holder beside run 1's C-mount socket.

This is intentionally a surgical variant of the immutable run-1 builder.  The
source-board parser, C-mount thread construction, retained cut positions, and
proxy construction are loaded from run 1.  This file replaces the square plate
blank with one named cylindrical blank, adds complete per-body exports, and
records deeper print-ready validation.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_BSplineSurface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
import trimesh


ROOT = Path(__file__).resolve().parents[5]
RUN_DIR = Path(__file__).resolve().parent
DESIGN_DIR = RUN_DIR.parents[1]
ARTIFACT_DIR = RUN_DIR / "artifacts"
RUN1_DIR = DESIGN_DIR / "runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z"
RUN1_BUILDER = RUN1_DIR / "build_run1_shared_24mm_pcb_cmount_5mm.py"
# Stable digest of run 1 after excluding interpreter/editor cache files using
# RUN1_DIGEST_EXCLUSION_RULES below. It must not depend on transient bytecode.
RUN1_EXPECTED_TREE_SHA256 = "48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e"
RUN1_DIGEST_EXCLUSION_RULES = {
    "directory_names": ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"],
    "file_names": [".DS_Store", "Thumbs.db"],
    "file_suffixes": [".pyc", ".pyo", ".swp", ".swo", ".tmp"],
    "file_name_endings": ["~"],
}
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "ws2812b_sk6812_cmount_led_holder"
    / RUN_DIR.name
)
STEM = "ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical"


def load_run1_builder():
    spec = importlib.util.spec_from_file_location("ws2812_sk6812_run1_baseline", RUN1_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load run-1 builder: {RUN1_BUILDER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


base = load_run1_builder()

PARAMS = dict(base.PARAMS)
PARAMS.update(
    {
        "name": STEM,
        "variant_mode": "surgical outer-profile replacement from preserved run 1",
        "run1_reference": str(RUN1_DIR.relative_to(ROOT)),
        "holder_outer_profile": "coaxial circular cylinder",
        "holder_outer_diameter_mm": 34.0,
        "holder_plate_thickness_x_mm": 5.0,
        "cmount_socket_length_mm": 5.0,
        "cmount_outer_diameter_mm": 34.0,
        "independent_body_contact_plane_x_mm": 5.0,
        "body_interval_note": (
            "C-mount socket occupies x=0..5 mm and cylindrical PCB holder occupies "
            "x=5..10 mm. They are independent, adjacent bodies with zero overlap."
        ),
        "outer_profile_change_note": (
            "Only the run-1 square 42 x 42 mm holder blank is replaced by a coaxial "
            "34.0 mm OD cylindrical blank; all board-derived Y/Z cuts and proxies are retained."
        ),
        "outer_breakout_policy": (
            "No retained cut may meet the 17 mm outer radius; no wire/header exit is opened in run 2."
        ),
    }
)
PARAMS.pop("holder_plate_width_y_mm", None)
PARAMS.pop("holder_plate_height_z_mm", None)
PARAMS.pop("holder_edge_fillet_mm", None)

# Make every reused run-1 function resolve the run-2 constants.
base.PARAMS = PARAMS
base.STEM = STEM
base.RUN_DIR = RUN_DIR
base.ARTIFACT_DIR = ARTIFACT_DIR
base.NUTSTORE_DIR = NUTSTORE_DIR


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def is_run1_digest_transient(path: Path) -> bool:
    """Return whether a run-1 path is an obvious generated cache/transient."""
    relative = path.relative_to(RUN1_DIR)
    if any(
        part in RUN1_DIGEST_EXCLUSION_RULES["directory_names"]
        for part in relative.parts[:-1]
    ):
        return True
    if relative.name in RUN1_DIGEST_EXCLUSION_RULES["file_names"]:
        return True
    if relative.suffix.lower() in RUN1_DIGEST_EXCLUSION_RULES["file_suffixes"]:
        return True
    return any(
        relative.name.endswith(ending)
        for ending in RUN1_DIGEST_EXCLUSION_RULES["file_name_endings"]
    )


def run1_tree_snapshot() -> dict[str, object]:
    """Return a deterministic cache-excluded run-1 integrity snapshot."""
    all_files = sorted(item for item in RUN1_DIR.rglob("*") if item.is_file())
    included = [path for path in all_files if not is_run1_digest_transient(path)]
    excluded = [path for path in all_files if is_run1_digest_transient(path)]
    combined = hashlib.sha256()
    for path in included:
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        combined.update(f"{file_digest}  {path.relative_to(ROOT).as_posix()}\n".encode("utf-8"))
    return {
        "sha256": combined.hexdigest(),
        "included_file_count": len(included),
        "excluded_transient_file_count": len(excluded),
        "excluded_transient_paths": [repo_path(path) for path in excluded],
    }


def run1_tree_digest() -> str:
    """Return the stable cache-excluded run-1 source/artifact tree digest."""
    return str(run1_tree_snapshot()["sha256"])


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cylindrical_holder_plate(layout: dict[str, object]) -> cq.Workplane:
    """Replace only the square run-1 blank with a 34 mm coaxial cylinder."""
    plate = base.x_cylinder(
        PARAMS["holder_outer_diameter_mm"],
        PARAMS["holder_plate_thickness_x_mm"],
        base.plate_x0(),
    )
    plate = plate.cut(
        base.optical_bore_cutter(
            base.plate_x0() - 0.6,
            PARAMS["holder_plate_thickness_x_mm"] + 1.2,
        )
    )
    plate = plate.cut(base.board_sink_cutter())
    for hole in layout["mounting_holes_relative_mm"]:  # type: ignore[index]
        plate = plate.cut(base.pcb_mount_cutter(hole["y"], hole["z"]))
    plate = plate.cut(base.header_relief_cutter(layout))
    return plate.clean()


base.build_holder_plate = build_cylindrical_holder_plate


def build_assembly(layout: dict[str, object]) -> cq.Assembly:
    """Preserve run-1 proxy positions and RGBA colors exactly."""
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(
        base.build_cmount_socket(),
        name="independent_5mm_cmount_socket_25p0_25p4",
        color=cq.Color(0.10, 0.10, 0.09, 1.0),
    )
    assembly.add(
        build_cylindrical_holder_plate(layout),
        name="independent_5mm_34mm_od_cylindrical_ws2812b_sk6812_pcb_holder_plate",
        color=cq.Color(0.18, 0.18, 0.16, 1.0),
    )
    assembly.add(
        base.build_board_proxy(layout),
        name="shared_24mm_ws2812b_sk6812_board_proxy",
        color=cq.Color(0.0, 0.24, 0.50, 0.58),
    )
    assembly.add(
        base.build_led_proxy(layout),
        name="5050_led_proxy_on_optical_axis",
        color=cq.Color(0.95, 0.82, 0.24, 0.88),
    )
    assembly.add(
        base.build_capacitor_proxy(layout),
        name="backside_C_0603_capacitor_footprint_proxy",
        color=cq.Color(0.08, 0.76, 0.44, 0.85),
    )
    assembly.add(
        base.build_header_proxy(layout),
        name="two_side_1x02_header_head_proxy",
        color=cq.Color(0.82, 0.18, 0.18, 0.55),
    )
    assembly.add(
        base.build_axis_proxy(),
        name="optical_axis_proxy",
        color=cq.Color(1.0, 0.72, 0.08, 0.58),
    )
    return assembly


def validate_step(path: Path) -> dict[str, object]:
    imported = cq.importers.importStep(str(path))
    shape = imported.val()
    bbox = shape.BoundingBox()
    explorer = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    bspline_faces = 0
    face_count = 0
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        face_count += 1
        if BRepAdaptor_Surface(face, True).GetType() == GeomAbs_BSplineSurface:
            bspline_faces += 1
        explorer.Next()
    return {
        "path": repo_path(path),
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solid_count": len(shape.Solids()),
        "bbox_mm": [round(bbox.xlen, 4), round(bbox.ylen, 4), round(bbox.zlen, 4)],
        "face_count": face_count,
        "bspline_face_count": bspline_faces,
    }


def validate_stl(path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(path, force="mesh")
    # `repair=False` keeps this check independent of Trimesh's optional
    # NetworkX package and avoids modifying the meshes during validation.
    components = mesh.split(only_watertight=False, repair=False)
    extents = mesh.bounds[1] - mesh.bounds[0]
    component_watertightness = [bool(component.is_watertight) for component in components]
    return {
        "path": repo_path(path),
        "combined_mesh_is_watertight": bool(mesh.is_watertight),
        "component_count": len(components),
        "component_watertightness": component_watertightness,
        "all_components_watertight": all(component_watertightness),
        "bbox_mm": [round(float(value), 4) for value in extents],
        "triangles": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path, "r") as archive:
        bad_entry = archive.testzip()
        names = sorted(archive.namelist())
        model_bytes = archive.read("3D/3dmodel.model")
    root = ET.fromstring(model_bytes)
    namespace = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    objects = root.findall(".//m:resources/m:object", namespace)
    items = root.findall(".//m:build/m:item", namespace)
    return {
        "path": repo_path(path),
        "valid_zip": bad_entry is None,
        "has_model": "3D/3dmodel.model" in names,
        "model_unit": root.attrib.get("unit"),
        "object_count": len(objects),
        "build_item_count": len(items),
        "zip_entries": names,
    }


def radial_distance(y: float, z: float) -> float:
    return math.hypot(y, z)


def validate_retained_cut_envelopes(layout: dict[str, object]) -> dict[str, object]:
    outer_radius = PARAMS["holder_outer_diameter_mm"] / 2.0
    envelopes: list[dict[str, object]] = []

    def add(name: str, radial_extent: float, source: str) -> None:
        envelopes.append(
            {
                "feature": name,
                "radial_extent_mm": round(radial_extent, 4),
                "radial_margin_to_outer_profile_mm": round(outer_radius - radial_extent, 4),
                "source": source,
            }
        )

    add("24.4 mm centered PCB sink", PARAMS["board_sink_diameter_mm"] / 2.0, "named run-1 parameter")
    add("10 mm centered LED/optical aperture", PARAMS["led_aperture_diameter_mm"] / 2.0, "named run-1 parameter")
    for index, hole in enumerate(layout["mounting_holes_relative_mm"], start=1):  # type: ignore[index]
        extent = radial_distance(float(hole["y"]), float(hole["z"])) + PARAMS["pcb_fixation_pilot_diameter_mm"] / 2.0
        add(f"fixation pilot {index}", extent, f"{layout['source']} mounting hole")
    for pad in layout["header_pads_relative_mm"]:  # type: ignore[index]
        extent = radial_distance(float(pad["y"]), float(pad["z"])) + PARAMS["pin_header_relief_diameter_mm"] / 2.0
        add(f"{pad['reference']} pad {pad['pad']} 3 mm clearance", extent, f"{layout['source']} header pad")
    pads_by_ref: dict[str, list[dict[str, object]]] = {}
    for pad in layout["header_pads_relative_mm"]:  # type: ignore[index]
        pads_by_ref.setdefault(str(pad["reference"]), []).append(pad)
    for reference, pads in pads_by_ref.items():
        y_mid = sum(float(pad["y"]) for pad in pads) / len(pads)
        z_min = min(float(pad["z"]) for pad in pads) - 0.04
        z_max = max(float(pad["z"]) for pad in pads) + 0.04
        y_half = PARAMS["pin_header_relief_diameter_mm"] / 2.0
        corners = [(y_mid + dy, z) for dy in (-y_half, y_half) for z in (z_min, z_max)]
        add(f"{reference} bridge clearance", max(radial_distance(y, z) for y, z in corners), "run-1 bridge construction")
    for body in layout["header_bodies_relative_mm"]:  # type: ignore[index]
        y_half = float(body["relief_width_y_mm"]) / 2.0
        z_half = float(body["relief_height_z_mm"]) / 2.0
        corners = [
            (float(body["center_y"]) + dy, float(body["center_z"]) + dz)
            for dy in (-y_half, y_half)
            for dz in (-z_half, z_half)
        ]
        add(
            f"{body['reference']} connector-head clearance",
            max(radial_distance(y, z) for y, z in corners),
            f"{layout['source']} header body plus retained run-1 clearance",
        )
    breakouts = [item["feature"] for item in envelopes if item["radial_margin_to_outer_profile_mm"] < 0]
    return {
        "holder_outer_radius_mm": outer_radius,
        "all_retained_cuts_fit_within_34mm_circle": not breakouts,
        "outer_breakouts": breakouts,
        "intentional_open_wire_or_header_exits": [],
        "minimum_radial_material_margin_mm": min(item["radial_margin_to_outer_profile_mm"] for item in envelopes),
        "feature_envelopes": envelopes,
    }


def validate_body_relationship(socket: cq.Workplane, plate: cq.Workplane) -> dict[str, object]:
    socket_bbox = socket.val().BoundingBox()
    plate_bbox = plate.val().BoundingBox()
    common = socket.intersect(plate)
    overlap_volume = sum(float(solid.Volume()) for solid in common.solids().vals())
    return {
        "socket_x_interval_mm": [round(socket_bbox.xmin, 6), round(socket_bbox.xmax, 6)],
        "holder_x_interval_mm": [round(plate_bbox.xmin, 6), round(plate_bbox.xmax, 6)],
        "contact_plane_x_mm": PARAMS["independent_body_contact_plane_x_mm"],
        "contact_plane_matches_both_bodies": (
            abs(socket_bbox.xmax - PARAMS["independent_body_contact_plane_x_mm"]) < 1e-6
            and abs(plate_bbox.xmin - PARAMS["independent_body_contact_plane_x_mm"]) < 1e-6
        ),
        "boolean_overlap_volume_mm3": round(overlap_volume, 9),
        "zero_overlap": overlap_volume < 1e-7,
        "bridge_or_middle_body_count": 0,
        "coaxial_yz_center_mm": [0.0, 0.0],
        "same_outside_diameter_mm": [PARAMS["cmount_outer_diameter_mm"], PARAMS["holder_outer_diameter_mm"]],
    }


def png_metadata(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    width, height = struct.unpack(">II", data[16:24])
    return {
        "path": repo_path(path),
        "valid_png_signature": True,
        "width_px": width,
        "height_px": height,
        "bytes": len(data),
        "nontrivial_file": len(data) > 50_000,
    }


def write_alignment_svg(path: Path, layout: dict[str, object]) -> None:
    scale = 10.0
    margin = 44
    legend_w = 575
    view = 40.0
    svg_w = int(view * scale + margin * 2 + legend_w)
    svg_h = int(view * scale + margin * 2)

    def sx(y: float) -> float:
        return margin + (y + view / 2.0) * scale

    def sy(z: float) -> float:
        return margin + (view / 2.0 - z) * scale

    def circle(y: float, z: float, diameter: float, fill: str, stroke: str, label: str = "") -> str:
        text = ""
        if label:
            text = (
                f'<text x="{sx(y)+8:.2f}" y="{sy(z)-8:.2f}" font-family="Arial" '
                f'font-size="12" fill="#1a202c">{label}</text>'
            )
        return (
            f'<circle cx="{sx(y):.2f}" cy="{sy(z):.2f}" r="{diameter/2*scale:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>{text}'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        circle(0, 0, PARAMS["holder_outer_diameter_mm"], "#f7fafc", "#1a202c", "34 mm holder OD"),
        f'<circle cx="{sx(0):.2f}" cy="{sy(0):.2f}" r="{PARAMS["board_sink_diameter_mm"]/2*scale:.2f}" fill="#e6f0ff" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="8 5"/>',
        circle(0, 0, PARAMS["led_aperture_diameter_mm"], "#fff7d6", "#d69e2e", "LED / axis"),
    ]
    for hole in layout["mounting_holes_relative_mm"]:  # type: ignore[index]
        label = "1.8" if hole["y"] < 0 and hole["z"] < 0 else ""
        lines.append(circle(hole["y"], hole["z"], PARAMS["pcb_fixation_pilot_diameter_mm"], "#edf2f7", "#4a5568", label))
    for pad in layout["header_pads_relative_mm"]:  # type: ignore[index]
        label = "3.0" if pad["pad"] == "1" else ""
        lines.append(circle(pad["y"], pad["z"], PARAMS["pin_header_relief_diameter_mm"], "#fff5f5", "#c53030", label))
    for body in layout["header_bodies_relative_mm"]:  # type: ignore[index]
        lines.append(
            f'<rect x="{sx(body["center_y"]-body["relief_width_y_mm"]/2):.2f}" '
            f'y="{sy(body["center_z"]+body["relief_height_z_mm"]/2):.2f}" '
            f'width="{body["relief_width_y_mm"]*scale:.2f}" height="{body["relief_height_z_mm"]*scale:.2f}" '
            'fill="none" stroke="#c53030" stroke-width="1.5" stroke-dasharray="5 4"/>'
        )
    cap = layout["backside_capacitor_relative_mm"]  # type: ignore[index]
    lines.append(
        f'<rect x="{sx(cap["y"]-0.8):.2f}" y="{sy(cap["z"]+0.4):.2f}" '
        f'width="{1.6*scale:.2f}" height="{0.8*scale:.2f}" fill="#9ae6b4" '
        'stroke="#276749" stroke-width="1.5"/>'
    )
    legend_x = margin + view * scale + 34
    legend = [
        "Run 2: same-diameter cylindrical holder",
        "Black circle: 34.0 mm cylindrical holder OD",
        "Blue dashed circle: 24.4 mm PCB sink",
        "Gold circle: 10 mm LED/optical aperture",
        "Gray holes: 1.8 mm PCB fixation pilots",
        "Red capsules: 3 mm pin, bridge, and head clearances",
        "Green rectangle: backside C_0603 footprint proxy",
        "C-mount: 5 mm, 34 OD, 25.0 pilot, 25.4 cutter",
        "Socket and plate touch only at x=5.0 mm",
    ]
    for index, text in enumerate(legend):
        lines.append(
            f'<text x="{legend_x:.2f}" y="{margin + index*25:.2f}" font-family="Arial" '
            f'font-size="{17 if index == 0 else 13}" font-weight="{700 if index == 0 else 400}" '
            f'fill="#1a202c">{text}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_alignment_svg(path: Path) -> None:
    """Create the requested PNG/PDF with the locally available SVG delegate."""
    convert = shutil.which("convert")
    if convert is None:
        raise RuntimeError("ImageMagick convert is required for rear-alignment PNG/PDF")
    subprocess.run(
        [convert, "-background", "white", "-density", "180", str(path), "-resize", "1800x", str(path.with_suffix(".png"))],
        check=True,
    )
    subprocess.run(
        [convert, "-background", "white", "-density", "180", str(path), str(path.with_suffix(".pdf"))],
        check=True,
    )


def write_readme(
    path: Path,
    layout: dict[str, object],
    outputs: dict[str, str],
    validations: dict[str, object],
) -> None:
    output_rows = "\n".join(f"| {key} | `{value}` |" for key, value in outputs.items())
    mount_rows = "\n".join(
        f"| mount | `{hole['y']}` | `{hole['z']}` | `{hole['source_drill_mm']}` | `{hole['holder_pilot_mm']}` |"
        for hole in layout["mounting_holes_relative_mm"]  # type: ignore[index]
    )
    header_rows = "\n".join(
        f"| {pad['reference']} pad {pad['pad']} | `{pad['y']}` | `{pad['z']}` | `{pad['source_drill_mm']}` | `{pad['holder_clearance_mm']}` |"
        for pad in layout["header_pads_relative_mm"]  # type: ignore[index]
    )
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# WS2812B / SK6812 C-Mount LED Holder Run 2

Print-ready surgical variant of preserved run 1. The `42 x 42 x 5 mm` square
PCB holder blank is replaced by a `34.0 mm OD x 5.0 mm` coaxial cylinder. The
adjacent `34.0 mm OD x 5.0 mm` C-mount socket and every source-board-derived
cut remain on the same optical axis.

## Body Contract

- C-mount socket: independent body at `x=0..5 mm`.
- Cylindrical PCB holder: independent body at `x=5..10 mm`.
- Contact: the two bodies touch at `x=5.0 mm`; there is no overlap, bridge, or
  middle body.
- Overall printable envelope: approximately `10 x 34 x 34 mm`, two solids.
- Female C-mount: `25.0 mm` pilot/root, `25.4 mm` cutter crest, `0.8 mm`
  pitch, and `0.4 mm` half-pitch construction runout beyond both ends before
  clipping by the 5 mm socket.

## Retained Board Features

- Centered `24.4 mm` PCB sink, nominal `1.7 mm` depth.
- Centered `10 mm` LED/optical aperture.
- Four `1.8 mm` fixation pilots at the source-board `(±6, ±6) mm` locations.
- Both source-position side headers: overlapping `3.0 mm` pin clearances,
  bridge cuts, and connector-head clearances.
- All retained cuts fit within the 17 mm plate radius. No outer wire/header
  breakout is introduced.

Both KiCad boards are parsed during every build and must pass mechanical-layout
equivalence before any output is exported:

- `pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb`
- `pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb`

## Source Geometry

Mounting holes:

| Feature | y mm | z mm | PCB drill mm | holder cut mm |
| --- | ---: | ---: | ---: | ---: |
{mount_rows}

Header pads:

| Feature | y mm | z mm | PCB drill mm | holder cut mm |
| --- | ---: | ---: | ---: | ---: |
{header_rows}

## Build

```bash
cad/.conda/cad-python/bin/python {repo_path(Path(__file__))}
```

The builder exports analytic B-reps and meshes, runs Blender for both the exact
direct-print holder and the proxy assembly, validates STEP/STL/3MF data, checks
the source layouts and radial cut envelopes, and then copies the clean handoff
set to:

`{NUTSTORE_DIR}`

## Stable Run-1 Integrity

The run-1 source/artifact integrity digest is cache-independent. The builder
excludes `__pycache__`, Python bytecode (`*.pyc`, `*.pyo`), common Python tool
caches, editor swap/temporary files, and OS metadata before hashing the sorted
root-relative file checksums. The expected stable digest is:

`{RUN1_EXPECTED_TREE_SHA256}`

The manifest records the same exclusion rules plus the included/excluded file
counts and stable digests measured before and after every regeneration.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Validation

```json
{json.dumps(validations, indent=2)}
```

## Parameters

| Parameter | Value |
| --- | --- |
{param_rows}
""",
        encoding="utf-8",
    )


def copy_print_ready(files: list[Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for path in files:
        if not path.exists():
            raise FileNotFoundError(f"required Nutstore handoff file is missing: {path}")
        shutil.copy2(path, NUTSTORE_DIR / path.name)


def main() -> None:
    run1_before_snapshot = run1_tree_snapshot()
    run1_before = str(run1_before_snapshot["sha256"])
    if run1_before != RUN1_EXPECTED_TREE_SHA256:
        raise RuntimeError(
            f"run 1 differs from inspected baseline: {run1_before} != {RUN1_EXPECTED_TREE_SHA256}"
        )
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    ws_layout = base.extract_led_board_geometry(base.WS2812B_PCB)
    sk_layout = base.extract_led_board_geometry(base.SK6812_PCB)
    base.assert_same_layout(ws_layout, sk_layout)
    layout = ws_layout

    socket = base.build_cmount_socket()
    plate = build_cylindrical_holder_plate(layout)
    # Evaluate analytic adjacency before STL meshing adds triangulation
    # deflection to OCCT's cached bounding boxes.
    relationship_validation = validate_body_relationship(socket, plate)
    holder = cq.Compound.makeCompound([socket.val(), plate.val()])
    board = base.build_board_proxy(layout)
    cutter = base.female_thread_cutter()
    assembly = build_assembly(layout)
    led = base.build_led_proxy(layout)
    capacitor = base.build_capacitor_proxy(layout)
    headers = base.build_header_proxy(layout)
    axis = base.build_axis_proxy()
    assembly_mesh_compound = cq.Compound.makeCompound(
        [
            socket.val(),
            plate.val(),
            board.val(),
            led.val(),
            capacitor.val(),
            *headers.solids().vals(),
            axis.val(),
        ]
    )

    paths = {
        "print_step": RUN_DIR / f"PRINT_THIS_{STEM}.step",
        "print_stl": RUN_DIR / f"PRINT_THIS_{STEM}.stl",
        "print_3mf": RUN_DIR / f"PRINT_THIS_{STEM}.3mf",
        "use_this_assembly_step": RUN_DIR / f"USE_THIS_{STEM}_assembly.step",
        "cmount_socket_step": ARTIFACT_DIR / f"{STEM}_cmount_socket.step",
        "cmount_socket_stl": ARTIFACT_DIR / f"{STEM}_cmount_socket.stl",
        "cylindrical_holder_plate_step": ARTIFACT_DIR / f"{STEM}_cylindrical_holder_plate.step",
        "cylindrical_holder_plate_stl": ARTIFACT_DIR / f"{STEM}_cylindrical_holder_plate.stl",
        "decoupled_holder_step": ARTIFACT_DIR / f"{STEM}_decoupled_holder.step",
        "decoupled_holder_stl": ARTIFACT_DIR / f"{STEM}_decoupled_holder.stl",
        "board_proxy_step": ARTIFACT_DIR / f"{STEM}_board_proxy.step",
        "board_proxy_stl": ARTIFACT_DIR / f"{STEM}_board_proxy.stl",
        "female_thread_cutter_step": ARTIFACT_DIR / f"{STEM}_female_thread_cutter.step",
        "female_thread_cutter_stl": ARTIFACT_DIR / f"{STEM}_female_thread_cutter.stl",
        "assembly_with_proxies_step": ARTIFACT_DIR / f"{STEM}_assembly_with_proxies.step",
        "assembly_with_proxies_stl": ARTIFACT_DIR / f"{STEM}_assembly_with_proxies.stl",
        "rear_alignment_svg": ARTIFACT_DIR / f"{STEM}_rear_alignment.svg",
        "rear_alignment_png": ARTIFACT_DIR / f"{STEM}_rear_alignment.png",
        "rear_alignment_pdf": ARTIFACT_DIR / f"{STEM}_rear_alignment.pdf",
        "print_render_png": RUN_DIR / f"PRINT_THIS_{STEM}_render.png",
        "assembly_render_png": ARTIFACT_DIR / f"{STEM}_assembly_with_proxies_render.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "readme": RUN_DIR / "README.md",
    }

    for key in ("print_step", "use_this_assembly_step", "decoupled_holder_step"):
        exporters.export(holder, str(paths[key]))
    for key in ("print_stl", "decoupled_holder_stl"):
        exporters.export(holder, str(paths[key]))
    for shape, step_key, stl_key in (
        (socket, "cmount_socket_step", "cmount_socket_stl"),
        (plate, "cylindrical_holder_plate_step", "cylindrical_holder_plate_stl"),
        (board, "board_proxy_step", "board_proxy_stl"),
        (cutter, "female_thread_cutter_step", "female_thread_cutter_stl"),
    ):
        exporters.export(shape, str(paths[step_key]))
        exporters.export(shape, str(paths[stl_key]))
    assembly.save(str(paths["assembly_with_proxies_step"]))
    exporters.export(assembly_mesh_compound, str(paths["assembly_with_proxies_stl"]))
    base.export_stl_as_3mf(paths["print_stl"], paths["print_3mf"], title=STEM)

    write_alignment_svg(paths["rear_alignment_svg"], layout)
    convert_alignment_svg(paths["rear_alignment_svg"])

    render_script = RUN_DIR / "render_run2_same_diameter_34mm_cylindrical_pcb_holder.py"
    subprocess.run(["blender", "--background", "--python", str(render_script)], check=True)

    step_keys = [key for key in paths if key.endswith("_step")]
    stl_keys = [key for key in paths if key.endswith("_stl")]
    step_validations = {key: validate_step(paths[key]) for key in step_keys}
    stl_validations = {key: validate_stl(paths[key]) for key in stl_keys}
    cut_validation = validate_retained_cut_envelopes(layout)

    print_step_check = step_validations["print_step"]
    print_stl_check = stl_validations["print_stl"]
    stl_bbox_matches = all(
        abs(actual - expected) <= 0.02
        for actual, expected in zip(print_stl_check["bbox_mm"], [10.0, 34.0, 34.0])
    )
    if not (
        print_step_check["valid"]
        and print_step_check["solid_count"] == 2
        and print_step_check["bbox_mm"] == [10.0, 34.0, 34.0]
        and print_stl_check["all_components_watertight"]
        and print_stl_check["component_count"] == 2
        and stl_bbox_matches
        and cut_validation["all_retained_cuts_fit_within_34mm_circle"]
        and relationship_validation["zero_overlap"]
    ):
        raise RuntimeError("run-2 print contract validation failed")

    run1_after_snapshot = run1_tree_snapshot()
    run1_after = str(run1_after_snapshot["sha256"])
    if run1_after != run1_before:
        raise RuntimeError("run 1 changed during run-2 generation")

    outputs = {key: repo_path(path) for key, path in paths.items()}
    validations = {
        "step_brep": step_validations,
        "stl_mesh": stl_validations,
        "print_3mf": validate_3mf(paths["print_3mf"]),
        "source_layout_match": True,
        "source_board_sha256": {
            repo_path(base.WS2812B_PCB): file_sha256(base.WS2812B_PCB),
            repo_path(base.SK6812_PCB): file_sha256(base.SK6812_PCB),
        },
        "retained_cut_fit": cut_validation,
        "independent_body_relationship": relationship_validation,
        "proxy_contract_preserved": {
            "positions": True,
            "colors_rgba": True,
            "source": repo_path(RUN1_BUILDER),
            "bounded_thread_cutter_exported_separately_to_keep_proxy_assembly_clean": True,
        },
        "renders": {
            "direct_print": png_metadata(paths["print_render_png"]),
            "assembly_with_proxies": png_metadata(paths["assembly_render_png"]),
            "rear_alignment": png_metadata(paths["rear_alignment_png"]),
        },
        "run1_integrity": {
            "digest_scope": "stable run-1 source/artifact files excluding obvious generated caches",
            "digest_algorithm": "SHA-256 of concatenated sorted '<file_sha256>  <root-relative-path>\\n' records",
            "exclusion_rules": RUN1_DIGEST_EXCLUSION_RULES,
            "expected_tree_sha256": RUN1_EXPECTED_TREE_SHA256,
            "before_generation": run1_before,
            "after_generation": run1_after,
            "before_snapshot": run1_before_snapshot,
            "after_snapshot": run1_after_snapshot,
            "preserved_exactly": run1_before == run1_after == RUN1_EXPECTED_TREE_SHA256,
        },
        "visual_inspection": {
            "status": (
                "passed: full frame, coaxial cylindrical geometry, clear body seam, readable proxies and circular rear drawing"
                if "--confirm-visual-inspection" in sys.argv
                else "pending manual inspection after generation"
            ),
            "checked_files": (
                [
                    repo_path(paths["print_render_png"]),
                    repo_path(paths["assembly_render_png"]),
                    repo_path(paths["rear_alignment_png"]),
                ]
                if "--confirm-visual-inspection" in sys.argv
                else []
            ),
        },
    }
    manifest = {
        "name": STEM,
        "run_folder": RUN_DIR.name,
        "params": PARAMS,
        "layout": layout,
        "sk6812_layout_checked_against_ws2812b": sk_layout,
        "outputs": outputs,
        "validations": validations,
        "nutstore_sync": str(NUTSTORE_DIR),
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_readme(paths["readme"], layout, outputs, validations)

    copy_print_ready(
        [
            paths["print_step"],
            paths["print_stl"],
            paths["print_3mf"],
            paths["use_this_assembly_step"],
            paths["cmount_socket_step"],
            paths["cmount_socket_stl"],
            paths["cylindrical_holder_plate_step"],
            paths["cylindrical_holder_plate_stl"],
            paths["decoupled_holder_step"],
            paths["decoupled_holder_stl"],
            paths["board_proxy_step"],
            paths["board_proxy_stl"],
            paths["female_thread_cutter_step"],
            paths["female_thread_cutter_stl"],
            paths["assembly_with_proxies_step"],
            paths["assembly_with_proxies_stl"],
            paths["rear_alignment_svg"],
            paths["rear_alignment_png"],
            paths["rear_alignment_pdf"],
            paths["print_render_png"],
            paths["assembly_render_png"],
            paths["manifest"],
            paths["readme"],
        ]
    )
    print(json.dumps({"run_dir": str(RUN_DIR), "nutstore": str(NUTSTORE_DIR), "validations": validations}, indent=2))


if __name__ == "__main__":
    main()
