#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render both optical holders, their sections and their actual print layouts."""

import json
import sys
from pathlib import Path

import bpy

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(DESIGN))
import render_stage as shared


def render(objects, path, direction, resolution):
    visible = [o for o in objects.values() if not o.hide_render]
    _, bounds = shared.studio.fit(visible, resolution, direction)
    if not path.exists():
        return shared.render(objects, path, direction, resolution)
    return {
        "path": str(path),
        "camera_bounds": bounds,
        "resolution": list(resolution),
        "visible_parts": [o.name for o in visible],
        "direction": list(direction),
        "reused_completed_image": True,
    }


def main():
    run = (
        ROOT
        / json.loads((DESIGN / "artifacts/polarizer_variant.json").read_text())[
            "run_dir"
        ]
    )
    data = json.loads((run / "manifest.json").read_text())
    records = []
    for variant, entry in data["variants"].items():
        folder = run / variant
        (folder / "renders").mkdir(exist_ok=True)
        mats, _ground = shared.setup(24)
        objects = shared.load(folder, entry["parts"], mats)
        records.append(
            render(
                objects,
                folder / "renders/assembled.png",
                (-1.5, -2.8, 2.1),
                (1100, 900),
            )
        )
        for name, obj in objects.items():
            if (
                name in ("polarizer_retainer",)
                or name.startswith("cap_M3")
                and "nut" not in name
            ):
                obj.location.z += 0.014
            elif name == "polarizer_gsp25_4p5mm":
                obj.location.z += 0.007
            elif name == "soft_upper_edge_pad":
                obj.location.z += 0.009
            elif name == "soft_lower_edge_pad":
                obj.location.z += 0.005
        records.append(
            render(
                objects,
                folder / "renders/exploded.png",
                (-1.5, -2.8, 1.6),
                (1000, 1200),
            )
        )
        mats, _ground = shared.setup(24)
        objects = shared.load(folder, entry["parts"], mats)
        # Render-only half-section; manufacturing meshes are never modified.
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.05, 0.1))
        cutter = bpy.context.object
        cutter.name = "explanatory_section_only"
        cutter.dimensions = (0.12, 0.1, 0.06)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        cutter.hide_render = True
        for name, obj in objects.items():
            if name.startswith(("existing_M3", "cap_M3")):
                obj.hide_render = True
                continue
            mod = obj.modifiers.new("Explanatory half section", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.solver = "EXACT"
            mod.object = cutter
        records.append(
            render(objects, folder / "renders/section.png", (0.3, -3, 1.0), (1100, 800))
        )
        for name, row in entry["print_validation"].items():
            mats, _ground = shared.setup(12)
            objects = shared.load(
                folder,
                {name: {"category": "polymer", "mesh": row["stem"] + ".stl"}},
                mats,
            )
            records.append(
                render(
                    objects,
                    folder / Path(row["stem"]).parent / "print_orientation.png",
                    (-1.5, -2.8, 2),
                    (650, 520),
                )
            )
        mats, _ground = shared.setup(20)
        objects = shared.load(folder, entry["parts"], mats)
        baseline = DESIGN / "runs" / data["base_run"]
        old = json.loads((baseline / "manifest.json").read_text())
        fixed = {
            name: row
            for name, row in old["parts"].items()
            if not name.startswith("polarizer_")
        }
        objects.update(shared.load(baseline, fixed, mats))
        records.append(
            render(
                objects,
                folder / "renders/installed_stage.png",
                (-1.8, -2.8, 1.8),
                (1100, 1000),
            )
        )
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / "editable_setup.blend"))
    for row in records:
        row["path"] = str(Path(row["path"]).relative_to(run))
    (run / "render_checks.json").write_text(
        json.dumps({"renders": records, "cpu_only": True, "threads": 6}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    main()
