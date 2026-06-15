from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .scene_spec import slugify


ROOT = Path.cwd()
JLC_ORDER_SCRIPT = Path("agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py")


@dataclass(frozen=True)
class Workflow:
    kind: str
    slug: str
    title: str
    path: Path
    keywords: tuple[str, ...]
    commands: tuple[dict[str, Any], ...]
    preview_paths: tuple[Path, ...]
    source_paths: tuple[Path, ...]
    notes: tuple[str, ...] = ()

    def to_summary(self, root: Path) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "slug": self.slug,
            "title": self.title,
            "path": relpath(self.path, root),
            "keywords": list(self.keywords),
            "commands": list(self.commands),
            "preview_paths": [relpath(path, root) for path in self.preview_paths],
            "source_paths": [relpath(path, root) for path in self.source_paths],
            "notes": list(self.notes),
        }


def looks_like_lab_task_prompt(text: str) -> bool:
    lowered = text.lower()
    board_words = ("pcb", "board", "gerber", "jlc", "jlcpcb", "kicad", "manufactur")
    cad_words = ("cmount", "c-mount", "reflector", "step", "stl", "3d print")
    action_words = ("generate", "prepare", "finish", "make", "draw", "design", "order", "submit", "export", "task")
    concrete_cad = any(word in lowered for word in cad_words) or (
        "cad" in lowered and any(word in lowered for word in ("device", "part", "mechanical", "reflector", "mount", "print", "task"))
    )
    return (
        any(word in lowered for word in board_words)
        or concrete_cad
    ) and any(word in lowered for word in action_words)


def run_lab_task(payload: dict[str, Any], storage_dir: Path, *, root: Path | None = None) -> dict[str, Any]:
    root = (root or ROOT).resolve()
    prompt = str(payload.get("prompt") or payload.get("message") or "").strip()
    if not prompt:
        prompt = "Prepare a reusable PCB and CAD generation task."
    mode = str(payload.get("mode") or "auto")
    execute = bool(payload.get("execute", False))
    plan = plan_lab_task(prompt, mode=mode, root=root)

    if execute:
        plan["executions"] = execute_safe_steps(plan, root)
    else:
        plan["executions"] = []

    artifacts = write_lab_task_artifacts(plan, storage_dir, root)
    plan["artifact_paths"] = artifacts["paths"]
    store = ArtifactStore(storage_dir)
    markdown_item = store.register(artifacts["markdown"], title=f"Lab task plan: {plan['title']}", kind="text", source="lab-task", preview=plan["summary"], selected=False)
    json_item = store.register(artifacts["json"], title=f"Lab task manifest: {plan['title']}", kind="json", source="lab-task", preview="Machine-readable board/CAD workflow manifest.", selected=False)

    linked_items: list[dict[str, Any]] = []
    selected_preview = False
    for linked in artifacts["linked"]:
        kind = "image" if linked.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp"} else "file"
        item = store.register(
            linked,
            title=linked.stem.replace("-", " ").replace("_", " ").title(),
            kind=kind,
            source="lab-task",
            preview="Copied from the selected PCB/CAD workflow for canvas review.",
            selected=not selected_preview and kind == "image",
        )
        selected_preview = selected_preview or kind == "image"
        linked_items.append(item)

    if not selected_preview:
        markdown_item = store.register(artifacts["markdown"], title=f"Lab task plan: {plan['title']}", kind="text", source="lab-task", preview=plan["summary"], selected=True)

    bundle = store.bundle()
    reply = (
        f"Prepared reusable {plan['kind']} task '{plan['title']}' with "
        f"{len(plan['workflows'])} workflow(s), {len(plan['steps'])} command step(s), "
        f"and {len(artifacts['linked'])} linked preview artifact(s)."
    )
    if not execute:
        reply += " It is a safe plan only; run with --execute from CLI to regenerate local files."
    return {
        "ok": True,
        "reply": reply,
        "task": plan,
        "artifact": linked_items[0] if linked_items else markdown_item,
        "manifest_artifact": json_item,
        "artifacts": bundle,
    }


def plan_lab_task(prompt: str, *, mode: str = "auto", root: Path | None = None) -> dict[str, Any]:
    root = (root or ROOT).resolve()
    board_workflows = discover_board_workflows(root)
    cad_workflows = discover_cad_workflows(root)
    lowered = prompt.lower()
    wants_board = mode in {"pcb", "board", "mixed"} or any(word in lowered for word in ("pcb", "board", "gerber", "jlc", "kicad"))
    wants_cad = mode in {"cad", "mixed"} or any(word in lowered for word in ("cad", "cmount", "c-mount", "reflector", "openscad", "step", "stl", "3d"))
    if mode == "auto" and not wants_board and not wants_cad:
        wants_board = wants_cad = True
    if mode == "pcb":
        wants_cad = False
    if mode == "cad":
        wants_board = False

    selected: list[Workflow] = []
    if wants_board:
        board = best_workflow_match(prompt, board_workflows, preferred=("lumileds-no-resistor", "hybec-hbl-273-g4"))
        if board:
            selected.append(board)
    if wants_cad:
        cad = best_workflow_match(prompt, cad_workflows, preferred=("cmount_threaded_reflector_assembly", "cmount_reflector_adapter"))
        if cad:
            selected.append(cad)

    if not selected:
        raise ValueError("No PCB or CAD workflows were discovered in this repository.")

    kind = "mixed" if len({workflow.kind for workflow in selected}) > 1 else selected[0].kind
    title = infer_title(prompt, selected)
    steps: list[dict[str, Any]] = []
    for workflow in selected:
        for command in workflow.commands:
            steps.append({**command, "workflow": workflow.slug, "kind": workflow.kind})

    return {
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "prompt": prompt,
        "mode": mode,
        "kind": kind,
        "title": title,
        "summary": summarize_plan(kind, selected, steps),
        "workflows": [workflow.to_summary(root) for workflow in selected],
        "steps": steps,
        "guardrails": [
            "Web chat generates reviewable plans and artifacts only; it does not submit manufacturing orders.",
            "CLI --execute runs only steps marked execute_by_default=true.",
            "JLCPCB place/submit remains guarded by the existing order script and requires explicit --allow-submit there.",
            "Private addresses, phone numbers, tokens, and browser profiles stay in local config files outside git.",
        ],
    }


def discover_board_workflows(root: Path) -> list[Workflow]:
    workflows: list[Workflow] = []
    for config_path in sorted((root / "pcb").glob("*/jlcpcb_order/order-settings.json")):
        board_dir = config_path.parents[1]
        slug = board_dir.name
        config = load_json(config_path)
        board = config.get("board", {}) if isinstance(config.get("board"), dict) else {}
        title = read_markdown_title(board_dir / "README.md") or str(config.get("project_name") or board.get("name") or slug)
        generator = first_existing(sorted(board_dir.glob("generate_*.py")))
        pcb = first_existing(sorted(board_dir.glob("*.kicad_pcb")))
        sch = first_existing(sorted(board_dir.glob("*.kicad_sch")))
        gerber_dir = board_dir / "gerber"
        artifacts_dir = board_dir / "artifacts"
        render_paths = tuple(path for path in render_candidates(config_path, config, slug, artifacts_dir) if path.exists())
        source_paths = tuple(path for path in (generator, pcb, sch, config_path) if path and path.exists())
        commands: list[dict[str, Any]] = []
        if generator:
            commands.append(step("generate-board", "Regenerate KiCad project from the deterministic board script.", ["python3", relpath(generator, root)], execute=True))
        if sch:
            commands.append(step("erc", "Run KiCad schematic ERC and write JSON report.", ["kicad-cli", "sch", "erc", "--format", "json", "--severity-all", "-o", relpath(artifacts_dir / "erc.json", root), relpath(sch, root)]))
        if pcb:
            commands.extend(
                [
                    step("drc", "Run KiCad PCB DRC and write JSON report.", ["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", relpath(artifacts_dir / "drc.json", root), relpath(pcb, root)]),
                    step(
                        "export-gerbers",
                        "Export JLCPCB-ready copper, mask, silkscreen, fab, edge, and drill files.",
                        [
                            "kicad-cli",
                            "pcb",
                            "export",
                            "gerbers",
                            "--layers",
                            "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab",
                            "--precision",
                            "6",
                            "-o",
                            relpath(gerber_dir, root),
                            relpath(pcb, root),
                        ],
                    ),
                    step("export-drill", "Export drill files and drill map/report.", ["kicad-cli", "pcb", "export", "drill", "--generate-map", "--map-format", "svg", "--generate-report", "--report-path", relpath(artifacts_dir / "drill-report.txt", root), "-o", relpath(gerber_dir, root), relpath(pcb, root)]),
                    step("export-step", "Export a 3D STEP board model for mechanical review.", ["kicad-cli", "pcb", "export", "step", "--force", "--include-pads", "--include-tracks", "--include-silkscreen", "--include-soldermask", "-o", relpath(artifacts_dir / f"{slug}.step", root), relpath(pcb, root)]),
                    step("render-board", "Render a full-board KiCad PNG preview.", ["xvfb-run", "-a", "kicad-cli", "pcb", "render", "--output", relpath(artifacts_dir / f"{slug}-render-full.png", root), "--width", "1400", "--height", "1000", "--background", "opaque", "--quality", "high", "--floor", "--perspective", "--rotate", "315,0,35", "--zoom", "0.95", relpath(pcb, root)]),
                ]
            )
        if config_path.exists():
            commands.append(step("jlc-package", "Package Gerbers and write a preflight manifest.", ["python3", relpath(root / JLC_ORDER_SCRIPT, root), "--config", relpath(config_path, root), "package"], execute=True))
            commands.append(step("jlc-validate", "Validate ERC/DRC reports before any manufacturing order.", ["python3", relpath(root / JLC_ORDER_SCRIPT, root), "--config", relpath(config_path, root), "validate"], execute=True))
            commands.append(step("jlc-place-guarded", "Optional guarded submit-to-review flow. Run manually only after preview checks.", ["python3", relpath(root / JLC_ORDER_SCRIPT, root), "--config", relpath(config_path, root), "--site", "china", "--shipping-mode", "separate", "--confirm-mode", "manual", "--allow-submit", "place"], safe=False, execute=False))

        workflows.append(
            Workflow(
                kind="pcb",
                slug=slug,
                title=title,
                path=board_dir,
                keywords=keywords_for(slug, title, extra=("pcb", "board", "gerber", "jlc", "kicad")),
                commands=tuple(commands),
                preview_paths=render_paths,
                source_paths=source_paths,
                notes=tuple(str(note) for note in config.get("notes", []) if isinstance(note, str)),
            )
        )
    return workflows


def discover_cad_workflows(root: Path) -> list[Workflow]:
    workflows: list[Workflow] = []
    for design_dir in sorted((root / "cad" / "designs").glob("*")):
        if not design_dir.is_dir():
            continue
        slug = design_dir.name
        title = read_markdown_title(design_dir / "README.md") or slug.replace("_", " ").replace("-", " ").title()
        scad = first_existing(sorted(design_dir.glob("*.scad")))
        support = design_dir / "generate_support_artifacts.py"
        render = design_dir / "blender_render.py"
        python_bin = root / "cad/.conda/cad-python/bin/python"
        py = relpath(python_bin, root) if python_bin.exists() else "python3"
        preview_paths = tuple(path for path in cad_preview_candidates(design_dir) if path.exists())
        source_paths = tuple(path for path in (scad, support if support.exists() else None, render if render.exists() else None, design_dir / "README.md") if path and path.exists())
        commands: list[dict[str, Any]] = []
        if scad:
            commands.append(step("openscad-preview", "Export the default OpenSCAD assembly preview STL.", ["openscad", "-D", 'part="assembly"', "-o", relpath(design_dir / "artifacts" / "labcanvas-preview.stl", root), relpath(scad, root)]))
        if support.exists():
            commands.append(step("cad-support-artifacts", "Regenerate STEP, SVG, DXF, PDF, and decomposition support artifacts.", [py, relpath(support, root)], execute=True))
        if render.exists():
            commands.append(step("blender-cad-render", "Render the CAD assembly preview with headless Blender.", ["blender", "--background", "--python", relpath(render, root)]))
        workflows.append(
            Workflow(
                kind="cad",
                slug=slug,
                title=title,
                path=design_dir,
                keywords=keywords_for(slug, title, extra=("cad", "openscad", "step", "stl", "3d", "print", "reflector", "cmount", "c-mount")),
                commands=tuple(commands),
                preview_paths=preview_paths,
                source_paths=source_paths,
            )
        )
    return workflows


def execute_safe_steps(plan: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in plan.get("steps", []):
        if not item.get("safe", True) or not item.get("execute_by_default", False):
            continue
        command = item.get("command")
        if not isinstance(command, list) or not command:
            continue
        started = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        try:
            completed = subprocess.run([str(part) for part in command], cwd=root, capture_output=True, text=True, timeout=600, check=False)
            results.append(
                {
                    "step_id": item.get("id"),
                    "ok": completed.returncode == 0,
                    "returncode": completed.returncode,
                    "started_at": started,
                    "stdout_tail": completed.stdout[-4000:],
                    "stderr_tail": completed.stderr[-4000:],
                }
            )
        except (OSError, subprocess.SubprocessError) as exc:
            results.append({"step_id": item.get("id"), "ok": False, "started_at": started, "error": str(exc)})
    return results


def write_lab_task_artifacts(plan: dict[str, Any], storage_dir: Path, root: Path) -> dict[str, Any]:
    storage_dir = storage_dir.resolve()
    run_slug = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slugify(plan['title'])}"
    out_dir = storage_dir / "lab-tasks" / run_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = out_dir / "plan.md"
    manifest = out_dir / "plan.json"
    linked_dir = out_dir / "linked"
    linked_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    copied_destinations: set[Path] = set()
    for workflow in plan.get("workflows", []):
        for raw in workflow.get("preview_paths", []) + workflow.get("source_paths", []):
            source = (root / raw).resolve()
            if not source.is_file():
                continue
            if source.suffix.lower() not in {".png", ".svg", ".json", ".md", ".step", ".stl", ".zip", ".kicad_pcb", ".kicad_sch", ".scad"}:
                continue
            parent_slug = slugify(source.parent.name) or "source"
            destination = linked_dir / f"{workflow['slug']}--{parent_slug}--{source.name}"
            if destination in copied_destinations:
                continue
            shutil.copy2(source, destination)
            copied_destinations.add(destination)
            copied.append(destination)

    markdown.write_text(render_markdown(plan), encoding="utf-8")
    manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "markdown": markdown,
        "json": manifest,
        "linked": copied,
        "paths": {
            "markdown": relpath(markdown, storage_dir),
            "json": relpath(manifest, storage_dir),
            "linked": [relpath(path, storage_dir) for path in copied],
        },
    }


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# {plan['title']}",
        "",
        plan["summary"],
        "",
        "## Selected Workflows",
    ]
    for workflow in plan.get("workflows", []):
        lines.append(f"- `{workflow['kind']}` `{workflow['slug']}`: {workflow['title']} (`{workflow['path']}`)")
    lines.extend(["", "## CLI Commands"])
    for item in plan.get("steps", []):
        marker = "safe" if item.get("safe", True) else "manual review required"
        default = ", default execute" if item.get("execute_by_default") else ""
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"{item['description']} ({marker}{default})",
                "",
                "```bash",
                shell_join(item.get("command", [])),
                "```",
                "",
            ]
        )
    lines.append("## Guardrails")
    for guardrail in plan.get("guardrails", []):
        lines.append(f"- {guardrail}")
    if plan.get("executions"):
        lines.extend(["", "## Execution Results"])
        for result in plan["executions"]:
            status = "ok" if result.get("ok") else "failed"
            lines.append(f"- `{result.get('step_id')}`: {status} (`returncode={result.get('returncode', 'n/a')}`)")
    return "\n".join(lines).rstrip() + "\n"


def step(step_id: str, description: str, command: list[str], *, safe: bool = True, execute: bool = False) -> dict[str, Any]:
    return {
        "id": step_id,
        "description": description,
        "command": command,
        "command_text": shell_join(command),
        "safe": safe,
        "execute_by_default": execute,
    }


def best_workflow_match(prompt: str, workflows: list[Workflow], *, preferred: tuple[str, ...] = ()) -> Workflow | None:
    if not workflows:
        return None
    lowered = prompt.lower()
    scored: list[tuple[int, int, Workflow]] = []
    for workflow in workflows:
        score = 0
        for keyword in workflow.keywords:
            if keyword and keyword in lowered:
                score += max(1, len(keyword.split()))
        if workflow.slug in preferred:
            score += len(preferred) - preferred.index(workflow.slug)
        scored.append((score, len(workflow.preview_paths), workflow))
    scored.sort(key=lambda item: (item[0], item[1], item[2].slug), reverse=True)
    return scored[0][2]


def infer_title(prompt: str, workflows: list[Workflow]) -> str:
    compact = " ".join(prompt.split())
    if compact and len(compact) <= 72:
        return compact
    if len(workflows) == 1:
        return workflows[0].title
    return "PCB and CAD generation task"


def summarize_plan(kind: str, workflows: list[Workflow], steps: list[dict[str, Any]]) -> str:
    names = ", ".join(workflow.slug for workflow in workflows)
    return f"Reusable {kind} generation workflow for {names}; {len(steps)} reviewable CLI step(s) are available from the same backend used by web chat."


def render_candidates(config_path: Path, config: dict[str, Any], slug: str, artifacts_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    renders = config.get("renders", {}) if isinstance(config.get("renders"), dict) else {}
    for value in renders.values():
        if isinstance(value, str):
            path = Path(value)
            candidates.append((config_path.parent / path).resolve() if not path.is_absolute() else path)
    candidates.extend(
        [
            artifacts_dir / f"{slug}-render-full.png",
            artifacts_dir / f"{slug}-render.png",
            artifacts_dir / f"{slug}.step",
        ]
    )
    return unique_paths(candidates)


def cad_preview_candidates(design_dir: Path) -> list[Path]:
    patterns = [
        "artifacts/**/threaded_reflector_assembly_render.png",
        "artifacts/**/*render*.png",
        "artifacts/**/*assembly*.png",
        "artifacts/**/*.step",
        "artifacts/**/*.stl",
    ]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(sorted(design_dir.glob(pattern), key=lambda path: (path.stat().st_mtime if path.exists() else 0, str(path)), reverse=True))
    return unique_paths(paths[:12])


def keywords_for(slug: str, title: str, *, extra: tuple[str, ...]) -> tuple[str, ...]:
    raw = [slug, title, *extra]
    words: list[str] = []
    for item in raw:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", item.lower())
        words.append(item.lower())
        words.extend(part for part in cleaned.split() if len(part) >= 2)
    return tuple(dict.fromkeys(words))


def read_markdown_title(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return ""


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def relpath(path: Path, root: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def shell_join(command: list[Any]) -> str:
    return " ".join(quote_arg(str(part)) for part in command)


def quote_arg(value: str) -> str:
    if not value:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"
