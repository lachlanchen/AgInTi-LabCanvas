#!/usr/bin/env python3
"""Worker-side helper for slower WeChat chatops tasks."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from wechat_codex_sessions import run_codex_session
from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
LAZYEDIT_PUBLISH_SKILL = ROOT / "agentic_tools" / "wechat_gui_agent" / "skills" / "lazyedit-publish-workflow" / "SKILL.md"
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
EFFORT_ORDER = ["low", "medium", "high"]
OUTBOUND_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".pdf",
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".zip",
    ".step",
    ".stp",
    ".stl",
    ".scad",
    ".kicad_pcb",
    ".kicad_sch",
    ".blend",
}
DEFAULT_MAX_OUTBOUND_BYTES = 100 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--chat", default="wechat-chat")
    parser.add_argument("--enqueue", help="Add a task to the private queue and exit.")
    parser.add_argument("--once", action="store_true", help="Process one pending task.")
    parser.add_argument("--loop", action="store_true", help="Continuously process pending tasks.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--send", action="store_true", help="Send worker result back to WeChat.")
    parser.add_argument("--send-targets", type=Path, default=DEFAULT_SEND_TARGETS, help="Ignored JSON mapping chat names to GUI target specs.")
    args = parser.parse_args()

    if args.enqueue:
        task = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "chat": args.chat,
            "request": args.enqueue,
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        append_jsonl(args.queue, task)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.once or args.loop:
        while True:
            processed = process_one(args.queue, args.chat, send=args.send, send_targets=args.send_targets, log_idle=not args.loop)
            if not args.loop:
                return 0
            if not processed:
                import time

                time.sleep(args.poll_seconds)
        return 0
    raise SystemExit("Use --enqueue, --once, or --loop")


def process_one(queue: Path, chat: str, *, send: bool, send_targets: Path = DEFAULT_SEND_TARGETS, log_idle: bool = True) -> bool:
    task = next_pending(queue)
    if not task:
        if log_idle:
            print(json.dumps({"status": "no-pending-task"}, ensure_ascii=False))
        return False
    result_text = run_worker_codex(task)
    result = parse_worker_result(result_text)
    result = prepare_result_files(result, result_text)
    target_chat = str(task.get("chat") or chat)
    send_errors = []
    if send:
        try:
            if result["message"]:
                send_message(result["message"], target_chat, send_targets)
            if result["confirmation"]:
                send_message(result["confirmation"], target_chat, send_targets)
            for file_path in result["files"]:
                send_file(Path(file_path), target_chat, send_targets)
        except Exception as exc:
            send_errors.append(str(exc))
    if result.get("skipped_files"):
        task["skipped_files"] = result["skipped_files"]
    if send_errors:
        task["status"] = "send_failed"
        task["send_errors"] = send_errors
    else:
        task["status"] = "waiting_confirmation" if result["confirmation"] else "done"
    task["completed_at"] = datetime.now().isoformat(timespec="seconds")
    task["result"] = result
    rewrite_task(queue, task)
    if send_errors:
        event_status = "send-failed"
    elif result["confirmation"]:
        event_status = "waiting-confirmation-sent" if send else "waiting-confirmation"
    else:
        event_status = "done-sent" if send else "done"
    record_event(
        chat_name=task.get("chat", chat),
        action="worker_task",
        direction="outbound",
        message=result["confirmation"] or result["message"] or result_text,
        status=event_status,
        db_path=DEFAULT_DB,
        metadata=task,
    )
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return True


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_tasks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def next_pending(path: Path) -> dict[str, Any] | None:
    return next((task for task in read_tasks(path) if task.get("status") == "pending"), None)


def rewrite_task(path: Path, updated: dict[str, Any]) -> None:
    tasks = read_tasks(path)
    for index, task in enumerate(tasks):
        if task.get("id") == updated.get("id"):
            tasks[index] = updated
            break
    path.write_text("".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks), encoding="utf-8")


def run_worker_codex(task: dict[str, Any]) -> str:
    policy = choose_worker_policy(task)
    task["worker_policy"] = policy
    result = run_worker_codex_once(task, policy)
    next_policy = escalated_policy(policy, result)
    if next_policy:
        task["worker_policy"] = {**next_policy, "escalated_from": policy["reasoning_effort"]}
        result = run_worker_codex_once(task, next_policy)
    return result


def run_worker_codex_once(task: dict[str, Any], policy: dict[str, Any]) -> str:
    artifact_dir = worker_artifact_dir(task)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    task.setdefault("artifact_dir", str(artifact_dir))
    tool_context = build_worker_tool_context(task)
    prompt = f"""You are the slower worker agent for a WeChat LabCanvas chat.
Handle the task using available local files/tools. Save downloaded or generated artifacts under the repo's ignored private/output folders when possible.
The task may be a fragment or follow-up from an ongoing WeChat thread. Use the task's source and context fields to resolve pronouns, repeated requests, "same/again/this/that/last one", and incomplete messages.
Before doing work or composing the final message, check whether the recent context already contains a bot/self answer or completed result for the same request. Avoid sending the same answer again; return only the new delta, current status, missing decision, or remaining artifact.
Strict source isolation: the task's `chat`, `source.local_id`, `source.server_id`, `context`, and any explicit source/reference rows embedded in `request` define the only WeChat source. Never use media, files, or generated artifacts from another chat, another direct message, a nearby queue item, or an unrelated old task.
If no exact matching source media is available for "this image", "this PDF", "this video", "last one", or a quoted command, return a source-limited message asking for the exact file/source. Do not synthesize or continue from unrelated media.
Exception for WeChat video-to-AutoPublish requests: if the task asks to copy/download a WeChat video to Nutstore AutoPublish and the recent context contains a same-chat video row, first run:
`PYTHONPATH=src python -m agenticapp wechat autopublish-video --chat "<chat>" --sync --fetch-gui --since-minutes 720 --json`
This opens the chat in the isolated WeChat desktop, clicks the latest visible video so the official client caches the MP4, media-syncs it, and atomically copies it to `/home/lachlan/Nutstore Files/AutoPublish/AutoPublish`. Only report missing source after that command fails or returns no matching video.

{tool_context}

Return either plain text or this JSON shape:
{{
  "message": "concise message to send back",
  "files": ["/absolute/path/to/file.pdf", "/absolute/path/to/preview.png"],
  "confirmation": "optional question to ask before continuing"
}}

Use confirmation when an important choice, purchase, external send, deletion, privacy-sensitive action, or irreversible action needs approval.
If a download is blocked by login, CAPTCHA, bot check, consent page, or a site that needs human action, do not try to bypass it.
Open a human-assist browser in the isolated virtual desktop with:
PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<url>" --json
Then return a confirmation telling the user to complete the manual step in noVNC and approve continuation.
If other external tools or files are not available, say exactly what is needed next.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""
    result = run_codex_session(
        prompt,
        chat_name=str(task.get("chat") or "wechat-chat"),
        role="worker",
        model=str(policy["model"]),
        reasoning_effort=str(policy["reasoning_effort"]),
        sandbox=str(policy["sandbox"]),
        timeout_seconds=int(policy["timeout_seconds"]),
        workdir=ROOT,
        reuse=bool(policy.get("reuse_session", True)),
    )
    if not result["ok"]:
        return f"Worker failed: {str(result.get('stderr_tail') or result.get('message') or '').strip()[:1000]}"
    task["codex_session"] = {
        "role": "worker",
        "thread_id_short": str(result.get("thread_id") or "")[:8],
        "resumed": bool(result.get("resumed")),
        "fallback_started": bool(result.get("fallback_started")),
    }
    return str(result.get("message") or "").strip()


def worker_artifact_dir(task: dict[str, Any]) -> Path:
    task_id = safe_slug(str(task.get("id") or "manual-task"))
    return ROOT / "output" / "wechat_worker" / task_id


def build_worker_tool_context(task: dict[str, Any]) -> str:
    artifact_dir = str(task.get("artifact_dir") or worker_artifact_dir(task))
    prompt_text = str(task.get("request") or "").strip()
    quoted_prompt = json.dumps(prompt_text or "prepare CAD/PCB/Blender artifacts", ensure_ascii=False)
    return f"""LabCanvas tool playbook:
- Use `{artifact_dir}` as the preferred working/output folder for new artifacts.
- Match every input file/media path to this task's exact `chat`, `source.local_id`, `source.server_id`, explicit source/reference rows in `request`, or source-scoped context text. Do not borrow files from another group/direct chat or from unrelated previous worker tasks.
- If the exact requested media is missing, stop with a source-limited message asking the user to resend/provide it instead of using a nearby file.
- For editable paper-figure grids plus AgInTi image-generation payloads/live images, run:
  `PYTHONPATH=src python -m agenticapp studio figure-grid {quoted_prompt} --storage-dir output/webapp --json`
- For PCB/CAD planning and reusable artifacts, run:
  `PYTHONPATH=src python -m agenticapp studio lab-task {quoted_prompt} --mode auto --execute --storage-dir output/webapp --json`
- For a Blender experiment/setup render, write or reuse a scene JSON under `{artifact_dir}`, then run:
  `PYTHONPATH=src python -m agenticapp render-scene <scene.json> --output-dir {artifact_dir} --timeout 240`
- For a built-in starting scene, run:
  `PYTHONPATH=src python -m agenticapp scene-template experiment-setup --output {artifact_dir}/scene.json`
- For direct target envelopes or MCP handoff, use:
  `PYTHONPATH=src python -m agenticapp studio dispatch blender "<instruction>" --json`
- For existing KiCad/OpenSCAD/Blender workflows, prefer the commands emitted by `studio lab-task`; they know the repo's PCB, CAD, Gerber, STEP, STL, and render locations.
- For AgInTi figure requests, return the editable SVG grid plus AgInTi prompt/request/manifest files; if live image generation is enabled and `imagePaths` contains PNG/JPG outputs, include those image paths too.
- For PCB render requests, return the KiCad/board PNG preview and any STEP/Gerber zip when available. For CAD/Blender render requests, return the PNG render plus STEP/STL/source spec when useful.

LazyEdit/AutoPublish video publishing:
- For publish, re-publish, Shipinhao, YouTube, Instagram, AutoPublish, LazyEdit, subtitle-correction, metadata, or platform-monitoring requests, first read the repo-local workflow:
  `sed -n '1,260p' {LAZYEDIT_PUBLISH_SKILL.relative_to(ROOT)}`
- Prefer the LazyEdit CLI in `/home/lachlan/DiskMech/Projects/lazyedit` over manual browser work:
  `cd /home/lachlan/DiskMech/Projects/lazyedit && source ~/miniconda3/etc/profile.d/conda.sh && conda activate lazyedit`
- If the source is a WeChat video, resolve the exact same-chat media first with:
  `PYTHONPATH=src python -m agenticapp wechat autopublish-video --chat "<chat>" --sync --fetch-gui --since-minutes 720 --json`
- For real publishes, verify configured logo settings with:
  `curl -fsS http://127.0.0.1:18787/api/ui-settings/logo_settings | jq .`
- For processing plus publish, use `scripts/lazyedit_publish.py` with `--use-current-settings`, platform flags, `--guided-monitor`, `--wait`, and separate `--correction-prompt-file` and `--metadata-prompt-file` files when context is needed.
- Use `--no-process` only when the final LazyEdit output already exists or the user explicitly asks to reuse the last/current output.
- Monitor local and remote queues:
  `curl -fsS http://127.0.0.1:18787/api/autopublish/queue | jq '.jobs[:8]'`
  `curl -fsS http://lazyingart:8081/publish/queue | jq '.jobs[:8]'`
  `ssh lachlan@lazyingart 'tmux capture-pane -pt autopub:0 -S -120 | tail -n 120'`
- If Shipinhao or another platform needs QR login, CAPTCHA, consent, or a manual click, open the isolated browser via `PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<url>" --json`, then ask for human completion instead of bypassing it.
- Final responses should include LazyEdit job id, remote job id if present, platforms, status, whether processing was reused/rerun, and safe output paths.

Shipinhao/Finder and short-video shares:
- Treat comment sections as useful auxiliary evidence when they are accessible from the local GUI, cached metadata, a browser-assist session, or a public mirrored page.
- Search visible or retrieved comments for Tencent Yuanbao-style prompts such as `@元宝`, `腾讯元宝`, `英文全文`, `全文`, `总结`, `摘要`, `字幕`, `转写`, `transcript`, and `summary`; these comments often request or contain transcript/summary material.
- Also skim other highly visible comments for quoted lines, timestamps, topic summaries, corrections, names, links, or context that helps infer the video content.
- Do not post a comment or ask Yuanbao yourself unless the user explicitly requests that action. Reading comments is allowed; writing comments needs confirmation.
- If the actual video, comments, transcript, or reliable public mirror are not available, do not produce a "deep analysis" or imply you watched/read the source. Return a source-limited note, state what was accessible, and ask the user to provide the video/comments/transcript or approve a manual/browser path if deeper analysis is needed.

Artifact return contract:
- If you generate or find preview files, include their existing absolute or repo-relative paths in the JSON `files` array. The outer worker sends those files to WeChat.
- Prefer PNG/JPG/SVG/PDF/STEP/STL/ZIP/SCAD/KiCad files. Do not include decrypted WeChat DBs, private config, cookies, tokens, browser profiles, or chat logs.
- Do not say a file was sent unless it is listed in `files` and exists locally.
"""


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:96] or "task"


def choose_worker_policy(task: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(task, ensure_ascii=False).lower()
    high_keywords = [
        "deep research",
        "pcb",
        "kicad",
        "cad",
        "openscad",
        "blender",
        "render",
        "install",
        "github",
        "mcp",
        "commit",
        "push",
        "publish",
        "order",
        "jlc",
        "wenext",
        "labview",
        "full task",
        "完整",
        "下单",
        "电路板",
        "渲染",
        "安装",
    ]
    medium_keywords = [
        "paper",
        "pdf",
        "search",
        "summarize",
        "summary",
        "dataset",
        "figure",
        "figure grid",
        "diagram",
        "aginti",
        "imagegen",
        "image generation",
        "icons",
        "overview",
        "research",
        "nature",
        "hyperspectral",
        "论文",
        "总结",
        "搜索",
        "文献",
        "高光谱",
        "高光譜",
    ]
    if any(keyword in text for keyword in high_keywords):
        effort, timeout = "high", 600
    elif any(keyword in text for keyword in medium_keywords) or len(text) > 1200:
        effort, timeout = "medium", 300
    else:
        effort, timeout = "low", 120
    return {
        "model": "gpt-5.5",
        "reasoning_effort": effort,
        "sandbox": worker_sandbox(),
        "timeout_seconds": timeout,
    }


def worker_sandbox() -> str:
    raw = os.environ.get("WECHAT_WORKER_CODEX_SANDBOX", "danger-full-access").strip()
    aliases = {
        "full": "danger-full-access",
        "full-access": "danger-full-access",
        "danger": "danger-full-access",
        "workspace": "workspace-write",
    }
    return aliases.get(raw, raw or "danger-full-access")


def escalated_policy(policy: dict[str, Any], result: str) -> dict[str, Any] | None:
    text = str(result or "").lower()
    failure_markers = [
        "worker failed",
        "timed out",
        "cannot complete",
        "can't complete",
        "unable to complete",
        "i cannot",
        "i can't",
        "无法完成",
        "不能完成",
        "没有完成",
    ]
    if len(text.strip()) >= 80 and not any(marker in text for marker in failure_markers):
        return None
    effort = str(policy.get("reasoning_effort") or "medium")
    try:
        index = EFFORT_ORDER.index(effort)
    except ValueError:
        index = 1
    if index >= len(EFFORT_ORDER) - 1:
        return None
    next_effort = EFFORT_ORDER[index + 1]
    timeout = 300 if next_effort == "medium" else 600
    return {**policy, "reasoning_effort": next_effort, "timeout_seconds": timeout}


def parse_worker_result(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            message = str(data.get("message") or "").strip()
            confirmation = str(data.get("confirmation") or data.get("confirm") or "").strip()
            files = file_entries_from_json(data)
            return {"message": message, "confirmation": confirmation, "files": files, "raw": text}
    except Exception:
        pass
    message_lines = []
    files = []
    for line in text.splitlines():
        if line.strip().upper().startswith("FILE:"):
            files.append(str(Path(line.split(":", 1)[1].strip()).expanduser()))
        else:
            message_lines.append(line)
    return {"message": "\n".join(message_lines).strip(), "confirmation": "", "files": files, "raw": text}


def file_entries_from_json(data: Any) -> list[str]:
    files: list[str] = []
    file_keys = {"file", "files", "path", "paths", "artifact", "artifacts", "attachment", "attachments", "image", "images", "render", "renders", "preview", "previews"}

    def visit(value: Any, *, key: str = "") -> None:
        lowered = key.lower()
        if isinstance(value, str):
            if lowered in file_keys or looks_like_artifact_path(value):
                files.append(value)
        elif isinstance(value, list):
            for item in value:
                visit(item, key=key)
        elif isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, key=str(child_key))

    visit(data)
    return unique_strings(files)


def prepare_result_files(result: dict[str, Any], raw_text: str) -> dict[str, Any]:
    candidates = unique_strings([*result.get("files", []), *extract_artifact_paths(raw_text)])
    files: list[str] = []
    skipped: list[dict[str, str]] = []
    for candidate in candidates:
        path = resolve_candidate_path(candidate)
        if not path.exists():
            skipped.append({"path": candidate, "reason": "missing"})
            continue
        ok, reason = is_safe_outbound_file(path)
        if not ok:
            skipped.append({"path": str(path), "reason": reason})
            continue
        files.append(str(path))
    result["files"] = unique_strings(files)
    if skipped:
        result["skipped_files"] = skipped
    if result["files"] and not result.get("message"):
        result["message"] = f"Generated {len(result['files'])} artifact(s); sending them now."
    return result


def extract_artifact_paths(text: str) -> list[str]:
    candidates: list[str] = []
    absolute = r"/[A-Za-z0-9_./:@%+=,\-]+"
    relative = r"(?:output|cad|pcb|publications|references|examples)/[A-Za-z0-9_./:@%+=,\-]+"
    for match in re.finditer(f"(?:{absolute}|{relative})", text):
        token = clean_path_token(match.group(0))
        if looks_like_artifact_path(token):
            candidates.append(token)
    return unique_strings(candidates)


def looks_like_artifact_path(value: str) -> bool:
    token = clean_path_token(value)
    return bool(token and Path(token).suffix.lower() in OUTBOUND_SUFFIXES)


def clean_path_token(value: str) -> str:
    return str(value or "").strip().strip("\"'`").rstrip(".,;:)]}>")


def resolve_candidate_path(value: str) -> Path:
    path = Path(clean_path_token(value)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def is_safe_outbound_file(path: Path) -> tuple[bool, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        return False, "not-a-file"
    if resolved.suffix.lower() not in OUTBOUND_SUFFIXES:
        return False, "unsupported-suffix"
    if ".private" in resolved.parts or resolved == PRIVATE or PRIVATE in resolved.parents:
        return False, "private-path"
    private_markers = {"wechat_decrypt", "xwechat_files", "cookies", "session", "tokens", "keys"}
    if any(marker in part.lower() for part in resolved.parts for marker in private_markers):
        return False, "sensitive-path"
    max_bytes = int(os.environ.get("WECHAT_WORKER_MAX_OUTBOUND_BYTES", DEFAULT_MAX_OUTBOUND_BYTES))
    try:
        if resolved.stat().st_size > max_bytes:
            return False, "too-large"
    except OSError:
        return False, "stat-failed"
    return True, ""


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def send_message(message: str, chat: str, send_targets: Path) -> None:
    target = load_send_target(chat, send_targets)
    if target:
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": message, "targets": [target]}, handle, ensure_ascii=False)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
                    "--targets-file",
                    str(target_file),
                    "--send",
                    "--prefer-current",
                    "--pause",
                    os.environ.get("WECHAT_WORKER_SEND_PAUSE", "0.35"),
                    "--mirror-db",
                    str(DEFAULT_DB),
                ],
                cwd=ROOT,
                check=True,
                timeout=60,
                env=wechat_send_env(),
            )
        finally:
            target_file.unlink(missing_ok=True)
        return
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--chat",
            chat,
            "--message",
            message,
        ],
        cwd=ROOT,
        check=False,
    )


def send_file(file_path: Path, chat: str, send_targets: Path) -> None:
    ok, reason = is_safe_outbound_file(file_path)
    if not ok:
        raise ValueError(f"Refusing outbound file {file_path}: {reason}")
    target = load_send_target(chat, send_targets)
    if target:
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": "", "targets": [target]}, handle, ensure_ascii=False)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
                    "--targets-file",
                    str(target_file),
                    "--prefer-current",
                    "--pause",
                    os.environ.get("WECHAT_WORKER_SEND_PAUSE", "0.35"),
                ],
                cwd=ROOT,
                check=True,
                timeout=60,
                env=wechat_send_env(),
            )
        finally:
            target_file.unlink(missing_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--chat",
            chat,
            "--file",
            str(file_path.expanduser().resolve()),
        ],
        cwd=ROOT,
        check=False,
        env=wechat_send_env(),
    )


def wechat_send_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WECHAT_INITIAL_TITLE_WAIT", os.environ.get("WECHAT_WORKER_INITIAL_TITLE_WAIT", "0.45"))
    env.setdefault("WECHAT_TITLE_RETRY_SECONDS", os.environ.get("WECHAT_WORKER_TITLE_RETRY_SECONDS", "3.2"))
    return env


def load_send_target(chat: str, path: Path) -> dict[str, Any] | None:
    direct_target = load_direct_config_send_target(chat)
    registry_target = None
    if not path.exists():
        return direct_target
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return direct_target
    raw = data.get(chat) if isinstance(data, dict) else None
    if isinstance(raw, dict):
        registry_target = raw
    if direct_target and registry_target:
        merged = {**registry_target, **direct_target}
        if not merged.get("fallback_clicks") and registry_target.get("fallback_clicks"):
            merged["fallback_clicks"] = registry_target["fallback_clicks"]
        return merged
    return direct_target or registry_target


def load_direct_config_send_target(chat: str) -> dict[str, Any] | None:
    for config_path in PRIVATE.glob("*direct-chatops.local.json"):
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("chat_name") or "") != chat:
            continue
        target = data.get("send_target")
        if isinstance(target, dict):
            return target
    return None


if __name__ == "__main__":
    raise SystemExit(main())
