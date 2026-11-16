#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional parallel NEMA17 mount; never replaces the physically accepted run."""

import copy
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import cadquery as cq

import build_stage as base

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
BASELINE = DESIGN / "runs/run-7-upright-chamfered-rotor-prototype-20261106T110659Z"
FIT = {
    "plate_half_x_mm": 30.0,
    "plate_half_y_mm": 28.0,
    "plate_bottom_z_mm": 80.0,
    "plate_top_z_mm": 84.0,
    "plate_pocket_clearance_each_side_mm": 0.2,
    "tension_travel_each_way_mm": 3.0,
    "clamp_x_offset_mm": 24.0,
    "clamp_y_offset_mm": 24.0,
    "clamp_screw_length_mm": 10.0,
    "clamp_washer_thickness_mm": 0.5,
}


def clamp_points(center):
    dx, dy = FIT["clamp_x_offset_mm"], FIT["clamp_y_offset_mm"]
    return [(center + x, y) for x in (-dx, dx) for y in (-dy, dy)]


def mounting_parts(center):
    px, py = FIT["plate_half_x_mm"], FIT["plate_half_y_mm"]
    gap = FIT["plate_pocket_clearance_each_side_mm"]
    travel = FIT["tension_travel_each_way_mm"]
    bottom, top = FIT["plate_bottom_z_mm"], FIT["plate_top_z_mm"]
    carrier = base.carrier(center).cut(
        base.box(
            center - px - travel - gap,
            center + px + travel + gap,
            -py - gap,
            py + gap,
            bottom,
            top + 1,
        )
    )
    plate = base.box(center - px, center + px, -py, py, bottom, top)
    boss = (
        base.P["motor_boss_diameter_mm"] + base.P["motor_boss_clearance_diametral_mm"]
    )
    plate = plate.cut(base.cyl(boss, bottom - 0.1, top - bottom + 0.3, center))
    for x, y in base.motor_mount_points(center):
        plate = plate.cut(base.cyl(3.4, 79.9, 4.3, x, y))
        plate = plate.cut(base.cyl(7.4, 82, 2.2, x, y))
    for x, y in clamp_points(center):
        carrier = carrier.cut(base.cyl(3.4, 74.9, 5.3, x, y))
        carrier = carrier.cut(base.hex_prism(5.8, x, y, 74.9, 2.7))
        plate = plate.cut(
            base.slot(3.4, 2 * travel, x, y, bottom - 0.1, top - bottom + 0.3)
        )
    return carrier, plate


def require_clear(checks, name, a, b):
    value = base.volume(a.intersect(b))
    checks[name] = value
    if value > 1e-5:
        raise RuntimeError(f"Interference {name}: {value} mm3")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path, help="Resume this optional builder's unfinished run"
    )
    args = parser.parse_args()
    if args.run_dir and (args.run_dir / "manifest.json").exists():
        raise ValueError("Completed runs are preserved; create a new run instead")
    baseline = json.loads((BASELINE / "manifest.json").read_text())
    base.P["motor_mount_rotation_deg"] = 0.0
    center, _, big, small = base.center_distance()
    carrier, plate = mounting_parts(center)
    motor, _ = base.motor_reference()
    motor = motor.translate((center, 0, 80))
    belt = base.belt(center, big, small)
    retainer = cq.importers.importStep(str(BASELINE / "inner_race_retainer.step"))
    stand = cq.importers.importStep(str(BASELINE / "footed_stand.step"))
    checks = {}
    for shift in (-3, 0, 3):
        moved_plate = plate.translate((shift, 0, 0))
        moved_motor = motor.translate((shift, 0, 0))
        require_clear(checks, f"plate/carrier/{shift}", moved_plate, carrier)
        require_clear(checks, f"motor/carrier/{shift}", moved_motor, carrier)
        require_clear(checks, f"motor/stand/{shift}", moved_motor, stand)
        require_clear(checks, f"motor/plate/{shift}", moved_motor, moved_plate)
        for name in (
            "rotor_cup",
            "rotor_cap",
            "polarizer_insert",
            "polarizer_retainer",
        ):
            part = cq.importers.importStep(str(BASELINE / (name + ".step")))
            for angle in (0, 45, 90, 180):
                rotated = part.rotate((0, 0, 0), (0, 0, 1), angle)
                require_clear(
                    checks, f"{name}/plate/{shift}/{angle}", rotated, moved_plate
                )
                require_clear(
                    checks, f"{name}/motor/{shift}/{angle}", rotated, moved_motor
                )
    # Motor-to-plate screws are tightened on the bench before fitting the belt.
    # The four independent tension clamps must remain accessible with the belt on.
    hardware = base.hardware_references(center)
    for number, (x, y) in enumerate(clamp_points(center)):
        tool = base.cyl(4, 87.5, 35, x, y)
        require_clear(checks, f"clamp_tool/belt/{number}", tool, belt)
        washer = base.ring(7, 3.2, 84, 0.5).translate((x, y, 0))
        screw = base.cyl(3, 74.5, 10, x, y).union(base.cyl(5.5, 84.5, 3, x, y))
        require_clear(checks, f"clamp_head/belt/{number}", screw, belt)
        require_clear(checks, f"clamp_washer/belt/{number}", washer, belt)
        hardware[f"plate_clamp_{number}"] = (screw, "metal")
        hardware[f"plate_clamp_washer_{number}"] = (washer, "metal")
    bore = base.cyl(30, -1, 110)
    for name, shape in (("carrier", carrier), ("motor_plate", plate)):
        require_clear(checks, f"optical_bore/{name}", shape, bore)
        if not base.valid(shape) or len(shape.solids().vals()) != 1:
            raise RuntimeError(f"Invalid printable solid: {name}")
    number = max(int(p.name.split("-")[1]) for p in (DESIGN / "runs").glob("run-*")) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = (
        args.run_dir.resolve()
        if args.run_dir
        else DESIGN
        / "runs"
        / f"run-{number}-parallel-nema17-removable-motor-plate-{stamp}"
    )
    if (
        run.parent != DESIGN / "runs"
        or "parallel-nema17-removable-motor-plate" not in run.name
    ):
        raise ValueError(
            "Optional output must stay in this project's parallel-motor runs"
        )
    run.mkdir(exist_ok=True)
    for folder in ("print", "render_meshes"):
        shutil.copytree(BASELINE / folder, run / folder, dirs_exist_ok=True)
    data = copy.deepcopy(baseline)
    shapes = {}
    for name in baseline["parts"]:
        path = BASELINE / (name + ".step")
        shutil.copy2(path, run / path.name)
        shapes[name] = cq.importers.importStep(str(path))
    changes = {"carrier": carrier, "motor_plate": plate, "motor_OpenHI_exact": motor}
    changes.update({name: row[0] for name, row in hardware.items()})
    for name, shape in changes.items():
        shapes[name] = shape
        cq.exporters.export(shape, str(run / (name + ".step")))
        mesh = run / "render_meshes" / (name + ".stl")
        cq.exporters.export(shape, str(mesh), tolerance=0.04, angularTolerance=0.12)
        data["parts"][name] = {
            "category": "polymer_mid"
            if name in ("carrier", "motor_plate")
            else "metal",
            "mesh": str(mesh.relative_to(run)),
        }
    for name, shape in (("carrier", carrier), ("motor_plate", plate)):
        data["print_validation"][name] = base.print_export(
            shape, run, name, ears=name == "carrier"
        )
    assembly = cq.Assembly(name="Optional_parallel_NEMA17_rotary_stage")
    for name, shape in shapes.items():
        assembly.add(shape, name=name)
    step = run / "optional_parallel_nema17_rotary_stage_assembly.step"
    assembly.save(str(step))
    if not base.valid(cq.importers.importStep(str(step))):
        raise RuntimeError("Assembly STEP round trip failed")
    for name in (
        "rotor_cup",
        "rotor_cap",
        "inner_race_retainer",
        "footed_stand",
        "polarizer_insert",
        "polarizer_retainer",
    ):
        if base.sha(run / (name + ".step")) != base.sha(BASELINE / (name + ".step")):
            raise RuntimeError(f"Unrelated part changed: {name}")
    for path in (BASELINE / "print/height_shim_5mm").iterdir():
        if base.sha(path) != base.sha(run / path.relative_to(BASELINE)):
            raise RuntimeError("Optional height shim changed")
    data.update(
        {
            "run_name": run.name,
            "base_run": BASELINE.name,
            "parameters": dict(base.P),
            "optional_mount_parameters": FIT,
            "checks": {"clearances_mm3": checks, "assembly_step_valid": True},
            "assembly_step": step.name,
            "field_status": "untested_optional_variant; installed run7 unchanged",
            "manufacturing": None,
            "printability": None,
            "prototype_limitations": [
                "Optional prototype: not the owner-validated run7 and not physically tested.",
                "Motor plate is clamped on four new M3x10 screws with 0.5mm flat washers and plain M3 nuts.",
                "Attach all four M3x6 motor screws with 1mm washer stacks before installing the plate and belt. The outboard clamps then set tension.",
                "The bearing, rotor, belt, optical height, stand and insert are unchanged. The outside envelope is not a NEMA23 mount and is not substantially miniaturized.",
                "Motor plate pocket allowance is 0.2mm per side. Measure the actual print; no guarantee of a powder-print fit class.",
            ],
        }
    )
    (run / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    source = run / "source"
    source.mkdir(exist_ok=True)
    for name in (
        "build_stage.py",
        "build_parallel_variant.py",
        "render_stage.py",
        "fastener_contract.json",
    ):
        shutil.copy2(DESIGN / name, source / name)
    note = """# Optional parallel NEMA17 motor plate

This new run does not replace the working run 7. Reprint only `carrier` and
`motor_plate`; the original stand, bearing, rotor, belt and polarizer parts are
unchanged. Files under `print/` are individual grounded STEP/STL/3MF parts.

Bench-attach the motor to the removable plate with four M3 x 6 screws and 1 mm
washer stacks. Load four ordinary M3 nuts into the new carrier's underside.
Set the plate on its flat seat, fit the belt, adjust the entire motor/plate
module along X, then lock the four accessible outboard M3 x 10 clamps with
0.5 mm flat washers. Do not try to tension by loosening the inner motor screws.
Begin with low belt tension. This variant has passed geometric checks only.

The carrier and plate are adjacent independent STEP bodies. Pocket fit is
0.2 mm per side; screw slots provide +/-3 mm travel. The tray and motor axial
datums remain unchanged. External size remains largely set by the 120T pulley.
No manufacturing submission or payment is performed by this script.
"""
    (run / "README.md").write_text(note)
    (DESIGN / "artifacts/parallel_variant.json").write_text(
        json.dumps(
            {
                "run_dir": str(run.relative_to(ROOT)),
                "physically_tested": False,
                "promoted_to_default": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {"run_dir": str(run), "checks": len(checks), "default_unchanged": True},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
