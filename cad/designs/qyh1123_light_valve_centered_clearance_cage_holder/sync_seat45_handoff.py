#!/usr/bin/env python3
"""Sync the exact and 45-degree QYH1123 packages with checksum verification."""

import hashlib
import json
import shutil
from pathlib import Path

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
DEST = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / DESIGN.name


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_checked(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha(source) != sha(target):
        raise RuntimeError(f"Copy mismatch: {target}")


def main():
    summary = json.loads((DESIGN / "artifacts/seat45_manifest.json").read_text())
    delivered = {}
    for key, row in summary["variants"].items():
        run = ROOT / row["run_dir"]
        data = json.loads((run / "manifest.json").read_text())
        cameras = json.loads((run / "renders/camera_validation.json").read_text())
        if {x["file"] for x in cameras} != {"holder_top.png", "assembly.png", "direct_print.png"}:
            raise RuntimeError("Missing final CAD renders")
        for record in cameras:
            b = record["projected_bounds"]
            if not (0.079 <= b["xmin"] < b["xmax"] <= 0.921 and 0.079 <= b["ymin"] < b["ymax"] <= 0.921):
                raise RuntimeError("Render violates camera margin")
        for source in data["source_identity"].values():
            if sha(ROOT / source["path"]) != source["sha256"]:
                raise RuntimeError("An accepted source changed")
        for name in ("build_seat45_handoff.py", "render_seat45_handoff.py", "sync_seat45_handoff.py"):
            copy_checked(DESIGN / name, run / "source" / name)
        for name in ("simple_3mf.py", "blender_camera_fit.py"):
            copy_checked(ROOT / "cad/tools" / name, run / "source" / name)
        note = ("The unchanged 0-degree package is an exact copy of the accepted tolerance-adjusted holder.\n"
                if key == "0deg" else
                "Only the LCD pocket, light window, pin relief and LCD/pin reference rotate 45 degrees counterclockwise viewed from +Z.\n")
        (run / "README.md").write_text(
            f"# QYH1123 Holder: {key}\n\n{note}\n"
            "Outer body: 42 x 42 x 8 mm. Cage centers: (+/-15, +/-15) mm; bores: 6.4 mm.\n"
            "Accepted LCD sink: 18.6 x 20.6 mm, nominal depth 2.2 mm; all existing clearance offsets are preserved.\n"
            "Through-window: 13 x 13 mm. Pin relief: 6.6 mm wide, nominal depth 2.7 mm.\n\n"
            f"Use `{data['print_validation']['stem']}.3mf` to print; the STEP and STL beside it are equivalent alternatives.\n"
            "The print model contains only the holder, with its flat back on Z=0. No ears or other features were added.\n"
            f"`{data['assembly_step']}` includes the separate LCD/pins and cage-rod references for alignment review.\n\n"
            + "\n".join("- " + item for item in data["limitations"]) + "\n")
        target = DEST / run.name
        files = [path for path in run.rglob("*") if path.is_file() and path.name != "sync_manifest.json"]
        record = {}
        for source in files:
            relative = source.relative_to(run)
            copy_checked(source, target / relative)
            record[str(relative)] = {"bytes": source.stat().st_size, "sha256": sha(source)}
        (run / "sync_manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        copy_checked(run / "sync_manifest.json", target / "sync_manifest.json")
        copy_checked(run / data["assembly_step"], DEST.parent / f"USE_THIS_qyh1123_holder_{key}_assembly.step")
        delivered[key] = {"folder": str(target), "verified_files": len(files) + 1,
                          "assembly": str(target / data["assembly_step"])}
    print(json.dumps(delivered, indent=2))


if __name__ == "__main__":
    main()
