#!/usr/bin/env python3
"""Build run 6 by widening only run 5's bottom ejector passages."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path


DESIGN_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DESIGN_DIR.parents[1]
RUN5_DIR = PROJECT_DIR / "runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z"
RUN5_SCRIPT = RUN5_DIR / "build_run5_m10p1_socket_m6p2_bottom_ejector.py"


def load_run5():
    spec = importlib.util.spec_from_file_location("cage_dock_run5", RUN5_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load run-5 source: {RUN5_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run5 = load_run5()
STEM = "cage_rod_dock_100mm_base_m10p1_socket_m6p4_bottom_ejector"
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "cage_rod_dock_100mm_base_10mm_holes"
    / "run-6-m10p1-socket-m6p4-bottom-ejector-print-ready"
)
PARAMS = dict(run5.PARAMS)
PARAMS.update(
    {
        "name": STEM,
        "design_intent": (
            "Preserve run 5 exactly while widening only the four coaxial bottom "
            "ejector passages from 6.2 mm to 6.4 mm."
        ),
        "bottom_ejector_diameter_mm": 6.4,
        "ejector_function": (
            "Insert a 6 mm metal push rod from the underside through the 6.4 mm passage "
            "to drive a tight M10 adapter out of the top socket."
        ),
        "print_orientation": (
            "Print flat on the 100 x 100 mm base with the four 10.1 mm sockets opening upward; "
            "the four 6.4 mm ejector passages open against the build plate."
        ),
    }
)


def write_top_svg(path: Path) -> None:
    run5.RUN4_WRITE_TOP_SVG(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Run 4 M6 dock with 10 mm side-contact ears",
        "Run 6 M10.1 dock with M6.4 bottom ejectors",
    )
    text = text.replace(
        "Rod holes: 10.1 mm diameter, 20 mm deep",
        "Top sockets: 10.1 mm diameter x 20 mm; bottom ejectors: 6.4 mm diameter x 5 mm",
    )
    path.write_text(text, encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str], checks: dict[str, object]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# Run 6: M10.1 Socket With M6.4 Bottom Ejector

This is a surgical fit adjustment derived from run 5. The only geometric change
is widening each bottom ejector passage from `6.2 mm` to `6.4 mm`.

## Geometry

- Base: `100 x 100 x 25 mm`, unchanged.
- Socket centers: `x/y = +/-15 mm`, unchanged.
- Top sockets: `10.1 mm` diameter and `20.0 mm` deep, unchanged.
- Bottom ejector passages: `6.4 mm` diameter through the remaining `5.0 mm`.
- Strong ears: unchanged, `1.0 mm` thick with `10.0 mm` contact along both
  adjoining edges.

Insert a 6 mm steel push rod from below and tap it to eject a tight M10 adapter.
Print flat with the M10.1 sockets facing upward, then clear first-layer residue
from the bottom ejector openings.

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
            [blender, "--background", "--python", str(DESIGN_DIR / "render_run6_m10p1_socket_m6p4_bottom_ejector.py")],
            check=True,
        )


def main() -> None:
    run5.DESIGN_DIR = DESIGN_DIR
    run5.ARTIFACT_DIR = ARTIFACT_DIR
    run5.STEM = STEM
    run5.NUTSTORE_DIR = NUTSTORE_DIR
    run5.PARAMS = PARAMS
    run5.write_top_svg = write_top_svg
    run5.write_readme = write_readme
    run5.render_with_blender = render_with_blender
    run5.main()

    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_by"] = Path(__file__).name
    manifest["baseline_run"] = str(RUN5_DIR)
    manifest["geometry_delta"] = {
        "preserved": "all run-5 geometry and parameters",
        "changed": "bottom ejector diameter: 6.2 -> 6.4 mm",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(DESIGN_DIR / "README.md", manifest["outputs"], manifest["validation"])
    shutil.copy2(manifest_path, NUTSTORE_DIR / "manifest.json")
    shutil.copy2(DESIGN_DIR / "README.md", NUTSTORE_DIR / "README.md")


if __name__ == "__main__":
    main()
