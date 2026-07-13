#!/usr/bin/env python3
"""Build run 5: 25 mm dock with M10.1 sockets and M6.2 ejector holes."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import cadquery as cq


DESIGN_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DESIGN_DIR.parents[1]
RUN4_DIR = PROJECT_DIR / "runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z"
RUN4_SCRIPT = RUN4_DIR / "build_run4_m6_strong_ears_10mm_side_contact.py"


def load_run4():
    spec = importlib.util.spec_from_file_location("cage_dock_run4", RUN4_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load run-4 source: {RUN4_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run4 = load_run4()
RUN4_WRITE_TOP_SVG = run4.write_top_svg
STEM = "cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector"
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "cage_rod_dock_100mm_base_10mm_holes"
    / "run-5-m10p1-socket-m6p2-bottom-ejector-print-ready"
)

PARAMS = dict(run4.PARAMS)
PARAMS.update(
    {
        "name": STEM,
        "design_intent": (
            "Preserve run-4 cage geometry and strong ears while changing the dock to "
            "a 25 mm plate with four top M10.1 sockets and coaxial M6.2 bottom ejector holes."
        ),
        "base_thickness_mm": 25.0,
        "top_socket_nominal_diameter_mm": 10.0,
        "top_socket_diameter_mm": 10.1,
        "top_socket_depth_mm": 20.0,
        "bottom_ejector_nominal_diameter_mm": 6.0,
        "bottom_ejector_diameter_mm": 6.2,
        "bottom_ejector_depth_mm": 5.0,
        "socket_shoulder_z_mm": 5.0,
        "rod_hole_diameter_mm": 10.1,
        "rod_hole_depth_mm": 20.0,
        "bottom_floor_thickness_mm": 5.0,
        "rod_proxy_diameter_mm": 10.0,
        "ejector_function": (
            "Insert a 6 mm metal push rod from the underside through the 6.2 mm passage "
            "to drive a tight M10 adapter out of the top socket."
        ),
        "print_orientation": (
            "Print flat on the 100 x 100 mm base with the four 10.1 mm sockets opening upward; "
            "the four 6.2 mm ejector passages open against the build plate."
        ),
    }
)


def build_dock() -> cq.Workplane:
    p = PARAMS
    part = run4.z_box(
        (p["base_width_mm"], p["base_height_mm"], p["base_thickness_mm"]),
        (0, 0, p["base_thickness_mm"] / 2.0),
    )
    top_socket_z = p["base_thickness_mm"] - p["top_socket_depth_mm"]
    for x, y in p["rod_hole_centers_mm"]:
        top_socket = run4.z_cylinder(
            p["top_socket_diameter_mm"],
            p["top_socket_depth_mm"] + 0.2,
            top_socket_z,
        ).translate((x, y, 0))
        bottom_ejector = run4.z_cylinder(
            p["bottom_ejector_diameter_mm"],
            p["bottom_ejector_depth_mm"] + 0.2,
            -0.1,
        ).translate((x, y, 0))
        part = part.cut(top_socket).cut(bottom_ejector)

    if p["edge_chamfer_mm"] > 0:
        part = part.edges("|Z").chamfer(p["edge_chamfer_mm"])
    if p["hole_mouth_chamfer_mm"] > 0:
        part = part.faces(">Z").edges().chamfer(p["hole_mouth_chamfer_mm"])
    return run4.add_anti_warp_ears(part)


def write_top_svg(path: Path) -> None:
    RUN4_WRITE_TOP_SVG(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Run 4 M6 dock with 10 mm side-contact ears",
        "Run 5 M10.1 dock with M6.2 bottom ejectors",
    )
    text = text.replace(
        "Rod holes: 10.1 mm diameter, 20 mm deep",
        "Top sockets: 10.1 mm diameter x 20 mm; bottom ejectors: 6.2 mm diameter x 5 mm",
    )
    path.write_text(text, encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str], checks: dict[str, object]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# Run 5: M10.1 Socket With M6.2 Bottom Ejector

This run preserves run 4's 100 mm square body, 30 mm cage-center geometry,
edge chamfers, and strong 1 mm anti-warp ears with 10 mm contact along both
adjacent sides. Only the plate thickness and four coaxial hole profiles change.

## Geometry

- Base: `100 x 100 x 25 mm`.
- Socket centers: `x/y = +/-15 mm`, unchanged from run 4.
- Top sockets: `10.1 mm` diameter and `20.0 mm` deep.
- Bottom ejector passages: `6.2 mm` diameter through the remaining `5.0 mm`.
- Internal shoulder: annulus from radius `3.1 mm` to `5.05 mm` at `z = 5 mm`.
- Ears: unchanged run-4 filled full-corner design, `1.0 mm` thick with
  `10.0 mm` contact along both adjoining edges.

The bottom passage is not another mounting socket. It is an ejector access hole:
insert a 6 mm steel rod from below and tap it to push a tight M10 adapter upward.

## Print Notes

Use the root `PRINT_THIS_*` file in this run folder. Print the dock flat with the
M10.1 sockets facing upward. The M6.2 openings will be on the build plate; clear
any first-layer elephant-foot or bridging residue before using the ejector rod.

Validation: STEP imports as `{checks['step_solid_count']}` solid; STL watertight
is `{checks['print_layout_stl']['watertight']}` with
`{checks['print_layout_stl']['component_count']}` component and bounds
`{checks['print_layout_stl']['bounds_mm']['size']} mm`.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}
""",
        encoding="utf-8",
    )


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if blender:
        subprocess.run(
            [blender, "--background", "--python", str(DESIGN_DIR / "render_run5_m10p1_socket_m6p2_bottom_ejector.py")],
            check=True,
        )


def main() -> None:
    run4.__file__ = str(Path(__file__).resolve())
    run4.DESIGN_DIR = DESIGN_DIR
    run4.ARTIFACT_DIR = ARTIFACT_DIR
    run4.STEM = STEM
    run4.NUTSTORE_DIR = NUTSTORE_DIR
    run4.PARAMS = PARAMS
    run4.build_dock = build_dock
    run4.write_top_svg = write_top_svg
    run4.write_readme = write_readme
    run4.render_with_blender = render_with_blender
    run4.main()

    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bottom_render = ARTIFACT_DIR / f"{STEM}_bottom_ejector_render.png"
    manifest["outputs"]["bottom_ejector_render_png"] = str(bottom_render.resolve())
    manifest["baseline_run"] = str(RUN4_DIR)
    manifest["geometry_delta"] = {
        "preserved": ["base XY outline", "cage centers", "edge chamfer", "strong anti-warp ears"],
        "changed": ["base Z: 30 -> 25 mm", "top socket: 6.4 x 25 -> 10.1 x 20 mm", "new bottom ejector: 6.2 x 5 mm"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(DESIGN_DIR / "README.md", manifest["outputs"], manifest["validation"])
    shutil.copy2(manifest_path, NUTSTORE_DIR / "manifest.json")
    shutil.copy2(DESIGN_DIR / "README.md", NUTSTORE_DIR / "README.md")
    if bottom_render.exists():
        shutil.copy2(bottom_render, NUTSTORE_DIR / bottom_render.name)


if __name__ == "__main__":
    main()
