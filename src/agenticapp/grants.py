from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


EXPECTED_OUTPUTS = (
    "proposal.md",
    "proposal.tex",
    "proposal.pdf",
    "references.bib",
    "figures/figure_manifest.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(value or "").strip()).strip("-._").lower()
    return slug[:96] or "grant-project"


def default_project_dir(title: str, *, root: str | Path = ".") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(root).resolve() / "output" / "grants" / f"{stamp}-{safe_slug(title)}"


def initialize_grant_workspace(
    project_dir: str | Path,
    *,
    title: str,
    objective: str,
    task_id: str = "",
    chat: str = "",
) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)
    for relative in ("sources", "evidence", "figures/parts", "figures/renders", "build"):
        (project / relative).mkdir(parents=True, exist_ok=True)

    goal_path = project / "goal.json"
    existing_goal = _load_json(goal_path)
    created_at = str(existing_goal.get("created_at") or utc_now())
    goal = {
        "schema_version": 1,
        "kind": "grant_proposal_goal",
        "project_id": str(existing_goal.get("project_id") or safe_slug(task_id or title)),
        "title": title.strip(),
        "objective": objective.strip(),
        "task_id": task_id,
        "chat": chat,
        "status": str(existing_goal.get("status") or "active"),
        "execution_mode": "codex_goal_with_durable_manifest",
        "created_at": created_at,
        "updated_at": utc_now(),
        "completion_gates": [
            "scope_and_funder_requirements_recorded",
            "claims_grounded_in_traceable_sources",
            "proposal_markdown_and_latex_written",
            "editable_figure_manifest_and_preview_created",
            "pdf_compiled_and_visually_checked",
            "artifact_manifest_validated",
        ],
        "expected_outputs": list(EXPECTED_OUTPUTS),
        "external_action_policy": "Drafting only. Never submit the grant or change credentials without explicit authorization.",
    }
    _write_json(goal_path, goal)

    _write_if_missing(
        project / "README.md",
        _workspace_readme(title=title, objective=objective),
    )
    _write_if_missing(
        project / "grant_brief.md",
        _grant_brief(title=title, objective=objective),
    )
    (project / "current_request.md").write_text(
        _current_request(title=title, objective=objective),
        encoding="utf-8",
    )
    _write_if_missing(project / "references.bib", "% Add verified references here.\n")
    _write_if_missing(
        project / "sources" / "source_manifest.json",
        json.dumps({"schema_version": 1, "sources": []}, ensure_ascii=False, indent=2) + "\n",
    )
    _write_if_missing(
        project / "figures" / "figure_manifest.json",
        json.dumps(
            {
                "schema_version": 1,
                "editable": True,
                "overview": "figures/renders/overview.png",
                "assembly_source": "figures/figure_assembly.tex",
                "parts": [],
                "tool_policy": {
                    "biorender": "Use authenticated BioRender MCP/browser for academic assets when available.",
                    "fallback": "Use editable SVG/TeX parts when BioRender is not authenticated.",
                    "bitmap": "Concept overview only; never the sole source of truth.",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    prompt_path = project / "agent_goal_prompt.md"
    prompt_path.write_text(
        build_grant_goal_prompt(project, title=title, objective=objective),
        encoding="utf-8",
    )
    return grant_workspace_status(project)


def build_grant_goal_prompt(project_dir: str | Path, *, title: str, objective: str) -> str:
    project = Path(project_dir).expanduser().resolve()
    return f"""# Grant Goal Contract

Project: `{project}`
Title: {title.strip()}
Objective: {objective.strip()}

Use this directory as the dedicated source of truth for the grant. At the start, use the Codex `create_goal` tool when it is available, with the objective above. If that tool is unavailable in the current surface, continue from `goal.json` and state that fact in private task evidence; never pretend the tool was called. Use `update_goal` only after every completion gate is genuinely satisfied.

Work as an evidence-grounded grant-writing agent:

1. Read `current_request.md`, `grant_brief.md`, same-chat context, supplied files, and relevant primary literature. Record stable source metadata in `sources/source_manifest.json` and `references.bib`.
2. Separate direct evidence, inference, hypothesis, and proposed work. Do not invent pilot data, collaborators, facilities, budgets, approvals, citations, or funder requirements.
3. Produce `proposal.md`, `proposal.tex`, and a polished `proposal.pdf`. Include significance, innovation, specific aims, approach, milestones, risks/alternatives, validation, reproducibility, timeline, and requested budget logic when relevant.
4. Keep figures editable and atomic. Maintain `figures/figure_manifest.json`, named parts under `figures/parts/`, an assembly source, and a checked overview preview. Prefer BioRender for authenticated academic assets; otherwise use editable SVG/TeX rather than blocking the grant.
5. Compile and inspect the PDF, then run `labcanvas grant validate --project-dir {project}`. Repair failures before completion.
6. Return the PDF, proposal sources, bibliography, figure manifest, and useful previews to the originating chat. Do not submit the grant or perform any irreversible external action.
"""


def grant_workspace_status(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    goal = _load_json(project / "goal.json")
    outputs = {name: (project / name).is_file() for name in EXPECTED_OUTPUTS}
    return {
        "ok": project.is_dir(),
        "project_dir": str(project),
        "goal": goal,
        "outputs": outputs,
        "prompt_path": str(project / "agent_goal_prompt.md"),
    }


def compile_grant(project_dir: str | Path, *, timeout: int = 300) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    tex = project / "proposal.tex"
    if not tex.is_file():
        return {"ok": False, "project_dir": str(project), "error": "proposal.tex is missing"}
    if shutil.which("latexmk"):
        command = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "proposal.tex"]
    elif shutil.which("pdflatex"):
        command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "proposal.tex"]
    else:
        return {"ok": False, "project_dir": str(project), "error": "latexmk/pdflatex is unavailable"}
    result = subprocess.run(
        command,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=max(10, min(int(timeout), 1800)),
        check=False,
    )
    return {
        "ok": result.returncode == 0 and (project / "proposal.pdf").is_file(),
        "project_dir": str(project),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-3000:],
        "stderr_tail": result.stderr[-3000:],
        "pdf": str(project / "proposal.pdf") if (project / "proposal.pdf").is_file() else "",
    }


def validate_grant_workspace(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    checks: dict[str, Any] = {
        "project_dir": project.is_dir(),
        "goal": (project / "goal.json").is_file(),
        "proposal_markdown": _substantive_file(project / "proposal.md", minimum_bytes=300),
        "proposal_tex": _substantive_file(project / "proposal.tex", minimum_bytes=300),
        "proposal_pdf": _valid_pdf(project / "proposal.pdf"),
        "references": _substantive_file(project / "references.bib", minimum_bytes=40),
        "source_manifest": _valid_source_manifest(project / "sources" / "source_manifest.json"),
        "figure_manifest": _valid_figure_manifest(project / "figures" / "figure_manifest.json", project),
    }
    checks["pdf_text_readable"] = _pdf_text_readable(project / "proposal.pdf") if checks["proposal_pdf"] else False
    required = tuple(checks.values())
    result = {
        "ok": all(value is True for value in required),
        "project_dir": str(project),
        "checks": checks,
        "validated_at": utc_now(),
    }
    _write_json(project / "validation.json", result)
    return result


def _workspace_readme(*, title: str, objective: str) -> str:
    return f"""# {title.strip()}

Objective: {objective.strip()}

This ignored workspace preserves the grant brief, evidence, editable figures, LaTeX source, compiled PDF, and validation record. `goal.json` is the durable execution contract. No grant submission is authorized by this workspace.
"""


def _grant_brief(*, title: str, objective: str) -> str:
    return f"""# Grant Brief

## Working Title
{title.strip()}

## Objective
{objective.strip()}

## Funder And Call
- Funder:
- Scheme/call:
- Deadline:
- Eligibility:
- Page/format limits:

## Scientific Context
- Unmet need:
- Central hypothesis:
- Preliminary evidence supplied by the requester:
- Claims that still require verification:

## Deliverables
- Proposal Markdown, LaTeX, and checked PDF
- Traceable source manifest and bibliography
- Editable figure parts, manifest, assembly source, and preview
- Validation record
"""


def _current_request(*, title: str, objective: str) -> str:
    return f"""# Current Grant Request

## Working Title
{title.strip()}

## Current Objective
{objective.strip()}

This file is refreshed when the same durable grant task receives an updated request. Preserve verified evidence and authored proposal content, but reconcile them with this current objective before continuing.
"""


def _valid_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 16:
        return False
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _substantive_file(path: Path, *, minimum_bytes: int) -> bool:
    return path.is_file() and path.stat().st_size >= minimum_bytes


def _pdf_text_readable(path: Path) -> bool:
    executable = shutil.which("pdftotext")
    if not executable:
        return _valid_pdf(path)
    result = subprocess.run(
        [executable, str(path), "-"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _valid_source_manifest(path: Path) -> bool:
    payload = _load_json(path)
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return False
    for source in sources:
        if not isinstance(source, dict):
            return False
        if not str(source.get("title") or source.get("name") or "").strip():
            return False
        if not any(str(source.get(key) or "").strip() for key in ("doi", "url", "path", "identifier")):
            return False
    return True


def _valid_figure_manifest(path: Path, project: Path) -> bool:
    payload = _load_json(path)
    parts = payload.get("parts")
    if payload.get("editable") is not True or not isinstance(parts, list) or not parts:
        return False
    overview = _project_file(project, payload.get("overview"))
    assembly = _project_file(project, payload.get("assembly_source"))
    if not (_substantive_file(overview, minimum_bytes=16) and _substantive_file(assembly, minimum_bytes=16)):
        return False
    for part in parts:
        if not isinstance(part, dict) or not str(part.get("id") or "").strip():
            return False
        source = _project_file(project, part.get("source") or part.get("source_path"))
        if not _substantive_file(source, minimum_bytes=8):
            return False
    return True


def _project_file(project: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else project / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
