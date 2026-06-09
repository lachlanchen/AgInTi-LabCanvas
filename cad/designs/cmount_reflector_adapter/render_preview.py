"""Generate lightweight 3D preview renders for the C-mount adapter.

This is a visualization helper, not the manufacturing source. The source of
truth remains cmount_reflector_adapter.scad.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


THREAD_LENGTH = 5.5
BODY_LENGTH = 18.0
THREAD_MAJOR_D = 24.4
BODY_D = 26.0
BORE_D = 20.0
INNER_CUBE = 20.0
WALL = 3.0
OUTER_CUBE = INNER_CUBE + 2 * WALL
CUBE_X0 = THREAD_LENGTH + BODY_LENGTH
TOTAL_LENGTH = THREAD_LENGTH + BODY_LENGTH + OUTER_CUBE
AXIS_Z = BODY_D / 2


def add_cylinder(ax, x0, length, radius, color, alpha=1.0):
    theta = np.linspace(0, 2 * np.pi, 96)
    x = np.array([x0, x0 + length])
    theta_grid, x_grid = np.meshgrid(theta, x)
    y = radius * np.cos(theta_grid)
    z = AXIS_Z + radius * np.sin(theta_grid)
    ax.plot_surface(x_grid, y, z, color=color, alpha=alpha, linewidth=0, shade=True)


def add_thread_ridges(ax):
    pitch = 25.4 / 32
    radius = THREAD_MAJOR_D / 2
    t = np.linspace(0, THREAD_LENGTH, 900)
    turns = t / pitch
    y = radius * np.cos(2 * np.pi * turns)
    z = AXIS_Z + radius * np.sin(2 * np.pi * turns)
    ax.plot(t, y, z, color="#1d4ed8", linewidth=2.2)


def add_box(ax, x0, x1, y0, y1, z0, z1, color, alpha=1.0):
    pts = np.array(
        [
            [x0, y0, z0],
            [x1, y0, z0],
            [x1, y1, z0],
            [x0, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x1, y1, z1],
            [x0, y1, z1],
        ]
    )
    faces = [
        [pts[i] for i in [0, 1, 2, 3]],
        [pts[i] for i in [4, 5, 6, 7]],
        [pts[i] for i in [0, 1, 5, 4]],
        [pts[i] for i in [2, 3, 7, 6]],
        [pts[i] for i in [1, 2, 6, 5]],
        [pts[i] for i in [0, 3, 7, 4]],
    ]
    poly = Poly3DCollection(faces, facecolors=color, edgecolors="#0f172a", linewidths=0.7, alpha=alpha)
    ax.add_collection3d(poly)


def set_equal_axes(ax):
    ax.set_xlim(-2, TOTAL_LENGTH + 4)
    ax.set_ylim(-20, 20)
    ax.set_zlim(-2, 32)
    ax.set_box_aspect((TOTAL_LENGTH + 6, 40, 34))


def draw(path, view):
    fig = plt.figure(figsize=(12, 7), dpi=160)
    ax = fig.add_subplot(111, projection="3d")
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")

    add_cylinder(ax, 0, THREAD_LENGTH, THREAD_MAJOR_D / 2, "#bfdbfe", 0.95)
    add_thread_ridges(ax)
    add_cylinder(ax, THREAD_LENGTH, BODY_LENGTH, BODY_D / 2, "#bae6fd", 0.95)
    add_box(ax, CUBE_X0, TOTAL_LENGTH, -OUTER_CUBE / 2, OUTER_CUBE / 2, 0, OUTER_CUBE, "#bbf7d0", 0.96)

    # Show optical opening and reflector cavity as translucent void references.
    add_cylinder(ax, -0.5, TOTAL_LENGTH + 1, BORE_D / 2, "#ffffff", 0.18)
    add_box(ax, CUBE_X0 + WALL, TOTAL_LENGTH + 1, -INNER_CUBE / 2, INNER_CUBE / 2, WALL, WALL + INNER_CUBE, "#ffffff", 0.18)

    ax.text(1, -17, 27, "male C-mount-like thread, 24.4 mm printed-fit major", color="#1e3a8a", fontsize=8)
    ax.text(CUBE_X0 + 2, 14, 27, "20 x 20 x 20 mm reflector pocket", color="#166534", fontsize=8)
    ax.text(THREAD_LENGTH + 5, -17, 4, "20 mm bore through optical axis", color="#334155", fontsize=8)
    ax.set_xlabel("X length (mm)")
    ax.set_ylabel("Y width (mm)")
    ax.set_zlabel("Z height (mm)")
    ax.view_init(elev=view[0], azim=view[1])
    set_equal_axes(ax)
    ax.grid(True, color="#cbd5e1", linewidth=0.4)
    plt.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main():
    out = Path(__file__).parent / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    draw(out / "adapter_render_3d.png", (24, -54))
    draw(out / "adapter_render_full_scale.png", (14, -84))


if __name__ == "__main__":
    main()
