#!/usr/bin/env python3
"""Sync checked fixture geometry and review evidence without transient meshes."""

import hashlib
import json
import shutil
from pathlib import Path

DESIGN = Path(__file__).resolve().parent
ART = DESIGN / "artifacts"
NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
RUN_NAME = "run-1-servo-full-gt090101-clearance-prototype-20261027T140000Z"


def copy_verified(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(source) != digest(destination):
        raise RuntimeError(f"Sync mismatch: {source.name}")


def main():
    data = json.loads((ART / "manifest.json").read_text())
    camera_records = json.loads((ART / "renders/camera_validation.json").read_text())
    if not data["assembly_step_round_trip_valid"] or len(camera_records) != 8:
        raise RuntimeError("Missing assembly validation or final renders")
    run = DESIGN / "runs" / RUN_NAME
    target = NUTSTORE / DESIGN.name / RUN_NAME
    files = [(DESIGN / "README.md", "README.md"), (ART / "manifest.json", "manifest.json")]
    for suffix in ("step", "stl", "3mf"):
        files += [(path, path.name) for path in sorted(run.glob("PRINT_THIS_*." + suffix))]
    files += [(path, "renders/" + path.name) for path in sorted((ART / "renders").glob("*.png"))]
    files += [(ART / "renders/camera_validation.json", "renders/camera_validation.json")]
    files += [(ART / "yxra100_servo_analyzer_breadboard_mount_assembly.step", "USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step")]
    for name in ("breadboard_foot", "gusseted_L_support", "rotating_analyzer_adapter", "vendor_YXRA100_servo_positioned"):
        files.append((ART / f"{name}.step", "editable_parts/" + name + ".step"))
    ref = DESIGN.parents[1] / "references/yixuan-yxra100"
    for name in ("YXRA100_100W_servo.step", "YXRA100_40_servo_specification.pdf", "downloads.json", "README.md"):
        files.append((ref / name, "references/" + name))
    for source, relative in files:
        copy_verified(source, target / relative)
        if not source.is_relative_to(run):
            copy_verified(source, run / relative)
    final = DESIGN / "USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step"
    copy_verified(final, NUTSTORE / final.name)
    print(json.dumps({"target": str(target), "verified_files": len(files) + 1}, indent=2))


if __name__ == "__main__":
    main()
