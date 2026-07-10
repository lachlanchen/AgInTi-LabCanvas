#!/usr/bin/env python3
"""Write simple single-mesh 3MF files from validated STL files.

This avoids trimesh's optional 3MF export dependency chain while keeping the
print handoff deterministic for slicers that prefer 3MF over STL.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import trimesh


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""


RELS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


def _load_as_mesh(stl_path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(stl_path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geom
            for geom in loaded.geometry.values()
            if isinstance(geom, trimesh.Trimesh) and len(geom.faces) > 0
        ]
        if not meshes:
            raise ValueError(f"No mesh geometry found in {stl_path}")
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"No triangle mesh found in {stl_path}")
    return loaded


def _format_float(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def export_stl_as_3mf(stl_path: Path | str, threemf_path: Path | str, *, title: str | None = None) -> None:
    """Export an STL mesh to a minimal 3MF file using millimeter units."""
    stl = Path(stl_path)
    target = Path(threemf_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    mesh = _load_as_mesh(stl)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    model_title = escape(title or target.stem)

    vertex_xml = "\n".join(
        f'          <vertex x="{_format_float(x)}" y="{_format_float(y)}" z="{_format_float(z)}"/>'
        for x, y, z in vertices
    )
    triangle_xml = "\n".join(
        f'          <triangle v1="{int(a)}" v2="{int(b)}" v3="{int(c)}"/>'
        for a, b, c in faces
    )
    model_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">{model_title}</metadata>
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
{vertex_xml}
        </vertices>
        <triangles>
{triangle_xml}
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1"/>
  </build>
</model>
"""

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("3D/3dmodel.model", model_xml)
