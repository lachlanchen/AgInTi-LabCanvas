#!/usr/bin/env python3
"""Build the ID 6.5 / OD 10.5 spacer print jobs."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cad" / "tools"))

from cylindrical_print_ready import build_ring_design


def main() -> None:
    manifest = build_ring_design(
        root=ROOT,
        design_dir=DESIGN_DIR,
        run_name="run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z",
        stem="cage_spacer_id6p5_od10p5",
        inner_diameter_mm=6.5,
        outer_diameter_mm=10.5,
        short_height_mm=5.0,
        tall_height_mm=50.0,
        rows=4,
        cols=4,
        pitch_mm=15.0,
        color=(0.10, 0.62, 0.58),
        source_path=Path(__file__),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
