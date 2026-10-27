#!/usr/bin/env python3
"""Verify, sync and acknowledge the manuscript apparatus handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
OVERVIEW = "rotary_horizontal_dual_4f_overview.png"
DETAIL = "shared_lower_stack_explanatory_detail.png"
DETECTORS = "horizontal_cascade_detector_detail.png"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_checked(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if digest(source) != digest(target):
        raise RuntimeError(f"Handoff copy mismatch: {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="Published CAD source commit")
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "--verify", args.commit + "^{commit}"], cwd=ROOT, text=True).strip()
    data = json.loads((DESIGN / "artifacts/manifest.json").read_text())
    if data.get("configuration") != "horizontal_dual_4f_rotary_analyzer" or not data["assembly_step_round_trip_valid"]:
        raise RuntimeError("Missing checked horizontal rotary assembly")
    run = DESIGN / "runs" / data["run_name"]
    target = NUTSTORE / DESIGN.name / run.name
    cameras = json.loads((run / "renders/camera_validation.json").read_text())
    if {row["file"] for row in cameras} != {OVERVIEW, DETAIL, DETECTORS}:
        raise RuntimeError("Missing final full-frame or detail render")
    for row in cameras:
        b = row["projected_bounds"]
        if not (0.079 <= b["xmin"] < b["xmax"] <= 0.921 and 0.079 <= b["ymin"] < b["ymax"] <= 0.921):
            raise RuntimeError(f"Unsafe image bounds: {row}")
    full = next(row for row in cameras if row["file"] == OVERVIEW)
    if full["object_count"] != len(data["render_components"]):
        raise RuntimeError("Overview omitted an assembly component")
    files = [(run / data["assembly_step"], data["assembly_step"]),
             (run / "manifest.json", "manifest.json"), (DESIGN / "README.md", "README.md"),
             (run / "rotary_horizontal_dual_4f_scene.blend", "rotary_horizontal_dual_4f_scene.blend")]
    files.extend((run / "renders" / name, "renders/" + name)
                 for name in (OVERVIEW, DETAIL, DETECTORS, "camera_validation.json"))
    for name in ("build_horizontal_cascade.py", "render_horizontal_cascade.py", "sync_horizontal_cascade.py", "render_mount.py"):
        files.append((DESIGN / name, "sources/" + name))
    files.append((ROOT / "cad/tools/blender_camera_fit.py", "sources/blender_camera_fit.py"))
    files.append((ROOT / "tests/test_yxra100_horizontal_cascade.py", "sources/test_yxra100_horizontal_cascade.py"))
    for key, record in data["frozen_sources"].items():
        source = ROOT / record["path"]
        if digest(source) != record["sha256"]:
            raise RuntimeError(f"Archived input changed: {source}")
        files.append((source, f"source_assemblies/{key}{source.suffix}"))
    base_run = ROOT / data["frozen_sources"]["rotary_manifest"]["path"]
    for suffix in ("step", "stl", "3mf"):
        for path in sorted(base_run.parent.glob("PRINT_THIS_*." + suffix)):
            files.append((path, "unchanged_fixture_prints/" + path.name))
    records = {}
    for source, relative in files:
        copy_checked(source, target / relative)
        if source.resolve() != (run / relative).resolve():
            copy_checked(source, run / relative)
        records[relative] = {"sha256": digest(source), "bytes": source.stat().st_size}
    evidence = {"commit": commit, "files": records, "verified_file_count": len(records)}
    (run / "synced_assets.json").write_text(json.dumps(evidence, indent=2) + "\n")
    copy_checked(run / "synced_assets.json", target / "synced_assets.json")
    copy_checked(run / data["assembly_step"], NUTSTORE / "USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step")
    local_renders = DESIGN / "artifacts/renders"
    for name in (OVERVIEW, DETAIL, DETECTORS, "camera_validation.json"):
        copy_checked(run / "renders" / name, local_renders / name)
    reply = {
        "status": "complete", "run_dir": str(target),
        "overview_png": str(target / "renders" / OVERVIEW),
        "detail_png": str(target / "renders" / DETAIL),
        "assembly_step": str(target / data["assembly_step"]),
        "panel_pdf": None, "commit": commit, "limitations": data["limitations"],
        "detector_detail_png": str(target / "renders" / DETECTORS),
        "asset_sha256": {key: digest(Path(value)) for key, value in {
            "overview_png": target / "renders" / OVERVIEW,
            "detail_png": target / "renders" / DETAIL,
            "assembly_step": target / data["assembly_step"],
        }.items()},
    }
    handoff = NUTSTORE / DESIGN.name / "handoffs/vspice_v8_1_reply_20261028.json"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(json.dumps(reply, indent=2) + "\n")
    (run / "vspice_v8_1_reply_20261028.json").write_text(json.dumps(reply, indent=2) + "\n")
    print(json.dumps({"reply": str(handoff), "run_dir": str(target), "verified_files": len(records)}, indent=2))


if __name__ == "__main__":
    main()
