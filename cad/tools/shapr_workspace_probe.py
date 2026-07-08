#!/usr/bin/env python3
"""Inspect Shapr3D .shapr packages without modifying the source file.

The .shapr container is a ZIP file whose `workspace` member is a SQLite
database. Most body payloads are Parasolid transmit blobs; history/properties
are a mix of MessagePack-like blobs and JSON.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import msgpack
except ImportError:  # pragma: no cover - optional analysis dependency.
    msgpack = None


@dataclass
class TableCount:
    name: str
    rows: int


@dataclass
class OperationNode:
    node_id: int
    node_type: int
    title: str
    operation: str
    children: list[int]
    body_ids: list[int]
    name_ids_sample: list[int]
    positions: list[list[float]]


@dataclass
class ImportedBody:
    body_id: int
    bytes: int
    header: str


def unpack_shapr(source: Path, workdir: Path) -> Path:
    if source.suffix.lower() == ".shapr":
        with zipfile.ZipFile(source) as zf:
            zf.extractall(workdir)
        workspace = workdir / "workspace"
    else:
        workspace = source
    if not workspace.exists():
        raise FileNotFoundError(f"workspace database not found: {workspace}")
    return workspace


def msgpack_or_none(blob: bytes) -> Any | None:
    if msgpack is None:
        return None
    try:
        return msgpack.unpackb(blob, raw=False, strict_map_key=False)
    except Exception:
        return None


def collect_refs(obj: Any, ref_kind: int) -> list[int]:
    refs: list[int] = []
    if isinstance(obj, list):
        if len(obj) == 2 and isinstance(obj[0], int) and obj[0] == ref_kind:
            if isinstance(obj[1], int):
                refs.append(obj[1])
        for item in obj:
            refs.extend(collect_refs(item, ref_kind))
    elif isinstance(obj, dict):
        for item in obj.values():
            refs.extend(collect_refs(item, ref_kind))
    return refs


def collect_positions(obj: Any) -> list[list[float]]:
    found: list[list[float]] = []

    def simplify(value: Any) -> list[float] | None:
        if isinstance(value, list):
            if len(value) == 1:
                return simplify(value[0])
            if len(value) == 2 and value[0] == 5 and isinstance(value[1], list):
                nums = value[1]
                if len(nums) == 3 and all(isinstance(n, (int, float)) for n in nums):
                    return [float(n) for n in nums]
            for item in value:
                result = simplify(item)
                if result is not None:
                    return result
        return None

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if item == "position" and idx + 1 < len(value):
                    result = simplify(value[idx + 1])
                    if result is not None:
                        found.append(result)
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(obj)
    return found


def table_counts(conn: sqlite3.Connection) -> list[TableCount]:
    rows = conn.execute(
        "select name from sqlite_master where type='table' order by name"
    ).fetchall()
    counts: list[TableCount] = []
    for (name,) in rows:
        count = conn.execute(f'select count(*) from "{name}"').fetchone()[0]
        counts.append(TableCount(name=name, rows=int(count)))
    return counts


def operation_nodes(conn: sqlite3.Connection) -> list[OperationNode]:
    nodes: list[OperationNode] = []
    rows = conn.execute(
        "select HistoryTreeNodeID, HistoryTreeNodeType, Properties "
        "from HistoryTreeNodes order by HistoryTreeNodeID"
    ).fetchall()
    child_payloads: dict[int, Any] = {}
    for node_id, node_type, props in rows:
        child_payloads[int(node_id)] = msgpack_or_none(props)

    for node_id, node_type, props in rows:
        payload = child_payloads[int(node_id)]
        if node_type != 2 or not isinstance(payload, list):
            continue
        title = str(payload[1]) if len(payload) > 1 else ""
        operation = str(payload[2]) if len(payload) > 2 else ""
        children = [int(x) for x in payload[3]] if len(payload) > 3 else []
        body_ids: list[int] = []
        name_ids: list[int] = []
        positions: list[list[float]] = []
        for child_id in children:
            child = child_payloads.get(child_id)
            body_ids.extend(collect_refs(child, 11))
            name_ids.extend(collect_refs(child, 7))
            positions.extend(collect_positions(child))
        nodes.append(
            OperationNode(
                node_id=int(node_id),
                node_type=int(node_type),
                title=title,
                operation=operation,
                children=children,
                body_ids=body_ids,
                name_ids_sample=name_ids[:40],
                positions=positions,
            )
        )
    return nodes


def imported_bodies(conn: sqlite3.Connection) -> list[ImportedBody]:
    bodies: list[ImportedBody] = []
    rows = conn.execute(
        "select ImportedBodyID, BodyData from HistoryImportedBodies order by ImportedBodyID"
    ).fetchall()
    for body_id, data in rows:
        header = "".join(chr(b) if 32 <= b < 127 else "." for b in data[:96])
        bodies.append(ImportedBody(body_id=int(body_id), bytes=len(data), header=header))
    return bodies


def extract_parasolid_bodies(conn: sqlite3.Connection, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for body_id, data in conn.execute(
        "select ImportedBodyID, BodyData from HistoryImportedBodies order by ImportedBodyID"
    ):
        (out_dir / f"body_{int(body_id):05d}.x_b").write_bytes(data)


def write_markdown(
    source: Path,
    output: Path,
    counts: Iterable[TableCount],
    nodes: Iterable[OperationNode],
    bodies: Iterable[ImportedBody],
) -> None:
    counts = list(counts)
    nodes = list(nodes)
    bodies = list(bodies)
    imports = [n for n in nodes if n.operation == "MaterializeImportedBodies"]
    transforms = [n for n in nodes if n.operation == "Transform"]
    sketches = [n for n in nodes if "Sketch" in n.title]
    extrudes = [n for n in nodes if n.operation == "Extrude"]
    largest = sorted(bodies, key=lambda b: b.bytes, reverse=True)[:20]

    lines = [
        "# Nature.shapr Workspace Probe",
        "",
        f"Source: `{source}`",
        "",
        "## Summary",
        "",
        "- Container: `.shapr` ZIP with `workspace` SQLite database.",
        f"- Tables with rows: `{sum(1 for c in counts if c.rows)}`.",
        f"- History operation nodes: `{len(nodes)}`.",
        f"- Imports: `{len(imports)}`; transforms: `{len(transforms)}`; sketches: `{len(sketches)}`; extrudes: `{len(extrudes)}`.",
        f"- Imported Parasolid body blobs: `{len(bodies)}`.",
        "- The native history here is mainly imported STEP assemblies plus transforms; it is not a full editable Shapr feature tree for the OpenHI 4f parts.",
        "",
        "## Public Tooling Check",
        "",
        "- `looking-glass-station/Shapr3d_backup`: useful reference for locating and packaging Shapr3D local projects as `.shapr`; it does not decode native body/history geometry.",
        "- `DleBlancNT/shapr-backup`: another local-project backup/export utility; it also preserves `.shapr` packages rather than converting workspace internals.",
        "- `tinyprocessing/Shapr3DConverter`: sample iOS conversion project with `.shapr` fixtures, but not a usable native geometry decoder for this task.",
        "- `Alfredoalv13/shapr3d-mcp`: relevant direction for AI-driven CAD through build123d/STEP exchange, not direct `.shapr` feature editing.",
        "- Conclusion: use this probe for SQLite/history/body extraction, and use exported STEP/Parasolid conversion for geometry work.",
        "- The script uses `msgpack` when available to decode Shapr history properties; without it, table/body summaries still work but operation details are sparse.",
        "",
        "## Operation Tree",
        "",
        "| Node | Title | Operation | Bodies | Positions |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for node in nodes:
        body_text = ", ".join(str(x) for x in node.body_ids[:24])
        if len(node.body_ids) > 24:
            body_text += ", ..."
        pos_text = "; ".join("[" + ", ".join(f"{v:g}" for v in p) + "]" for p in node.positions)
        lines.append(
            f"| {node.node_id} | `{node.title}` | `{node.operation}` | {body_text} | {pos_text} |"
        )

    lines.extend(
        [
            "",
            "## Row Counts",
            "",
            "| Table | Rows |",
            "| --- | ---: |",
        ]
    )
    for count in counts:
        if count.rows:
            lines.append(f"| `{count.name}` | {count.rows} |")

    lines.extend(
        [
            "",
            "## Largest Imported Bodies",
            "",
            "| Body ID | Bytes | Header clue |",
            "| ---: | ---: | --- |",
        ]
    )
    for body in largest:
        header = body.header.replace("|", "\\|")
        lines.append(f"| {body.body_id} | {body.bytes} | `{header}` |")

    lines.extend(
        [
            "",
            "## Interpretation For 4f Redesign",
            "",
            "- Use `Nature.shapr` to recover assembly intent, imported body IDs, transforms, and Parasolid payloads.",
            "- Use the already-exported STEP files under `cad/extracted/OpenHI_STEP/` for direct geometric measurement of A/B/C/lens-holder thread axes.",
            "- To change only the larger female receiver from the loose old `30.4 mm` fit toward `30.0 mm`, the safest route is a new derived CAD reconstruction that preserves measured body envelopes and rebuilds only the local female-thread socket.",
            "- A native Shapr feature edit is possible only if you provide the original file where that specific holder was modeled with editable sketches/features, not only imported STEP bodies.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help=".shapr file or extracted workspace SQLite DB")
    parser.add_argument("--out-dir", type=Path, default=Path("cad/analysis/nature_shapr_probe"))
    parser.add_argument("--keep-workspace", action="store_true", help="copy the extracted SQLite workspace to OUT_DIR")
    parser.add_argument("--extract-parasolid", action="store_true", help="write body_XXXXX.x_b files under OUT_DIR/blobs")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shapr_probe_") as tmp:
        workspace = unpack_shapr(args.source, Path(tmp))
        workspace_copy = args.out_dir / "workspace.sqlite"
        if args.keep_workspace:
            shutil.copy2(workspace, workspace_copy)
        conn = sqlite3.connect(workspace)
        counts = table_counts(conn)
        nodes = operation_nodes(conn)
        bodies = imported_bodies(conn)
        manifest = {
            "source": str(args.source),
            "workspace_copy": str(workspace_copy) if args.keep_workspace else None,
            "table_counts": [asdict(c) for c in counts],
            "operation_nodes": [asdict(n) for n in nodes],
            "imported_bodies": [asdict(b) for b in bodies],
        }
        (args.out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        write_markdown(args.source, args.out_dir / "README.md", counts, nodes, bodies)
        if args.extract_parasolid:
            extract_parasolid_bodies(conn, args.out_dir / "blobs")
        conn.close()

    print(args.out_dir / "README.md")
    print(args.out_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
