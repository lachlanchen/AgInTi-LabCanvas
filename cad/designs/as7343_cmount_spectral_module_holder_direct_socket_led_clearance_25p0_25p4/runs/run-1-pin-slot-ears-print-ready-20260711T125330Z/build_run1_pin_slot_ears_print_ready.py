#!/usr/bin/env python3
"""Build a print-ready AS7343 holder run with the current 3 mm pin slot and ears."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import trimesh
from cadquery import exporters
from OCP.BRepCheck import BRepCheck_Analyzer


RUN_DIR = Path(__file__).resolve().parent
DESIGN_DIR = RUN_DIR.parents[1]
ARTIFACT_DIR = RUN_DIR / "artifacts"
SOURCE_BUILD = DESIGN_DIR / "build_as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4.py"
STEM = "as7343_pin_slot_ears_print_ready"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4"
    / RUN_DIR.name
)


def find_repo_root() -> Path:
    for parent in RUN_DIR.parents:
        if (parent / "cad/tools/simple_3mf.py").exists():
            return parent
    raise RuntimeError("Cannot locate repo root with cad/tools/simple_3mf.py")


ROOT = find_repo_root()
sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402


def load_source_module():
    spec = importlib.util.spec_from_file_location("as7343_current_build", SOURCE_BUILD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load source build script: {SOURCE_BUILD}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SRC = load_source_module()


RUN_PARAMS = {
    "run_name": RUN_DIR.name,
    "source_design": str(DESIGN_DIR.relative_to(ROOT)),
    "source_commit_note": "Run generated from the current AS7343 25.0/25.4 holder with the 3.0 mm connected pin-header slot.",
    "print_orientation": "rear-face-down: original X axis rotated to print Z, PCB tray side on the build plate, C-mount rising upward",
    "anti_warp_ears_enabled": True,
    "anti_warp_ear_count": 4,
    "anti_warp_ear_thickness_mm": 1.0,
    "anti_warp_ear_side_contact_mm": 5.0,
    "anti_warp_ear_reach_mm": 10.0,
    "anti_warp_ear_breakaway_overlap_mm": 5.0,
    "anti_warp_ear_corner_pad_mm": 8.0,
    "anti_warp_ear_diagonal_pad_mm": 10.0,
    "anti_warp_ear_diagonal_pad_overlap_mm": 4.0,
    "anti_warp_ear_note": "Each ear is a filled sacrificial rear-face tab: 5 mm side contacts, a filled corner pad, and a diagonal pull pad. The inboard overlap is 5 mm so the ears fuse into the flat plate despite the rounded holder corners; removability comes from the 1.0 mm layer thickness.",
    "print_weld_overlap_mm": 0.1,
    "print_weld_note": "The print export adds a hidden 0.1 mm overlap disk at the original C-mount/socket contact plane so the slicer receives one connected body. This does not change the visible envelope.",
    "pin_header_relief_mm": SRC.PARAMS["pin_header_hole_diameter_mm"],
    "pin_header_pitch_mm": SRC.PARAMS["pin_header_hole_pitch_z_mm"],
    "pin_header_relief_note": "Pin reservation is unchanged from the current design: 3.0 mm holes on 2.54 mm pitch, bridged into one continuous slot.",
}


def repo_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def rear_face_box(y_center: float, z_center: float, y_size: float, z_size: float) -> cq.Workplane:
    thickness = RUN_PARAMS["anti_warp_ear_thickness_mm"]
    x_center = SRC.total_length() - thickness / 2.0
    return SRC.x_box((x_center, y_center, z_center), (thickness, y_size, z_size))


def anti_warp_corner_ear(sign_y: int, sign_z: int) -> cq.Workplane:
    half_y = SRC.PARAMS["sensor_plate_width_y_mm"] / 2.0
    half_z = SRC.PARAMS["sensor_plate_height_z_mm"] / 2.0
    contact = RUN_PARAMS["anti_warp_ear_side_contact_mm"]
    reach = RUN_PARAMS["anti_warp_ear_reach_mm"]
    overlap = RUN_PARAMS["anti_warp_ear_breakaway_overlap_mm"]
    corner = RUN_PARAMS["anti_warp_ear_corner_pad_mm"]
    diagonal = RUN_PARAMS["anti_warp_ear_diagonal_pad_mm"]
    diagonal_overlap = RUN_PARAMS["anti_warp_ear_diagonal_pad_overlap_mm"]

    ear = rear_face_box(
        sign_y * (half_y + (reach - overlap) / 2.0),
        sign_z * (half_z - contact / 2.0),
        reach + overlap,
        contact,
    )
    ear = ear.union(
        rear_face_box(
            sign_y * (half_y - contact / 2.0),
            sign_z * (half_z + (reach - overlap) / 2.0),
            contact,
            reach + overlap,
        )
    )
    ear = ear.union(
        rear_face_box(
            sign_y * (half_y + corner / 2.0),
            sign_z * (half_z + corner / 2.0),
            corner,
            corner,
        )
    )
    ear = ear.union(
        rear_face_box(
            sign_y * (half_y + reach + diagonal / 2.0 - diagonal_overlap),
            sign_z * (half_z + reach + diagonal / 2.0 - diagonal_overlap),
            diagonal,
            diagonal,
        )
    )
    return ear.clean()


def build_sensor_plate_with_ears() -> cq.Workplane:
    plate = SRC.build_sensor_plate_body()
    for sign_y in (-1, 1):
        for sign_z in (-1, 1):
            plate = plate.union(anti_warp_corner_ear(sign_y, sign_z))
    return plate.clean()


def build_holder_with_ears_compound() -> cq.Compound:
    return cq.Compound.makeCompound([SRC.build_cmount_socket_body().val(), build_sensor_plate_with_ears().val()])


def build_print_holder_with_ears_solid() -> cq.Workplane:
    weld = SRC.x_cylinder(
        SRC.PARAMS["socket_outer_diameter_mm"],
        RUN_PARAMS["print_weld_overlap_mm"] * 2.0,
        SRC.sensor_plate_x0() - RUN_PARAMS["print_weld_overlap_mm"],
    )
    holder = SRC.build_cmount_socket_body().union(weld).union(build_sensor_plate_with_ears())
    return holder.clean()


def workplane_from_shape(shape: cq.Shape) -> cq.Workplane:
    return cq.Workplane("XY").newObject([shape])


def build_print_layout() -> cq.Workplane:
    holder = build_print_holder_with_ears_solid()
    return holder.rotate((0, 0, 0), (0, 1, 0), 90).translate((0, 0, SRC.total_length()))


def mesh_checks(stl_path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(stl_path, force="mesh")
    return {
        "watertight": bool(mesh.is_watertight),
        "component_count": mesh_component_count(mesh),
        "bounds_mm": {
            "min": [round(float(v), 3) for v in mesh.bounds[0]],
            "max": [round(float(v), 3) for v in mesh.bounds[1]],
            "size": [round(float(v), 3) for v in (mesh.bounds[1] - mesh.bounds[0])],
        },
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }


def mesh_component_count(mesh: trimesh.Trimesh) -> int:
    face_count = len(mesh.faces)
    if face_count == 0:
        return 0
    parent = list(range(face_count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for a, b in mesh.face_adjacency:
        union(int(a), int(b))
    return len({find(index) for index in range(face_count)})


def step_checks(step_path: Path) -> dict[str, object]:
    shape = cq.importers.importStep(str(step_path)).val()
    bb = shape.BoundingBox()
    return {
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solids": len(shape.Solids()),
        "bounds_mm": [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)],
    }


def validate_3mf(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return sorted(archive.namelist())


def sync_to_nutstore(files: list[Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for src in files:
        if src.exists():
            shutil.copy2(src, NUTSTORE_DIR / src.name)


def write_readme(path: Path, outputs: dict[str, str], checks: dict[str, object]) -> None:
    path.write_text(
        f"""# AS7343 Pin-Slot Holder Print-Ready Run

This run keeps the current AS7343 holder geometry and the current `3.0 mm`
connected pin-header reservation slot. The only geometry added is four
removable anti-warp ears on the rear print face.

## Print This

Use the root `PRINT_THIS_*` files in this run folder:

- `PRINT_THIS_{STEM}.3mf`
- `PRINT_THIS_{STEM}.stl`
- `PRINT_THIS_{STEM}.step`

The print files are already rotated to a rear-face-down orientation: the PCB
tray side is on the build plate and the C-mount rises upward.

## Ears

- Thickness: `{RUN_PARAMS['anti_warp_ear_thickness_mm']} mm`
- Side contact on each adjacent edge: `{RUN_PARAMS['anti_warp_ear_side_contact_mm']} mm`
- Four filled corner/diagonal sacrificial tabs
- Remove after printing with a knife or flush cutter.

## Outputs

```json
{json.dumps(outputs, ensure_ascii=False, indent=2)}
```

## Validation

```json
{json.dumps(checks, ensure_ascii=False, indent=2)}
```
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    holder = build_print_holder_with_ears_solid()
    print_layout = build_print_layout()

    design_step = ARTIFACT_DIR / f"{STEM}_design_orientation_with_ears.step"
    design_stl = ARTIFACT_DIR / f"{STEM}_design_orientation_with_ears.stl"
    print_step = ARTIFACT_DIR / f"{STEM}_print_layout.step"
    print_stl = ARTIFACT_DIR / f"{STEM}_print_layout.stl"
    print_3mf = ARTIFACT_DIR / f"{STEM}_print_layout.3mf"
    manifest = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder, str(design_step))
    exporters.export(holder, str(design_stl))
    exporters.export(print_layout, str(print_step))
    exporters.export(print_layout, str(print_stl))
    export_stl_as_3mf(print_stl, print_3mf, title=f"{STEM} print layout")

    print_this_step = RUN_DIR / f"PRINT_THIS_{STEM}.step"
    print_this_stl = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
    print_this_3mf = RUN_DIR / f"PRINT_THIS_{STEM}.3mf"
    shutil.copy2(print_step, print_this_step)
    shutil.copy2(print_stl, print_this_stl)
    shutil.copy2(print_3mf, print_this_3mf)

    outputs = {
        "design_orientation_step": repo_path(design_step),
        "design_orientation_stl": repo_path(design_stl),
        "print_layout_step": repo_path(print_step),
        "print_layout_stl": repo_path(print_stl),
        "print_layout_3mf": repo_path(print_3mf),
        "print_this_step": repo_path(print_this_step),
        "print_this_stl": repo_path(print_this_stl),
        "print_this_3mf": repo_path(print_this_3mf),
        "render_png": repo_path(RUN_DIR / f"PRINT_THIS_{STEM}_render.png"),
        "manifest": repo_path(manifest),
        "nutstore_folder": str(NUTSTORE_DIR),
    }
    checks = {
        "source_pin_header_relief_mm": SRC.PARAMS["pin_header_hole_diameter_mm"],
        "source_pin_header_pitch_mm": SRC.PARAMS["pin_header_hole_pitch_z_mm"],
        "print_step": step_checks(print_step),
        "print_stl": mesh_checks(print_stl),
        "print_3mf_entries": validate_3mf(print_3mf),
    }

    manifest.write_text(
        json.dumps(
            {
                "name": STEM,
                "run_params": RUN_PARAMS,
                "source_params": SRC.PARAMS,
                "source_reference_geometry": SRC.board_reference_geometry(),
                "outputs": outputs,
                "validation": checks,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_readme(RUN_DIR / "README.md", outputs, checks)
    sync_to_nutstore([print_this_step, print_this_stl, print_this_3mf, RUN_DIR / "README.md", manifest])

    print(json.dumps({"outputs": outputs, "validation": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
