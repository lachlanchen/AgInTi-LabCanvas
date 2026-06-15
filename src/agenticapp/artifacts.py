from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MIME_BY_SUFFIX = {
    ".blend": "application/octet-stream",
    ".json": "application/json; charset=utf-8",
    ".kicad_pcb": "text/plain; charset=utf-8",
    ".kicad_sch": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".scad": "text/plain; charset=utf-8",
    ".step": "model/step",
    ".stl": "model/stl",
    ".svg": "image/svg+xml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".zip": "application/zip",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_id(*parts: Any) -> str:
    raw = "\0".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def content_type_for_path(path: str | Path) -> str:
    return MIME_BY_SUFFIX.get(Path(path).suffix.lower(), "application/octet-stream")


def artifact_kind_for_path(path: str | Path, kind: str = "") -> str:
    candidate = str(kind or "").strip().lower()
    if candidate in {"image", "json", "text", "file", "model", "openscad"}:
        return candidate
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix == ".json":
        return "json"
    if suffix == ".scad":
        return "openscad"
    if suffix == ".blend":
        return "model"
    return "file"


@dataclass(frozen=True)
class ArtifactStore:
    storage_dir: Path

    @property
    def index_path(self) -> Path:
        return self.storage_dir / "artifacts.json"

    def bundle(self) -> dict[str, Any]:
        index = self._read_index()
        selected_id = str(index.get("selected_id") or "")
        items = index.get("items", [])
        if not isinstance(items, list):
            items = []
        public = [self._public_item(item, selected_id) for item in items if isinstance(item, dict)]
        public.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return {"ok": True, "items": public, "selected_id": selected_id}

    def register(
        self,
        path: str | Path,
        *,
        title: str,
        kind: str = "",
        source: str = "webapp",
        preview: str = "",
        selected: bool = True,
    ) -> dict[str, Any]:
        relative = self._safe_relative_path(path)
        artifact_id = stable_id(source, relative)
        item = {
            "id": artifact_id,
            "title": title.strip() or Path(relative).name,
            "kind": artifact_kind_for_path(relative, kind),
            "path": relative,
            "url": f"/artifacts/{relative}",
            "source": source,
            "preview": preview.strip(),
            "mime": content_type_for_path(relative),
            "created_at": now_iso(),
        }

        index = self._read_index()
        items = index.get("items", [])
        if not isinstance(items, list):
            items = []
        by_id = {str(existing.get("id")): existing for existing in items if isinstance(existing, dict)}
        if artifact_id in by_id:
            item["created_at"] = str(by_id[artifact_id].get("created_at") or item["created_at"])
        by_id[artifact_id] = {**by_id.get(artifact_id, {}), **item}
        index["items"] = list(by_id.values())
        if selected:
            index["selected_id"] = artifact_id
        self._write_index(index)
        return self._public_item(item, artifact_id if selected else str(index.get("selected_id") or ""))

    def _public_item(self, item: dict[str, Any], selected_id: str) -> dict[str, Any]:
        artifact_id = str(item.get("id") or "")
        relative = str(item.get("path") or "")
        return {
            "id": artifact_id,
            "title": str(item.get("title") or Path(relative).name),
            "kind": artifact_kind_for_path(relative, str(item.get("kind") or "")),
            "path": relative,
            "url": str(item.get("url") or f"/artifacts/{relative}"),
            "source": str(item.get("source") or "webapp"),
            "preview": str(item.get("preview") or ""),
            "mime": str(item.get("mime") or content_type_for_path(relative)),
            "created_at": str(item.get("created_at") or ""),
            "selected": artifact_id == selected_id,
        }

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"items": [], "selected_id": ""}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"items": [], "selected_id": ""}
        return data if isinstance(data, dict) else {"items": [], "selected_id": ""}

    def _write_index(self, payload: dict[str, Any]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _safe_relative_path(self, path: str | Path) -> str:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.storage_dir / resolved
        resolved = resolved.resolve()
        root = self.storage_dir.resolve()
        if not resolved.is_file() or root not in resolved.parents:
            raise ValueError("Artifact path must be an existing file inside the webapp output directory")
        return resolved.relative_to(root).as_posix()
