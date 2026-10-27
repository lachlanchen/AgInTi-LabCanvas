#!/usr/bin/env python3
"""Run 2: square-Y motor support, removable bridge, and M3 metal-nut locks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section

import build_mount as base

RUN_NAME = "run-2-square-y-motor-yoke-m3-bridge-20261027T145017Z"
P = {
    "band_xmin_mm": 91.0, "band_xmax_mm": 103.0,
    "motor_case_ymin_mm": 29.0, "motor_case_ymax_mm": 69.0,
    "motor_case_bottom_z_mm": 124.5, "motor_case_top_z_mm": 164.5,
    "fork_inner_ymin_mm": 28.5, "fork_inner_ymax_mm": 69.5,
    "fork_inner_bottom_z_mm": 124.0, "bridge_inner_top_z_mm": 165.0,
    "fork_outer_ymin_mm": 18.5, "fork_outer_ymax_mm": 79.5,
    "fork_bottom_z_mm": 118.0, "fork_top_z_mm": 167.0,
    "bridge_top_z_mm": 175.0,
    "m3_clearance_diameter_mm": 3.4,
    "m3_nut_pocket_af_mm": 5.7, "m3_nut_pocket_height_mm": 2.6,
    "dock_foot_bottom_z_mm": 8.0,
    "table_foot_bottom_z_mm": 0.0,
    "m6_clearance_diameter_mm": 6.4,
}
BOLTS = [(97.0, 23.5), (97.0, 74.5)]
DOCK_HOLES = [(100.0, 0.0), (125.0, 0.0)]
TABLE_HOLES = [(150.0, 0.0), (175.0, 0.0), (150.0, 75.0), (175.0, 75.0)]


def square_y_fork():
    fork = base.box(91, 103, 18.5, 79.5, 118, 167)
    fork = fork.cut(base.box(90, 104, 28.5, 69.5, 124, 168))
    shoulder = cq.Workplane("YZ", origin=(91, 0, 0)).polyline(
        [(40, 96), (18.5, 118.1), (79.5, 118.1), (58, 96)]
    ).close().extrude(12)
    fork = fork.union(shoulder)
    for x, y in BOLTS:
        fork = fork.cut(base.cylinder(3.4, 153, 16, x, y))
        fork = fork.cut(base.hex_prism(5.7, 156, 2.6, x, y))
        # Slide a real M3 nut in from the front, then the cap screws lock it.
        fork = fork.cut(base.box(90, 97, y - 2.85, y + 2.85, 156, 158.6))
    return fork.clean()


def yoke(direct_table=False):
    if direct_table:
        foot = base.box(140, 190, -10, 90, 0, 8)
        # Offset the table foot beyond the original 138 mm stand-foot edge.
        stem = cq.Workplane("XZ", origin=(0, 58, 0)).polyline(
            [(154, 7.9), (176, 7.9), (103, 118.1), (91, 118.1)]
        ).close().extrude(18)
        holes = TABLE_HOLES
    else:
        foot = base.box(90, 140, -10, 90, 8, 16)
        stem = base.box(91, 103, 40, 58, 15.9, 98)
        holes = DOCK_HOLES
    shape = foot.union(stem).union(square_y_fork())
    for x, y in holes:
        shape = shape.cut(base.cylinder(6.4, -1, 18, x, y))
    return shape.clean()


def bridge():
    cap = base.box(91, 103, 18.5, 79.5, 167, 175)
    cap = cap.union(base.box(91, 103, 30, 68, 165, 167.1))
    for x, y in BOLTS:
        cap = cap.cut(base.cylinder(3.4, 164, 13, x, y))
        cap = cap.cut(base.cylinder(6.4, 171.8, 5.2, x, y))
    return cap.clean()


def fastener_proxies():
    parts = []
    for i, (x, y) in enumerate(BOLTS, 1):
        screw = base.cylinder(3, 155.8, 16, x, y).union(base.cylinder(5.5, 171.8, 3, x, y))
        screw = screw.cut(base.hex_prism(2.5, 173, 2.8, x, y))
        nut = base.hex_prism(5.5, 156.1, 2.4, x, y).cut(base.cylinder(2.5, 155, 5, x, y))
        parts.extend([(f"bridge_M3_screw_{i}", screw, (0.60, 0.63, 0.67)),
                      (f"bridge_M3_nut_{i}", nut, (0.60, 0.63, 0.67))])
    return parts


def motor_sections(motor):
    records = []
    for x in (91.0, 97.0, 103.0, 105.0):
        plane = cq.Face.makePlane(400, 400, (x, 0, 145), (1, 0, 0))
        section = cq.Shape.cast(BRepAlgoAPI_Section(motor.val().wrapped, plane.wrapped).Shape())
        vertices = section.Vertices()
        values = {"x_mm": x, "ymin_mm": min(v.Y for v in vertices), "ymax_mm": max(v.Y for v in vertices),
                  "zmin_mm": min(v.Z for v in vertices), "zmax_mm": max(v.Z for v in vertices)}
        if not (values["ymin_mm"] >= 29 - 1e-3 and values["ymax_mm"] <= 69 + 1e-3
                and values["zmin_mm"] >= 124.5 - 1e-3 and values["zmax_mm"] <= 164.5 + 1e-3):
            raise RuntimeError(f"Motor band is not clear of protrusions: {values}")
        records.append(values)
    return records


def main():
    dock = yoke()
    table = yoke(direct_table=True)
    cap = bridge()
    source = cq.importers.importStep(str(base.REF / "YXRA100_100W_servo.step"))
    motor = base.stage_transform(cq.Workplane(obj=list(source.val())[2]))
    sections = motor_sections(motor)
    # Closed conservative casing envelope in the selected connector-free band.
    case = base.box(91, 103, 29, 69, 124.5, 164.5)
    stand = base.support()
    foot = base.foot()
    rotating = base.stage_transform(cq.Workplane(obj=source.solids().vals()[3]))
    checks = {
        "dock_yoke_vs_motor_case": base.intersection_volume(dock, case),
        "bridge_vs_motor_case": base.intersection_volume(cap, case),
        "bridge_vs_yoke": base.intersection_volume(cap, dock),
        "dock_yoke_vs_stand": base.intersection_volume(dock, stand),
        "dock_yoke_vs_foot": base.intersection_volume(dock, foot),
        "table_yoke_vs_stand": base.intersection_volume(table, stand),
        "table_yoke_vs_foot": base.intersection_volume(table, foot),
        "dock_yoke_vs_rotor": base.intersection_volume(dock, rotating),
        "table_yoke_vs_rotor": base.intersection_volume(table, rotating),
    }
    aperture_probe = base.cylinder(29.8, 122.05, 44.9)
    checks["stage_aperture_core_obstruction"] = base.intersection_volume(base.stage_transform(source), aperture_probe)
    checks["new_support_aperture_obstruction"] = base.intersection_volume(dock.union(cap), aperture_probe)
    for x, y in DOCK_HOLES:
        checks[f"shared_M6_hole_{x:g}_{y:g}"] = base.intersection_volume(dock.union(foot), base.cylinder(6.3, -0.1, 16.2, x, y))
    for x, y in BOLTS:
        checks[f"M3_screw_path_{y:g}"] = base.intersection_volume(dock.union(cap), base.cylinder(3.0, 154, 18, x, y))
    if any(abs(v) > 0.01 for v in checks.values()):
        raise RuntimeError(f"Unwanted interference: {checks}")

    base.RUN = base.DESIGN / "runs" / RUN_NAME
    base.ART.mkdir(parents=True, exist_ok=True)
    base.export_part("motor_yoke_direct_table", table)
    base.export_part("motor_yoke_stand_foot", dock)
    base.export_part("motor_yoke_top_bridge", cap)
    baseline = json.loads((base.DESIGN / "runs/run-1-servo-full-gt090101-clearance-prototype-20261027T140000Z/manifest.json").read_text())
    extras = [("motor_yoke_stand_foot", dock, (0.20, 0.43, 0.51)),
              ("motor_yoke_top_bridge", cap, (0.85, 0.56, 0.16)), *fastener_proxies()]
    metadata = {
        "motor_yoke": {
            "parameters_mm": P, "source_section_measurements": sections,
            "M3_screw_centers_mm": BOLTS, "stand_foot_M6_centers_mm": DOCK_HOLES,
            "table_foot_M6_centers_mm": TABLE_HOLES,
            "interference_volume_mm3": checks,
            "locking_method": "2x M3 x 16 socket screws into captive real metal M3 nuts; screw/nut thread geometry is visualization-only, not a printed thread",
            "case_clearance_mm": {"each_side": 0.5, "below": 0.5, "above": 0.5},
            "connector_note": "Band X=91..103 is before the connector protrusions; bore, rotor, coupler and connector faces remain unrestrained.",
            "installation": "Choose one lower yoke only: stand-foot version shares two M6 mounting holes; direct-table version sits outboard of the existing foot. The top bridge fits either.",
            "contact_note": "Use optional thin compliant pads to take up the running clearance; close the bridge gently, do not crush the casing or preload the stage bearings.",
            "role": "Secondary motor-end support/retention. Original three stationary-base mounting screws remain the primary support.",
        },
        "preserved_run_1_geometry": {name: baseline["geometry_validation"][name] for name in ("breadboard_foot", "gusseted_L_support", "rotating_analyzer_adapter")},
    }
    _, components = base.main(extra_components=extras,
              extra_prints={"motor_yoke_stand_foot": ("yxra100_motor_yoke_stand_foot", base.ears(dock.translate((0, 0, -8)), base_bounds=(90, 140, -10, 90))),
                            "motor_yoke_direct_table": ("yxra100_motor_yoke_direct_table", base.ears(table, base_bounds=(140, 190, -10, 90))),
                            "motor_yoke_top_bridge": ("yxra100_motor_yoke_M3_top_bridge", cap.rotate((0, 0, 0), (1, 0, 0), 180))},
              extra_manifest=metadata)
    data = json.loads((base.ART / "manifest.json").read_text())
    for name, previous in metadata["preserved_run_1_geometry"].items():
        if previous != data["geometry_validation"][name]:
            raise RuntimeError(f"Accepted geometry changed: {name}")
    alternative = cq.Assembly(name="YXRA100_direct_table_motor_yoke_alternative")
    for name, shape, color in components:
        alternative.add(table if name == "motor_yoke_stand_foot" else shape,
                        name="motor_yoke_direct_table" if name == "motor_yoke_stand_foot" else name,
                        color=cq.Color(*color))
    alternate_path = base.ART / "yxra100_direct_table_motor_yoke_assembly.step"
    alternative.save(str(alternate_path))
    imported = cq.importers.importStep(str(alternate_path))
    valid = bool(imported.solids().vals()) and all(s.isValid() for s in imported.solids().vals())
    if not valid:
        raise RuntimeError("Direct-table alternative STEP is invalid")
    data["motor_yoke"]["direct_table_assembly_step"] = alternate_path.name
    data["motor_yoke"]["direct_table_assembly_round_trip_valid"] = valid
    (base.ART / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    shutil.copy2(base.ART / "manifest.json", base.RUN / "manifest.json")
    shutil.copy2(alternate_path, base.RUN / alternate_path.name)
    print(json.dumps({"run": RUN_NAME, "motor_yoke_checks": checks}, indent=2))


if __name__ == "__main__":
    main()
