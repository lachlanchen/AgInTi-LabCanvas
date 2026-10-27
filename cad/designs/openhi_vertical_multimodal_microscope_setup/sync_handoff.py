#!/usr/bin/env python3
"""Keep one complete assembly-review run in Nutstore without render caches."""

import hashlib
import json
import shutil
from pathlib import Path

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
ART = DESIGN / "artifacts"
RUN_NAME = "run-2-vertical-cascade-full-frame-20261027T140302Z"
NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")


def main():
    manifest = json.loads((ART / "manifest.json").read_text())
    cameras = json.loads((ART / "renders/camera_validation.json").read_text())
    if len(cameras) != 5 or not manifest["checks"]["all_step_round_trips_valid"]:
        raise RuntimeError("Missing final assembly/camera evidence")
    run = DESIGN / "runs" / RUN_NAME
    target = NUTSTORE / DESIGN.name / RUN_NAME
    files = [(DESIGN / "README.md", "README.md"), (ART / "manifest.json", "manifest.json")]
    files += [(path, "renders/" + path.name) for path in sorted((ART / "renders").glob("*.png"))]
    files += [(ART / "renders/camera_validation.json", "renders/camera_validation.json")]
    files += [(path, "figures/" + path.name) for path in sorted((ART / "figures").glob("Figure_*"))]
    for variant in manifest["variants"].values():
        path = ROOT / variant["use_this_step"]
        files.append((path, path.name))
        NUTSTORE.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, NUTSTORE / path.name)
    for source, relative in files:
        for destination in (run / relative, target / relative):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            digest = lambda path: hashlib.sha256(path.read_bytes()).digest()
            if digest(source) != digest(destination):
                raise RuntimeError(f"Sync checksum mismatch: {destination}")
    print(json.dumps({"nutstore": str(target), "verified_files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
