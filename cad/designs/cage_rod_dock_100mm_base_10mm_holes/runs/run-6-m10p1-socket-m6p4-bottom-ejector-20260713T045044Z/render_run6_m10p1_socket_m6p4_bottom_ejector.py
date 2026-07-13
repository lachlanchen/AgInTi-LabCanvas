#!/usr/bin/env python3
"""Render run 6 from the tested run-5 rendering setup."""

from __future__ import annotations

import importlib.util
from pathlib import Path


DESIGN_DIR = Path(__file__).resolve().parent
RUN5_RENDER = (
    DESIGN_DIR.parents[1]
    / "runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z"
    / "render_run5_m10p1_socket_m6p2_bottom_ejector.py"
)


spec = importlib.util.spec_from_file_location("cage_dock_run5_render", RUN5_RENDER)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load run-5 renderer: {RUN5_RENDER}")
run5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run5)

stem = "cage_rod_dock_100mm_base_m10p1_socket_m6p4_bottom_ejector"
run5.renderer.DESIGN_DIR = DESIGN_DIR
run5.renderer.ARTIFACT_DIR = DESIGN_DIR / "artifacts"
run5.renderer.STEM = stem
run5.renderer.DOCK_STL = run5.renderer.ARTIFACT_DIR / f"{stem}.stl"
run5.renderer.RENDER = run5.renderer.ARTIFACT_DIR / f"{stem}_render.png"
run5.renderer.ASSEMBLY_RENDER = run5.renderer.ARTIFACT_DIR / f"{stem}_assembly_render.png"
run5.BOTTOM_RENDER = run5.renderer.ARTIFACT_DIR / f"{stem}_bottom_ejector_render.png"


if __name__ == "__main__":
    run5.renderer.main()
    run5.render_bottom()
