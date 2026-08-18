#!/usr/bin/env python3
"""Audit a print mesh for unintended layer-to-layer XY translation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene", process=True)
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geometry
            for geometry in loaded.geometry.values()
            if isinstance(geometry, trimesh.Trimesh) and len(geometry.faces)
        ]
        if not meshes:
            raise ValueError(f"no mesh geometry found in {path}")
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh) or not len(loaded.faces):
        raise ValueError(f"no mesh geometry found in {path}")
    return loaded


def audit_layer_stack(
    mesh: trimesh.Trimesh,
    *,
    layer_height_mm: float,
    gross_jump_threshold_mm: float,
) -> tuple[dict[str, Any], list[dict[str, float]]]:
    if layer_height_mm <= 0:
        raise ValueError("layer height must be positive")
    if gross_jump_threshold_mm <= 0:
        raise ValueError("gross jump threshold must be positive")

    bounds = np.asarray(mesh.bounds, dtype=float)
    z_min = float(bounds[0, 2])
    z_max = float(bounds[1, 2])
    sample_z = np.arange(
        z_min + layer_height_mm / 2.0,
        z_max,
        layer_height_mm,
    )
    rows: list[dict[str, float]] = []
    for z_mm in sample_z:
        section = mesh.section(
            plane_origin=[0.0, 0.0, float(z_mm)],
            plane_normal=[0.0, 0.0, 1.0],
        )
        if section is None or not len(section.vertices):
            continue
        xy = np.asarray(section.vertices, dtype=float)[:, :2]
        xy_min = xy.min(axis=0)
        xy_max = xy.max(axis=0)
        center = (xy_min + xy_max) / 2.0
        extent = xy_max - xy_min
        rows.append(
            {
                "z_mm": float(z_mm),
                "center_x_mm": float(center[0]),
                "center_y_mm": float(center[1]),
                "extent_x_mm": float(extent[0]),
                "extent_y_mm": float(extent[1]),
            }
        )

    if len(rows) < 2:
        raise ValueError("fewer than two non-empty layer sections were found")

    centers = np.asarray(
        [[row["center_x_mm"], row["center_y_mm"]] for row in rows],
        dtype=float,
    )
    reference_limit = z_min + 0.6 * (z_max - z_min)
    reference_centers = np.asarray(
        [
            center
            for row, center in zip(rows, centers)
            if row["z_mm"] <= reference_limit
        ],
        dtype=float,
    )
    if not len(reference_centers):
        reference_centers = centers
    reference_center = np.median(reference_centers, axis=0)
    offsets = np.linalg.norm(centers - reference_center, axis=1)
    jumps = np.zeros(len(rows), dtype=float)
    jumps[1:] = np.linalg.norm(np.diff(centers, axis=0), axis=1)

    for index, row in enumerate(rows):
        row["offset_from_reference_mm"] = float(offsets[index])
        row["jump_from_previous_mm"] = float(jumps[index])

    gross_jumps = [
        {
            "z_mm": round(row["z_mm"], 6),
            "jump_mm": round(row["jump_from_previous_mm"], 6),
        }
        for row in rows
        if row["jump_from_previous_mm"] > gross_jump_threshold_mm
    ]
    components = mesh.split(only_watertight=False)
    summary: dict[str, Any] = {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "connected_component_count": len(components),
        "vertex_count": int(len(mesh.vertices)),
        "face_count": int(len(mesh.faces)),
        "bounds_mm": [[round(float(value), 6) for value in row] for row in bounds],
        "layer_height_mm": layer_height_mm,
        "sampled_layer_count": len(rows),
        "reference_center_xy_mm": [
            round(float(reference_center[0]), 6),
            round(float(reference_center[1]), 6),
        ],
        "max_center_offset_mm": round(float(offsets.max()), 6),
        "max_consecutive_center_jump_mm": round(float(jumps.max()), 6),
        "gross_jump_threshold_mm": gross_jump_threshold_mm,
        "gross_jump_count": len(gross_jumps),
        "gross_jumps": gross_jumps,
        "passes_gross_layer_translation_guard": not gross_jumps,
    }
    return summary, rows


def write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_plot(path: Path, rows: list[dict[str, float]], *, title: str) -> None:
    import matplotlib.pyplot as plt

    z_mm = [row["z_mm"] for row in rows]
    x_mm = [row["center_x_mm"] for row in rows]
    y_mm = [row["center_y_mm"] for row in rows]
    jump_mm = [row["jump_from_previous_mm"] for row in rows]

    figure, axes = plt.subplots(1, 2, figsize=(10, 4.4), constrained_layout=True)
    axes[0].plot(x_mm, z_mm, label="X center", linewidth=1.5)
    axes[0].plot(y_mm, z_mm, label="Y center", linewidth=1.5)
    axes[0].axvline(0.0, color="#666666", linewidth=0.8)
    axes[0].set_xlabel("Section bounding-box center (mm)")
    axes[0].set_ylabel("Z (mm)")
    axes[0].set_title("Layer center by height")
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(jump_mm, z_mm, color="#b23a48", linewidth=1.5)
    axes[1].set_xlabel("Center jump from prior layer (mm)")
    axes[1].set_ylabel("Z (mm)")
    axes[1].set_title("Consecutive layer-center jump")
    axes[1].grid(alpha=0.25)
    figure.suptitle(f"{title} layer-stack audit")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="print-ready STL path")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--layer-height", type=float, default=0.2)
    parser.add_argument("--gross-jump-threshold", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    mesh = load_mesh(input_path)
    summary, rows = audit_layer_stack(
        mesh,
        layer_height_mm=args.layer_height,
        gross_jump_threshold_mm=args.gross_jump_threshold,
    )
    summary["source"] = str(input_path)
    summary["source_sha256"] = sha256_file(input_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = input_path.stem
    json_path = output_dir / f"{output_stem}_layer_stack_audit.json"
    csv_path = output_dir / f"{output_stem}_layer_stack.csv"
    plot_path = output_dir / f"{output_stem}_layer_stack.png"
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_csv(csv_path, rows)
    write_plot(plot_path, rows, title=output_stem)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passes_gross_layer_translation_guard"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
