#!/usr/bin/env python3
"""Render run 5 dock and an assembly with 10 mm adapter proxies."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path


DESIGN_DIR = Path(__file__).resolve().parent
RUN4_RENDER = (
    DESIGN_DIR.parents[1]
    / "runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z"
    / "render_run4_m6_strong_ears_10mm_side_contact.py"
)


def load_renderer():
    spec = importlib.util.spec_from_file_location("cage_dock_run4_render", RUN4_RENDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load run-4 renderer: {RUN4_RENDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = load_renderer()
renderer.DESIGN_DIR = DESIGN_DIR
renderer.ARTIFACT_DIR = DESIGN_DIR / "artifacts"
renderer.STEM = "cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector"
renderer.DOCK_STL = renderer.ARTIFACT_DIR / f"{renderer.STEM}.stl"
renderer.RENDER = renderer.ARTIFACT_DIR / f"{renderer.STEM}_render.png"
renderer.ASSEMBLY_RENDER = renderer.ARTIFACT_DIR / f"{renderer.STEM}_assembly_render.png"
renderer.BASE_THICKNESS = 25.0
renderer.ROD_DEPTH = 20.0
renderer.ROD_VISIBLE_HEIGHT = 72.0
renderer.ROD_DIAMETER = 10.0
BOTTOM_RENDER = renderer.ARTIFACT_DIR / f"{renderer.STEM}_bottom_ejector_render.png"


def render_bottom() -> None:
    materials = renderer.setup_common()
    dock = renderer.import_stl(
        renderer.DOCK_STL,
        "dock underside with four M6.2 ejector openings",
        materials["dock"],
    )
    dock.rotation_euler[0] = math.pi
    dock.location.z = renderer.BASE_THICKNESS
    renderer.render(BOTTOM_RENDER, (180, -210, 148), (0, 0, 10), ortho_scale=250)


if __name__ == "__main__":
    renderer.main()
    render_bottom()
