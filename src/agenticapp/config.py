from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "targets": [
        {
            "name": "blender",
            "kind": "blender",
            "description": "Blender editor bridge, typically exposed by a Blender MCP add-on.",
            "transport": {"type": "http_json", "url": "http://127.0.0.1:8400/agent"},
            "mcp": {"command": "uvx", "args": ["blender-mcp"]},
        },
        {
            "name": "unity",
            "kind": "unity",
            "description": "Unity editor bridge or MCP package endpoint.",
            "transport": {"type": "http_json", "url": "http://127.0.0.1:8600/agent"},
            "mcp": {"command": "uvx", "args": ["unity-mcp"]},
        },
        {
            "name": "unreal",
            "kind": "unreal",
            "description": "Unreal editor bridge using a plugin or Python remote execution proxy.",
            "transport": {"type": "http_json", "url": "http://127.0.0.1:8500/agent"},
            "mcp": {"command": "npx", "args": ["-y", "@runreal/unreal-mcp"]},
        },
        {
            "name": "biorender",
            "kind": "biorender",
            "description": "BioRender official remote MCP endpoint, with browser launch fallback.",
            "transport": {"type": "browser", "url": "https://app.biorender.com/"},
            "mcp": {
                "url": "https://mcp.services.biorender.com/mcp",
                "transport": "http",
                "headers": {"Authorization": "Bearer ${BIORENDER_API_KEY}"},
            },
        },
    ]
}

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class Target:
    name: str
    kind: str
    description: str = ""
    transport: dict[str, Any] = field(default_factory=dict)
    mcp: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    targets: tuple[Target, ...]

    def get_target(self, name: str) -> Target:
        for target in self.targets:
            if target.name == name:
                return target
        names = ", ".join(target.name for target in self.targets) or "none"
        raise KeyError(f"Unknown target {name!r}. Available targets: {names}")


def default_config_path() -> Path | None:
    for candidate in (Path("agenticapp.targets.json"), Path("configs/targets.example.json")):
        if candidate.exists():
            return candidate
    return None


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else default_config_path()
    data = json.loads(config_path.read_text(encoding="utf-8")) if config_path else DEFAULT_CONFIG
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> AppConfig:
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list):
        raise ValueError("Config must contain a 'targets' list")

    targets: list[Target] = []
    seen: set[str] = set()
    for item in raw_targets:
        if not isinstance(item, dict):
            raise ValueError("Each target must be an object")
        name = str(item.get("name", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not name:
            raise ValueError("Target is missing a non-empty 'name'")
        if not kind:
            raise ValueError(f"Target {name!r} is missing a non-empty 'kind'")
        if name in seen:
            raise ValueError(f"Duplicate target name {name!r}")
        seen.add(name)
        transport = item.get("transport") or {"type": "noop"}
        if not isinstance(transport, dict):
            raise ValueError(f"Target {name!r} transport must be an object")
        mcp = item.get("mcp") or {}
        if not isinstance(mcp, dict):
            raise ValueError(f"Target {name!r} mcp must be an object")
        targets.append(
            Target(
                name=name,
                kind=kind,
                description=str(item.get("description", "")),
                transport=transport,
                mcp=mcp,
                enabled=bool(item.get("enabled", True)),
            )
        )
    return AppConfig(tuple(targets))


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda match: os.environ.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value
