#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CPU-only studio and exact print-orientation views for the current stage run."""

import importlib.util
import json
from pathlib import Path

import bpy
from mathutils import Vector

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
STUDIO = (
    ROOT
    / "cad/designs/openhi_vertical_multimodal_microscope_setup/render_publication.py"
)
spec = importlib.util.spec_from_file_location("publication_studio", STUDIO)
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


def setup(samples=40):
    mats, ground = studio.setup(samples)
    mats["polymer"] = studio.principled(
        "Teal printed rotor", (0.045, 0.30, 0.32), rough=0.36
    )
    mats["polymer_mid"] = studio.principled(
        "Graphite printed carrier", (0.09, 0.105, 0.12), rough=0.38
    )
    mats["belt"] = studio.principled(
        "Timing belt rubber", (0.012, 0.014, 0.018), rough=0.58
    )
    mats["motor_dark"] = studio.principled(
        "Motor laminations", (0.035, 0.037, 0.041), rough=0.34
    )
    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.location *= 0.25
            obj.data.energy *= 0.0625
            obj.data.size *= 0.25
            obj.rotation_euler = (
                (Vector((0.04, 0, 0.065)) - obj.location)
                .to_track_quat("-Z", "Y")
                .to_euler()
            )
    return mats, ground


def load(run, rows, mats):
    entry = {
        "render_components": [
            {
                "name": name,
                "category": row["category"],
                "source_mesh": str((run / row["mesh"]).relative_to(ROOT)),
            }
            for name, row in rows.items()
        ]
    }
    objects = studio.load_parts(entry, mats)
    motor = objects.get("motor_OpenHI_exact")
    if motor:
        motor.data.materials.append(mats["motor_dark"])
        for face in motor.data.polygons:
            if 0.045 <= face.center.z <= 0.075:
                face.material_index = 1
    return objects


def render(objects, path, direction, resolution=(1600, 1300)):
    visible = [obj for obj in objects.values() if not obj.hide_render]
    camera, bounds = studio.fit(visible, resolution, direction)
    scene = bpy.context.scene
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return {
        "path": str(path),
        "camera_bounds": bounds,
        "resolution": list(resolution),
        "visible_parts": [obj.name for obj in visible],
        "direction": list(direction),
    }


def main():
    latest = json.loads((DESIGN / "artifacts/latest.json").read_text())
    run = ROOT / latest["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    out = run / "renders"
    out.mkdir(exist_ok=True)
    records = []
    mats, ground = setup()
    objects = load(run, data["parts"], mats)
    records.append(render(objects, out / "assembled_overview.png", (-1.8, -2.8, 1.8)))
    for name, obj in objects.items():
        if name.startswith("polarizer_"):
            obj.hide_render = True
    records.append(render(objects, out / "bare_30mm_bore.png", (-1.8, -2.8, 2.1)))
    ground.hide_render = True
    records.append(render(objects, out / "underside_access.png", (-1.5, -2.8, -1.6)))

    # Explanatory decomposition, not an installed-state measurement or literal crop.
    offsets = {
        "rotor_cup": 15,
        "belt_backing_reference": 15,
        "purchased_20T_pulley_reference": 15,
        "rotor_cap": 58,
        "inner_race_retainer": 47,
        "polarizer_insert": 85,
        "polarizer_retainer": 100,
        "polarizer_1mm_reference": 85,
    }
    for name, obj in objects.items():
        obj.hide_render = False
        dz = offsets.get(
            name,
            35
            if name.startswith("bearing_")
            else 47
            if name.startswith("fixed_M2")
            else 0,
        )
        obj.location.z += dz * 0.001
    records.append(
        render(objects, out / "exploded_assembly.png", (-1.7, -3.2, 1.6), (1300, 1900))
    )

    prints = {**data["print_validation"], **data["fit_coupons"]}
    for name, row in prints.items():
        mats, ground = setup(16)
        path = run / (row["stem"] + ".stl")
        objects = load(
            run,
            {name: {"category": "polymer", "mesh": str(path.relative_to(run))}},
            mats,
        )
        record = render(
            objects,
            path.parent / "print_orientation.png",
            (-1.6, -2.4, 1.9),
            (700, 580),
        )
        record["print_part"] = name
        records.append(record)

    mats, ground = setup()
    objects = load(run, data["parts"], mats)
    studio.fit(list(objects.values()), (1600, 1300), (-1.8, -2.8, 1.8))
    bpy.ops.wm.save_as_mainfile(filepath=str(run / "editable_stage.blend"))
    for row in records:
        row["path"] = str(Path(row["path"]).relative_to(run))
    (run / "render_checks.json").write_text(
        json.dumps(
            {
                "cpu_only": True,
                "threads": 6,
                "studio_dependency": str(STUDIO.relative_to(ROOT)),
                "renders": records,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
