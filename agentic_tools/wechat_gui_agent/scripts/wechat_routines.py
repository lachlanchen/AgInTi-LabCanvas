#!/usr/bin/env python3
"""Reusable routine contracts for WeChat LabCanvas worker tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class RoutineDefinition:
    id: str
    title: str
    route_kinds: tuple[str, ...]
    purpose: str
    stages: tuple[dict[str, Any], ...]
    default_effort: str = "medium"
    required_gates: tuple[str, ...] = ()
    artifact_policy: str = "Return safe generated/downloaded artifacts in the worker JSON files array."
    rules: tuple[str, ...] = field(default_factory=tuple)


COMMON_RULES = (
    "Use this routine as the execution contract; do not invent a new workflow when a stage has an entrypoint.",
    "Re-check the current request, route_decision, source chat, and source local_id before every external action.",
    "Use only same-chat source rows, explicit references, and source-scoped synced media.",
    "Save evidence and generated artifacts under the task artifact directory or other ignored output/private folders.",
    "Return blockers as stateful status or confirmation instead of silently completing partial work.",
    "Do not treat a file-picker click as artifact delivery; required files need a verified send, deferred state, or explicit blocker evidence.",
)


ROUTINES: dict[str, RoutineDefinition] = {
    "research_summary": RoutineDefinition(
        id="research_summary",
        title="Research, PDF, Link, Or Summary",
        route_kinds=("research_or_summary",),
        purpose="Fetch, read, summarize, compare, or explain source material from a chat request.",
        default_effort="medium",
        stages=(
            {
                "id": "source_resolution",
                "owner": "queue_orchestrator",
                "entrypoint": "same-chat context + media/link extraction",
                "success": "exact source rows, links, PDFs, or text context are identified",
            },
            {
                "id": "research_or_read",
                "owner": "worker_agent",
                "entrypoint": "Codex worker with source-limited browsing/files",
                "success": "answer is grounded in accessible same-chat sources",
            },
            {
                "id": "deliver_summary",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "concise answer and any safe report/PDF are returned to the source chat",
            },
        ),
        rules=COMMON_RULES,
    ),
    "editable_figure_image": RoutineDefinition(
        id="editable_figure_image",
        title="Editable Figure Or Image Artifact",
        route_kinds=("generate_image", "edit_existing_media"),
        purpose="Create or edit figures as atomic, maintainable artifacts rather than one opaque bitmap.",
        default_effort="medium",
        stages=(
            {
                "id": "source_or_prompt_resolution",
                "owner": "queue_orchestrator",
                "entrypoint": "source_reference_rows + media_sync",
                "success": "prompt and exact image/media references are identified or fail source-limited",
            },
            {
                "id": "editable_artifact_generation",
                "owner": "worker_agent",
                "entrypoint": "labcanvas studio figure-grid / AgInTi image generation / TeX assembly",
                "success": "overview plus editable SVG/manifest/parts are saved",
            },
            {
                "id": "artifact_delivery_gate",
                "owner": "queue_orchestrator",
                "entrypoint": "prepare_result_files -> send_result_with_retries",
                "success": "preview and editable source files are returned or deferred with evidence",
            },
        ),
        required_gates=("artifact_delivery_gate",),
        artifact_policy="Return preview images plus editable SVG/manifest/TeX/source files where available.",
        rules=COMMON_RULES
        + (
            "Keep generated figures atomic: overview, parts, prompts, source files, and manifests must stay editable.",
            "Do not treat a generated bitmap as the only source of truth when editable output is requested.",
        ),
    ),
    "labcanvas_cad_pcb": RoutineDefinition(
        id="labcanvas_cad_pcb",
        title="LabCanvas CAD/PCB/Blender Artifact",
        route_kinds=("cad_pcb_labcanvas",),
        purpose="Run LabCanvas CAD, PCB, OpenSCAD, KiCad, Blender, or render routines.",
        default_effort="high",
        stages=(
            {
                "id": "spec_resolution",
                "owner": "worker_agent",
                "entrypoint": "studio lab-task / scene-template / existing project files",
                "success": "CAD/PCB/render specification is saved with source assumptions",
            },
            {
                "id": "tool_execution",
                "owner": "worker_agent",
                "entrypoint": "OpenSCAD/KiCad/Blender/LabCanvas CLI",
                "success": "source files, exports, and render previews are generated",
            },
            {
                "id": "artifact_delivery_gate",
                "owner": "queue_orchestrator",
                "entrypoint": "prepare_result_files -> send_result_with_retries",
                "success": "PNG preview plus STEP/STL/Gerber/Blend/source artifacts are returned or deferred",
            },
        ),
        required_gates=("artifact_delivery_gate",),
        artifact_policy="Return full-view PNG renders first, then STEP/STL/Gerber/Blend/source files when safe.",
        rules=COMMON_RULES
        + (
            "Use existing repo CAD/PCB CLI routines before raw GUI automation.",
            "Do not submit orders, purchase, delete, or publish without current-message permission and confirmation.",
        ),
    ),
    "file_download_save": RoutineDefinition(
        id="file_download_save",
        title="File, Media, Or Link Save",
        route_kinds=("file_download_or_save",),
        purpose="Download, cache, copy, or organize source-scoped WeChat media/files/links.",
        default_effort="medium",
        stages=(
            {
                "id": "exact_source_resolution",
                "owner": "queue_orchestrator",
                "entrypoint": "media_sync + exact local_id/token matching",
                "success": "exact source file/media/link is available or task fails source-limited",
            },
            {
                "id": "copy_or_fetch",
                "owner": "worker_agent",
                "entrypoint": "wechat_media_sync.py / wechat_autopublish_video.py / browser assist when needed",
                "success": "requested file is copied, downloaded, or blocked with evidence",
            },
            {
                "id": "artifact_delivery_gate",
                "owner": "queue_orchestrator",
                "entrypoint": "prepare_result_files -> send_result_with_retries -> apply_send_outcome",
                "success": "safe file/media/path is returned, or the task is left deferred/blocked with evidence",
            },
        ),
        required_gates=("exact_source_resolution", "artifact_delivery_gate"),
        artifact_policy=(
            "Return the requested safe media/file as a WeChat attachment when supported; "
            "text-like artifacts may be returned as saved paths. Do not close required artifact work "
            "until delivery is verified, deferred, or blocked with evidence."
        ),
        rules=COMMON_RULES
        + (
            "Never use nearby media if exact local_id/token matching fails.",
            "Use browser assist for login/CAPTCHA/download consent instead of bypassing the site.",
        ),
    ),
    "video_publish_existing": RoutineDefinition(
        id="video_publish_existing",
        title="Existing Video LazyEdit/Publish",
        route_kinds=("process_existing_video", "publish_video"),
        purpose="Process or publish an existing source-scoped video through LazyEdit and requested platforms.",
        default_effort="high",
        stages=(
            {
                "id": "exact_video_resolution",
                "owner": "queue_orchestrator",
                "entrypoint": "wechat_autopublish_video.py --message-local-id / media_sync",
                "success": "exact same-chat video is cached and copied, or fail closed",
            },
            {
                "id": "lazyedit_process",
                "owner": "worker_agent",
                "entrypoint": "lazyedit_publish.py with correction and metadata prompt files",
                "success": "processed video/subtitles/metadata are verified",
            },
            {
                "id": "public_publish",
                "owner": "worker_agent",
                "entrypoint": "lazyedit_publish.py --platforms",
                "success": "only requested current-message platforms are queued/published",
            },
            {
                "id": "status_delivery",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "job ids/status and safe files are returned to the source chat",
            },
        ),
        required_gates=("exact_video_resolution",),
        rules=COMMON_RULES
        + (
            "Old chat history may explain subtitles but cannot authorize public publish.",
            "If exact source video is missing, fail closed; do not publish old or nearby videos.",
        ),
    ),
    "generated_video": RoutineDefinition(
        id="generated_video",
        title="Generated Video Routine",
        route_kinds=("generate_video",),
        purpose="Create a new video, monitor long generation, send MP4 back, then run optional poststages.",
        default_effort="medium",
        stages=(
            {
                "id": "route_contract",
                "owner": "fast_chat_agent",
                "entrypoint": "enqueue_worker_task -> routine contract + generated_video_route_contract",
                "success": "current-request stage permissions and route decision are persisted",
            },
            {
                "id": "story_and_prompt",
                "owner": "worker_agent",
                "entrypoint": "run_worker_codex_once with LALACHAN/Xiaoyunque context",
                "success": "story, prompt, upload evidence, and submitted/running/blocked state or MP4 are saved",
            },
            {
                "id": "xyq_deterministic_monitor",
                "owner": "queue_orchestrator",
                "entrypoint": "deterministic_generated_video_monitor_result",
                "success": "MP4 downloaded or generation_waiting requeued with next_poll_at",
            },
            {
                "id": "wechat_artifact_delivery_gate",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries -> apply_send_outcome",
                "success": "sent_file_paths contains verified MP4 before LazyEdit/public poststage starts",
            },
            {
                "id": "lazyedit_poststage",
                "owner": "queue_orchestrator",
                "entrypoint": "deterministic_generated_video_poststage_result",
                "success": "LazyEdit import/process completes or requeues generation_poststage_pending",
            },
            {
                "id": "public_publish",
                "owner": "queue_orchestrator",
                "entrypoint": "run_generated_video_lazyedit_command(..., publish=True)",
                "success": "requested current-message platforms finish or requeue for verification",
            },
        ),
        required_gates=("wechat_artifact_delivery_gate",),
        artifact_policy="A generated MP4 must be delivered to the source chat before LazyEdit/public poststage.",
        rules=COMMON_RULES
        + (
            "Do not process old WeChat MP4, LazyEdit, or AutoPublish files as the new generated-video output.",
            "Long generation waits must live in queue state and CDP probes, not one multi-hour model call.",
            "LazyEdit import and public publishing require explicit current-message permission.",
        ),
    ),
    "general_worker": RoutineDefinition(
        id="general_worker",
        title="General Worker Supervised Task",
        route_kinds=("other_worker",),
        purpose="Fallback routine for tasks that need backend work but do not match a specialized route.",
        default_effort="medium",
        stages=(
            {
                "id": "scope_check",
                "owner": "worker_agent",
                "entrypoint": "task route_decision + recent context review",
                "success": "safe interpretation and required tools are identified",
            },
            {
                "id": "execute_or_block",
                "owner": "worker_agent",
                "entrypoint": "Codex worker and available LabCanvas tools",
                "success": "requested safe work completes or returns a precise blocker",
            },
            {
                "id": "deliver_result",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "answer and safe artifacts are returned or deferred",
            },
        ),
        rules=COMMON_RULES,
    ),
}


ROUTE_TO_ROUTINE = {
    route_kind: routine.id
    for routine in ROUTINES.values()
    for route_kind in routine.route_kinds
}


def list_routines() -> list[dict[str, Any]]:
    return [routine_to_dict(routine) for routine in ROUTINES.values()]


def routine_to_dict(routine: RoutineDefinition) -> dict[str, Any]:
    return {
        "id": routine.id,
        "title": routine.title,
        "route_kinds": list(routine.route_kinds),
        "purpose": routine.purpose,
        "default_effort": routine.default_effort,
        "required_gates": list(routine.required_gates),
        "artifact_policy": routine.artifact_policy,
        "rules": list(routine.rules),
        "stages": [dict(stage) for stage in routine.stages],
    }


def routine_id_for_route(route_decision: dict[str, Any] | None, request_text: str = "") -> str:
    route = route_decision if isinstance(route_decision, dict) else {}
    route_kind = str(route.get("route_kind") or "").strip()
    if route_kind in ROUTE_TO_ROUTINE:
        return ROUTE_TO_ROUTINE[route_kind]
    lowered = str(request_text or "").lower()
    if any(marker in lowered for marker in ("pcb", "kicad", "openscad", "blender", "cad", "gerber", "render", "渲染", "电路板")):
        return "labcanvas_cad_pcb"
    if any(marker in lowered for marker in ("lalachan", "raraxia", "ayachan", "sasakun", "xiaoyunque", "seedance", "小云雀", "啦啦侠", "阿芽酱", "飒飒君")):
        return "generated_video"
    if any(marker in lowered for marker in ("lazyedit", "autopublish", "shipinhao", "视频号", "youtube", "instagram")):
        return "video_publish_existing"
    if any(marker in lowered for marker in ("image", "figure", "diagram", "aginti", "biorender", "图片", "图", "示意图")):
        return "editable_figure_image"
    if any(marker in lowered for marker in ("download", "save", "copy", "file", "pdf", "link", "url", "下载", "保存", "复制", "文件", "链接")):
        return "file_download_save"
    if any(marker in lowered for marker in ("paper", "research", "summarize", "summary", "论文", "研究", "总结", "摘要")):
        return "research_summary"
    return "general_worker"


def build_routine_contract(
    route_decision: dict[str, Any] | None,
    request_text: str = "",
    *,
    task_id: str = "",
    chat: str = "",
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routine_id = routine_id_for_route(route_decision, request_text)
    routine = ROUTINES.get(routine_id, ROUTINES["general_worker"])
    route = route_decision if isinstance(route_decision, dict) else {}
    return {
        "id": routine.id,
        "title": routine.title,
        "task_id": task_id,
        "chat": chat,
        "source": source or {},
        "route_kind": str(route.get("route_kind") or ""),
        "project": str(route.get("project") or ""),
        "purpose": routine.purpose,
        "selected_at": datetime.now().isoformat(timespec="seconds"),
        "selected_by": "wechat_routines.routine_id_for_route",
        "default_effort": routine.default_effort,
        "artifact_policy": routine.artifact_policy,
        "required_gates": list(routine.required_gates),
        "rules": list(routine.rules),
        "stages": [dict(stage) for stage in routine.stages],
        "state_policy": {
            "long_waits": "Persist queue state and deterministic probe timestamps instead of holding a model call.",
            "blocked": "Return confirmation or blocker status with evidence and keep task resumable.",
            "delivery": "Do not mark required artifacts complete until sent, explicitly deferred, or blocked.",
        },
    }


def ensure_task_routine_contract(task: dict[str, Any]) -> dict[str, Any]:
    existing = task.get("routine")
    if isinstance(existing, dict) and existing.get("id") in ROUTINES:
        return existing
    contract = build_routine_contract(
        task.get("route_decision") if isinstance(task.get("route_decision"), dict) else {},
        str(task.get("request") or ""),
        task_id=str(task.get("id") or ""),
        chat=str(task.get("chat") or ""),
        source=task.get("source") if isinstance(task.get("source"), dict) else {},
    )
    task["routine"] = contract
    return contract


def write_routine_contract(task: dict[str, Any], artifact_dir: Path) -> dict[str, str]:
    contract = ensure_task_routine_contract(task)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifact_dir / "routine_contract.json"
    md_path = artifact_dir / "routine_contract.md"
    json_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_routine_contract_markdown(contract), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "rule": "Worker must supervise this routine instead of inventing a new workflow.",
    }


def format_routine_contract_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# WeChat Routine Contract",
        "",
        f"- Routine: `{contract.get('id')}` - {contract.get('title')}",
        f"- Task: {contract.get('task_id') or '(not set)'}",
        f"- Chat: {contract.get('chat') or '(not set)'}",
        f"- Route kind: {contract.get('route_kind') or '(not set)'}",
        f"- Default effort: {contract.get('default_effort') or 'medium'}",
        "",
        "## Purpose",
        str(contract.get("purpose") or "").strip(),
        "",
        "## Stages",
    ]
    for stage in contract.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        lines.append(f"- `{stage.get('id')}` | owner: {stage.get('owner')} | entrypoint: {stage.get('entrypoint')}")
        if stage.get("success"):
            lines.append(f"  Success: {stage.get('success')}")
    lines.extend(["", "## Required Gates"])
    gates = contract.get("required_gates") or []
    if gates:
        lines.extend(f"- `{gate}`" for gate in gates)
    else:
        lines.append("- none beyond source, safety, and delivery checks")
    lines.extend(["", "## Rules"])
    for rule in contract.get("rules") or []:
        lines.append(f"- {rule}")
    lines.extend(["", "## Artifact Policy", str(contract.get("artifact_policy") or "").strip()])
    return "\n".join(lines).rstrip() + "\n"


def routine_prompt_context(task: dict[str, Any]) -> str:
    contract = ensure_task_routine_contract(task)
    stages = [
        {
            "id": stage.get("id"),
            "owner": stage.get("owner"),
            "entrypoint": stage.get("entrypoint"),
            "success": stage.get("success"),
        }
        for stage in contract.get("stages") or []
        if isinstance(stage, dict)
    ]
    compact = {
        "id": contract.get("id"),
        "title": contract.get("title"),
        "purpose": contract.get("purpose"),
        "required_gates": contract.get("required_gates") or [],
        "artifact_policy": contract.get("artifact_policy"),
        "stages": stages,
        "rules": contract.get("rules") or [],
    }
    return (
        "Routine supervisor contract:\n"
        "Follow this routine first. Use Codex reasoning to supervise stages, solve blockers, and verify outputs; "
        "do not design a different workflow unless the current request conflicts with the routine safety checks.\n"
        "```json\n"
        f"{json.dumps(compact, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:96] or "routine"


if __name__ == "__main__":
    print(json.dumps({"ok": True, "routines": list_routines()}, ensure_ascii=False, indent=2))
