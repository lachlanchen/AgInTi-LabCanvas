#!/usr/bin/env python3
"""Reusable routine contracts for WeChat LabCanvas worker tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = ROOT / "agentic_tools" / "wechat_gui_agent" / "docs"
AGENT_ROUTINE_CHEAT_SHEET = DOCS_DIR / "AGENT_ROUTINE_CHEAT_SHEET.md"


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
    "List every safe generated or fetched artifact in the worker JSON files array so the sender can attach it back to the source chat by default.",
    "Return blockers as stateful status or confirmation instead of silently completing partial work.",
    "Do not treat a file-picker click as artifact delivery; required files need a verified send, deferred state, or explicit blocker evidence.",
)


AUTONOMY_CHEAT_SHEET = (
    "WeChat is only the message box; the durable agent is the monitor, queue, routine registry, session registry, worker, probes, and guarded sender.",
    "Every actionable request becomes a source-scoped queue task with route_decision, routine, instruction_contract, and artifact delivery expectations.",
    "The worker must supervise the named routine first, using mature entrypoints and deterministic probes before asking a resumed per-chat agent to reason.",
    "Use the same chat's resumed worker session for ambiguous, repair, browser, or tool-heavy work; do not require the human operator to supervise manually.",
    "Long jobs persist progress in queue state and timestamps, then continue by deterministic probes or resumed worker turns until done, deferred, or blocked.",
    "Current-message permissions control irreversible stages. Generation, LazyEdit processing, and public publication are separate permissions.",
    "Required artifacts default back to the source chat; completion requires verified send, explicit deferred send state, or blocker evidence.",
)


ROUTINES: dict[str, RoutineDefinition] = {
    "research_summary": RoutineDefinition(
        id="research_summary",
        title="Research, PDF, Link, Or Summary",
        route_kinds=("research_or_summary",),
        purpose="Fetch, read, summarize, compare, or explain source material from a chat request, including link-inbox webpages, papers, GitHub repos, WeChat articles, and short-video shares.",
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
                "entrypoint": "Codex worker with source-limited browsing/files and visible browser-assist for blocked WeChat articles",
                "success": "answer is grounded in accessible same-chat sources, with blockers stated explicitly",
            },
            {
                "id": "deliver_summary",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "concise answer and any safe report/PDF are returned to the source chat",
            },
        ),
        artifact_policy=(
            "Return a concise chat summary plus safe Markdown/PDF reports when useful. "
            "Generate Markdown and, when practical, a PDF for papers, GitHub repos, technical articles, "
            "mp.weixin/Gongzhonghao articles, and useful Shipinhao/Finder summaries; list those files in the worker JSON files array."
        ),
        rules=COMMON_RULES
        + (
            "For link/read-later inbox tasks, treat shared URLs/cards/media as source material to read and summarize by default.",
            "For mp.weixin/Gongzhonghao links, direct verification pages are not final; use visible browser-assist with reuse-window/readable polling or a WeChat-native/manual-assisted capture before declaring a blocker.",
            "For Shipinhao/Finder shares, inspect accessible metadata, cached media, comments, Yuanbao/transcript/summary comments, and public mirrors, but do not post comments unless explicitly requested.",
            "For inaccessible sources, state exactly what was accessible and avoid pretending the source was fully read.",
        ),
    ),
    "career_strategy": RoutineDefinition(
        id="career_strategy",
        title="Career, Writing, And Money Strategy",
        route_kinds=("career_strategy",),
        purpose=(
            "Help the user think through writing topics, career direction, monetization, "
            "opportunities, strengths, and long-range fit using chat memory, local repo evidence, "
            "GitHub/lazying.art context, and current market research when useful."
        ),
        default_effort="medium",
        stages=(
            {
                "id": "personal_context_resolution",
                "owner": "queue_orchestrator",
                "entrypoint": "wechat memory summary + same-chat recent messages + local project/repo surface",
                "success": "current question, recurring interests, and available evidence sources are identified",
            },
            {
                "id": "opportunity_research",
                "owner": "worker_agent",
                "entrypoint": "Codex worker with local repo reading plus web/GitHub/lazying.art research when the question benefits from current context",
                "success": "evidence-backed opportunities, risks, writing directions, and next actions are drafted",
            },
            {
                "id": "deliver_strategy",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "concise WeChat answer and any safe Markdown/PDF profile report are returned to the source chat",
            },
        ),
        artifact_policy=(
            "Return a concise strategic answer in chat. For deeper asks or the daily agent, also save and attach "
            "a dated Markdown/PDF-style report with opportunities, evidence, experiments, and next actions."
        ),
        rules=COMMON_RULES
        + (
            "Treat this as practical strategic coaching, not therapy or prophecy. Do not diagnose personality or claim the user's future is fixed.",
            "Use evidence from the user's messages, local repositories, GitHub profile, lazying.art, and current public research when useful.",
            "Separate writing ideas, career positioning, product/business experiments, and immediate money-making actions.",
            "Be direct and concrete: propose small testable experiments, target users, offer wording, distribution channels, and validation signals.",
            "Prefer compounding strengths already visible in the user's work: agent tools, scientific visualization, CAD/PCB/lab automation, multilingual content, LazyEdit/video publishing, and research workflows.",
            "Do not expose private chat logs or file paths in the WeChat reply unless the user asks for paths.",
        ),
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
        artifact_policy="Return preview images plus editable SVG/manifest/TeX/source files by default when safe.",
        rules=COMMON_RULES
        + (
            "Keep generated figures atomic: overview, parts, prompts, source files, and manifests must stay editable.",
            "Do not treat a generated bitmap as the only source of truth when editable output is requested.",
        ),
    ),
    "story_script_generation": RoutineDefinition(
        id="story_script_generation",
        title="Story, Script, Or Prompt Writing",
        route_kinds=("story_or_script",),
        purpose="Write, revise, polish, or prepare story/script/prompt text while preserving the requested characters and context.",
        default_effort="medium",
        stages=(
            {
                "id": "context_resolution",
                "owner": "queue_orchestrator",
                "entrypoint": "same-chat current request + recent story context",
                "success": "characters, requested language/style, and previous story references are identified",
            },
            {
                "id": "story_or_script_write",
                "owner": "worker_agent",
                "entrypoint": "Codex worker with LALACHAN/story critic skill when applicable",
                "success": "requested story/script/prompt text is written or revised coherently",
            },
            {
                "id": "deliver_text_and_sources",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "story text and safe saved Markdown/source files are returned to the source chat",
            },
        ),
        artifact_policy="Return the story/script text in the message and attach saved Markdown/source files by default when safe.",
        rules=COMMON_RULES
        + (
            "Do not substitute image generation for a story/script request.",
            "If the user also asks for images or video, draft the story first, then satisfy the explicit visual/video stage.",
            "For LALACHAN/RaraXia/AyaChan/SasaKun story work, use the LALACHAN story quality rules; do not start Xiaoyunque video generation unless video is explicitly requested.",
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
        artifact_policy="Return full-view PNG renders first, then attach STEP/STL/Gerber/Blend/source files when safe.",
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
            "Return the requested safe media/file as a WeChat attachment by default, including text/source artifacts. "
            "Do not close required artifact work "
            "until delivery is verified, deferred, or blocked with evidence."
        ),
        rules=COMMON_RULES
        + (
            "Never use nearby media if exact local_id/token matching fails.",
            "Use browser assist for login/CAPTCHA/download consent instead of bypassing the site.",
        ),
    ),
    "file_intake": RoutineDefinition(
        id="file_intake",
        title="Bare File Intake",
        route_kinds=("file_intake",),
        purpose="Perform a cheap default intake for a WeChat file upload that has no explicit instruction.",
        default_effort="low",
        stages=(
            {
                "id": "exact_file_sync",
                "owner": "queue_orchestrator",
                "entrypoint": "media_sync + source local_id/token matching",
                "success": "the exact uploaded file is visible in the source-scoped downloads folder",
            },
            {
                "id": "metadata_receipt",
                "owner": "queue_orchestrator",
                "entrypoint": "prepare_worker_preflight -> deterministic_file_intake_result",
                "success": "file type, size, checksum, and task-scoped saved copy are recorded",
            },
            {
                "id": "receipt_delivery",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "a short receipt is returned to the source chat",
            },
        ),
        artifact_policy=(
            "Save a task-scoped copy plus manifest under ignored output/wechat_worker. "
            "Send a concise text receipt by default; do not resend the uploaded file unless asked."
        ),
        rules=COMMON_RULES
        + (
            "Do not deep-read, summarize, translate, convert, or publish a bare upload unless the current message explicitly asks.",
            "The copied file and manifest are for follow-up tasks from the same source chat.",
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
                "entrypoint": "wechat_autopublish_video.py --message-local-id first, then verified same-chat artifact ledger fallback",
                "success": "current/source video row is cached/copied, or a ledger artifact matches that row md5/length, or fail closed",
            },
            {
                "id": "lazyedit_process",
                "owner": "worker_agent",
                "entrypoint": "lazyedit_publish.py with correction and metadata prompt files",
                "success": "processed video/subtitles/metadata are verified",
            },
            {
                "id": "public_publish",
                "owner": "queue_orchestrator",
                "entrypoint": "lazyedit_publish.py --platforms",
                "success": "requested current-message platforms are terminal-verified or the task requeues",
            },
            {
                "id": "public_publish_verified",
                "owner": "queue_orchestrator",
                "entrypoint": "verify_lazyedit_publish_stage",
                "success": "all requested platforms have terminal LazyEdit/remote evidence before saying published",
            },
            {
                "id": "status_delivery",
                "owner": "queue_orchestrator",
                "entrypoint": "send_result_with_retries",
                "success": "verified job ids/status or resumable pending state are returned to the source chat",
            },
        ),
        required_gates=("exact_video_resolution", "public_publish_verified"),
        rules=COMMON_RULES
        + (
            "Old chat history may explain subtitles but cannot authorize public publish.",
            "Old chat history must not broaden source-video selection beyond the current quoted/source local-id rows.",
            "If exact source video is missing, fail closed; do not publish old or nearby videos.",
            "Never call queued/submitted/running jobs published; only terminal platform evidence is published.",
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
                "owner": "worker_agent_supervised_by_queue",
                "entrypoint": "Codex worker calls LazyEdit CLI/API through stored routine scripts; deterministic probes only monitor/requeue",
                "success": "LazyEdit import/process completes with context prompts or requeues generation_poststage_pending",
            },
            {
                "id": "public_publish",
                "owner": "worker_agent_supervised_by_queue",
                "entrypoint": "Codex worker invokes run_generated_video_lazyedit_command(..., publish=True) or the equivalent LazyEdit CLI",
                "success": "requested current-message platforms finish or requeue for verification",
            },
        ),
        required_gates=("wechat_artifact_delivery_gate",),
        artifact_policy="A generated MP4 and any safe story/prompt/source artifacts must be delivered to the source chat before LazyEdit/public poststage.",
        rules=COMMON_RULES
        + (
            "Do not process old WeChat MP4, LazyEdit, or AutoPublish files as the new generated-video output.",
            "Long generation waits must live in queue state and CDP probes, not one multi-hour model call.",
            "LazyEdit import and public publishing require explicit current-message permission.",
            "For LazyEdit stages, Codex worker supervision owns context selection and command execution; deterministic code is limited to source isolation, duplicate guards, probes, and terminal verification.",
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
    if any(marker in lowered for marker in ("xiaoyunque", "seedance", "小云雀")) or (
        any(marker in lowered for marker in ("lalachan", "raraxia", "ayachan", "sasakun", "啦啦侠", "阿芽酱", "飒飒君"))
        and any(marker in lowered for marker in ("video", "mp4", "视频", "影片", "短片", "动画", "動畫"))
    ):
        return "generated_video"
    if any(marker in lowered for marker in ("story", "script", "plot", "narrative", "dialogue", "故事", "剧本", "劇本", "脚本", "腳本", "提示词", "提示詞")):
        return "story_script_generation"
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
        "autonomy_contract": agent_autonomy_contract(routine),
    }


def agent_autonomy_contract(routine: RoutineDefinition) -> dict[str, Any]:
    return {
        "system_role": "autonomous_routine_supervisor",
        "wechat_role": "message_transport_only",
        "human_operator_role": "approval_only_for_login_captcha_payment_public_posting_deletion_or_unsafe_irreversible_actions",
        "execution_center": "wechat_task_worker.run_task_orchestrator",
        "agent_session": "resume_exact_chat_worker_session",
        "autonomous_completion_required": True,
        "manual_supervision_required": False,
        "routine_id": routine.id,
        "routine_title": routine.title,
        "cheat_sheet": list(AUTONOMY_CHEAT_SHEET),
        "loop": [
            "receive_and_coalesce",
            "route_and_contract",
            "claim_queue_task",
            "run_deterministic_stage_or_resume_worker_agent",
            "persist_progress_or_blocker",
            "deliver_required_artifacts_to_source_chat",
            "continue_poststages_only_when_current_request_permits",
        ],
    }


def ensure_task_routine_contract(task: dict[str, Any]) -> dict[str, Any]:
    existing = task.get("routine")
    if isinstance(existing, dict) and existing.get("id") in ROUTINES:
        if not isinstance(existing.get("autonomy_contract"), dict):
            routine = ROUTINES.get(str(existing.get("id")), ROUTINES["general_worker"])
            existing["autonomy_contract"] = agent_autonomy_contract(routine)
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
    cheat_path = artifact_dir / "agent_routine_cheat_sheet.md"
    json_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_routine_contract_markdown(contract), encoding="utf-8")
    cheat_path.write_text(format_agent_routine_cheat_sheet(contract), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "cheat_sheet": str(cheat_path),
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
    autonomy = contract.get("autonomy_contract") if isinstance(contract.get("autonomy_contract"), dict) else {}
    if autonomy:
        lines.extend(["", "## Autonomy Contract"])
        for item in autonomy.get("cheat_sheet") or []:
            lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def format_agent_routine_cheat_sheet(contract: dict[str, Any]) -> str:
    autonomy = contract.get("autonomy_contract") if isinstance(contract.get("autonomy_contract"), dict) else {}
    loop = autonomy.get("loop") if isinstance(autonomy.get("loop"), list) else []
    sheet = autonomy.get("cheat_sheet") if isinstance(autonomy.get("cheat_sheet"), list) else list(AUTONOMY_CHEAT_SHEET)
    lines = [
        "# Agent Routine Cheat Sheet",
        "",
        f"- Task: {contract.get('task_id') or '(not set)'}",
        f"- Chat: {contract.get('chat') or '(not set)'}",
        f"- Routine: `{contract.get('id')}` - {contract.get('title')}",
        f"- Execution center: `{autonomy.get('execution_center') or 'wechat_task_worker.run_task_orchestrator'}`",
        f"- Agent session: `{autonomy.get('agent_session') or 'resume_exact_chat_worker_session'}`",
        "",
        "## Autonomy Rules",
    ]
    lines.extend(f"- {item}" for item in sheet)
    lines.extend(["", "## Loop"])
    lines.extend(f"{index}. `{item}`" for index, item in enumerate(loop, start=1))
    lines.extend(
        [
            "",
            "## Stop Conditions",
            "- `done`: requested safe stages completed and required artifacts were delivered or explicitly not needed.",
            "- `send_deferred_artifact` / `send_deferred_locked`: artifact exists but WeChat delivery must be retried by the outbox.",
            "- `generation_waiting` / `generation_poststage_pending` / `publish_poststage_pending`: long work is persisted and will resume later.",
            "- `waiting_confirmation`: login, CAPTCHA, payment, public posting, deletion, or another irreversible/sensitive decision needs approval.",
        ]
    )
    if AGENT_ROUTINE_CHEAT_SHEET.exists():
        lines.extend(["", "## Source Manual", f"- {AGENT_ROUTINE_CHEAT_SHEET.relative_to(ROOT)}"])
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
        "autonomy_contract": contract.get("autonomy_contract") or {},
        "stages": stages,
        "rules": contract.get("rules") or [],
    }
    return (
        "Routine supervisor contract:\n"
        "Follow this routine first. Use Codex reasoning to supervise stages, solve blockers, and verify outputs; "
        "do not design a different workflow unless the current request conflicts with the routine safety checks.\n"
        "Autonomy rule: the system itself owns execution through the queue, routine stages, and the resumed per-chat worker agent. "
        "Do not ask the human operator to supervise ordinary safe work; only ask for required approvals or real blockers.\n"
        "```json\n"
        f"{json.dumps(compact, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:96] or "routine"


if __name__ == "__main__":
    print(json.dumps({"ok": True, "routines": list_routines()}, ensure_ascii=False, indent=2))
