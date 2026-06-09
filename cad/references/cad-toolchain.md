# CAD Toolchain Reference

Date: 2026-06-09

## Installed System Tools

Installed on Ubuntu 24.04:

| Tool | Install path | Verified command |
| --- | --- | --- |
| OpenSCAD `2021.01` | apt package `openscad` | `openscad --version` |
| Blender `4.0.2` | apt package `blender` | `blender --version` |
| FreeCAD `1.1-g34a97166` | snap package `freecad` | `sudo snap run freecad.cmd --version` |
| Xvfb | apt package `xvfb` | available for headless GUI tools |

FreeCAD note: the snap package is installed and verifies through `sudo snap run freecad.cmd --version`. Direct user-session launch currently reports a snap cgroup error in this shell; a fresh desktop/login session may be required for normal `freecad` and `freecad.cmd` aliases.

## CAD Python Kernel

Local environment:

```bash
mamba activate /home/lachlan/ProjectsLFS/AgenticApp/cad/.conda/cad-python
```

Recreate from the repository spec:

```bash
mamba env create -p cad/.conda/cad-python -f cad/environment-cad-python.yml
cad/.conda/cad-python/bin/python -m ipykernel install --user --name appautoaction-cad --display-name "AppAutoAction CAD Python"
```

Registered Jupyter kernel:

```text
AppAutoAction CAD Python
kernel name: appautoaction-cad
```

Verified packages:

| Package | Version |
| --- | --- |
| `cadquery` | `2.7.0` |
| `build123d` | `0.9.1` |
| `trimesh` | `4.12.2` |
| `meshio` | `5.3.5` |
| `numpy` | `2.4.6` |
| `OCP` | import verified |

The conda environment is local and ignored by git because it is about 2.8 GB.

## Render And Export Commands

Export the C-mount adapter STL from OpenSCAD:

```bash
openscad -o cad/designs/cmount_reflector_adapter/artifacts/cmount_reflector_adapter.stl cad/designs/cmount_reflector_adapter/cmount_reflector_adapter.scad
```

Render with Blender:

```bash
blender --background --python cad/designs/cmount_reflector_adapter/blender_render.py
```

Generate lightweight Matplotlib previews:

```bash
cad/.conda/cad-python/bin/python cad/designs/cmount_reflector_adapter/render_preview.py
```

Validate the STL:

```bash
cad/.conda/cad-python/bin/python - <<'PY'
import trimesh
m = trimesh.load("cad/designs/cmount_reflector_adapter/artifacts/cmount_reflector_adapter.stl")
print(m.is_watertight)
print(len(m.split(only_watertight=False)))
print(m.bounds)
PY
```
