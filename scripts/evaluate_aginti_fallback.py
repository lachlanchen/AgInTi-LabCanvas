#!/usr/bin/env python3
"""Opt-in DeepSeek acceptance through the real LabCanvas adapters; no chat sends."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agentic_tools/wechat_gui_agent/scripts"))

from agenticapp.scene_spec import built_in_scene_template, load_scene_spec
from agenticapp.workspace_agent import build_agent_prompt, run_aginti_turn


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_memo(workspace: Path, body: str) -> Path:
    tex = workspace / "daily-memo.tex"
    tex.write_text(
        "\\documentclass[11pt]{article}\n\\usepackage[a4paper,margin=24mm]{geometry}\n"
        "\\usepackage{fontspec}\n\\usepackage{xeCJK}\n\\setmainfont{TeX Gyre Termes}\n"
        "\\setCJKmainfont{Noto Serif CJK SC}\n"
        "\\setlength{\\parindent}{0pt}\n\\setlength{\\parskip}{6pt}\n"
        "\\begin{document}\n" + body + "\n\\end{document}\n"
    )
    proc = subprocess.run(
        ["xelatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", tex.name],
        cwd=workspace, capture_output=True, text=True, timeout=60,
    )
    (workspace / "compile.log").write_text(proc.stdout + proc.stderr)
    require(proc.returncode == 0, "Host could not compile the generated memo body")
    require("Overfull \\hbox" not in proc.stdout, "Memo has clipped/overflowing text")
    subprocess.run(["pdftoppm", "-scale-to", "1300", "-png", "-singlefile", "daily-memo.pdf", "preview"],
                   cwd=workspace, check=True, capture_output=True, timeout=30)
    return tex.with_suffix(".pdf")


def session_evidence(workspace: Path, session_id: str) -> dict:
    pointer = json.loads(
        (workspace / ".aginti-sessions" / session_id / "session.json").read_text()
    )
    state = json.loads((Path(pointer["sessionDir"]) / "state.json").read_text())
    tools = [
        call.get("function", {}).get("name", "")
        for message in state.get("messages", [])
        for call in message.get("tool_calls", [])
    ]
    require(state.get("provider") == "deepseek", "Executor was not DeepSeek")
    require(not any("wrapper" in name for name in tools), "External wrapper was invoked")
    writes = []
    for message in state.get("messages", []):
        for call in message.get("tool_calls", []):
            function = call.get("function", {})
            if function.get("name") in {"write_file", "apply_patch"}:
                writes.append(json.loads(function.get("arguments") or "{}").get("path", ""))
    return {"provider": state.get("provider"), "model": state.get("model"), "tools": tools, "file_writes": writes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize metered DeepSeek calls")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--command", default="aginti", help="Installed CLI or candidate CLI path")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if not args.live:
        parser.error("No inference performed: pass --live to run the isolated acceptance suite")

    backend = importlib.import_module("wechat_agent_backend")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "output/aginti-fallback-acceptance" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True, mode=0o700)
    config = {
        "command": args.command,
        "provider_chain": ["deepseek"], "provider_models": {"deepseek": args.model},
        "permission_mode": "normal",
    }
    report = {"ok": False, "cases": [], "output": str(output)}

    def check(name, callback):
        start = time.monotonic()
        try:
            detail = callback()
            row = {"name": name, "ok": True, **detail}
        except Exception as exc:
            row = {"name": name, "ok": False, "error": str(exc)}
        row["seconds"] = round(time.monotonic() - start, 2)
        report["cases"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def chat_turn(workspace, prompt, role, chat="acceptance-chat"):
        result = backend.run_aginti_session(
            prompt, chat_name=chat, role=role, model="provider-default", reasoning_effort="low",
            sandbox="read-only" if backend.is_response_only_agent_role(role) else "workspace-write",
            timeout_seconds=args.timeout, workdir=workspace,
            backend_config={**config, "evidence_scope_artifact_root": str(workspace / "artifacts")},
        )
        (workspace / f"turn-{uuid.uuid4().hex[:8]}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        require(result.get("ok"), str(result.get("reason") or result.get("stderr_tail") or "Turn failed"))
        return result

    def grouped_chat():
        workspace = output / "grouped-chat"
        workspace.mkdir()
        result = chat_turn(workspace, """
Read all these consecutive same-chat messages together:
1. Lin sent Paris.mp4 without any publication command.
2. Zhang quoted that video: 法语中 baguette 的发音说错了。
3. Lin: 先更正法语表达，不要发布。这个视频保留英语、日语、中文、法语字幕。
4. Lin: 请简短说一下你会怎么处理，不要重复回复每一条。
Return one strict JSON object with message (natural Chinese), files (empty list),
and intent {source (exact filename), publish, languages}. This is a reasoning-only test: no external action.
No audio or video has been supplied here; do not invent the specific pronunciation error or extra audio tracks.
""", "fast", "acceptance-grouped")
        value = result_payload(result)
        require(value["files"] == [], "Chat unexpectedly returned files")
        require(value["intent"]["publish"] is False, "Passive video authorized publication")
        require(value["intent"]["source"] == "Paris.mp4", "Quote/source identity was lost")
        require(len(value["intent"]["languages"]) == 4, "An earlier language requirement was lost")
        require(10 < len(value["message"]) < 350, "Chat reply was empty or verbose")
        return {"reply": value["message"], **session_evidence(workspace, result["thread_id"])}

    def daily_memo():
        workspace = output / "daily-memo"
        workspace.mkdir()
        result = chat_turn(workspace, r"""
Produce a concise Chinese daily memo as LaTeX body only, with no document preamble or fences.
Earlier same-chat facts: the optical prototype's C port must retain its original chamfer;
the next print only changes the female pilot to 29.8 mm. Never edit the original STEP.
Today's messages: prepare a new run and a print-ready STL/STEP/3MF set, sync to Nutstore;
the business task is a factual comparison of two customer segments, not an invented revenue forecast.
No manufacturing order or public publication is authorized. Do not ask again about settled choices.
Synthesize both tasks and give their concrete next actions. Use two short sections, at most 350 Chinese characters.
The host will compile and deliver the PDF later. Do not claim files were created or delivered.
""", "daily-organizer", "acceptance-memo")
        body = result["message"]
        require("29.8" in body and "3MF" in body.upper(), "Memo omitted engineering requirements")
        require("客户" in body and ("倒角" in body or "chamfer" in body), "Memo ignored earlier context")
        require("\\documentclass" not in body and "```" not in body, "Memo violated host-owned compilation")
        return {"pdf": str(compile_memo(workspace, body)), **session_evidence(workspace, result["thread_id"])}

    def routine_worker():
        workspace = output / "routine-worker"
        workspace.mkdir()
        (workspace / "artifacts").mkdir()
        source = workspace / "requirements.txt"
        source.write_text("The optical scene is a dry-run only. Do not render or publish anything.\n")
        shutil.copytree(ROOT / "src/agenticapp", workspace / "src/agenticapp", ignore=shutil.ignore_patterns("__pycache__"))
        (workspace / "AGENTS.md").write_text(
            "LabCanvas CLI is available here as `python -m agenticapp` with PYTHONPATH=src.\n"
            "Use its existing routines; src/ is a read-only tool fixture. Do not install packages or publish.\n"
        )
        original = digest(source)
        fixture_hashes = {path: digest(path) for path in (workspace / "src").rglob("*.py")}
        first = chat_turn(workspace, """
Use the existing LabCanvas `scene-template experiment-setup` routine to create
artifacts/fallback-bench.scene.json with title 'Fallback optical bench', slug 'fallback-optical-bench',
and render resolution 1280x720. Validate it with the existing `render-scene --dry-run` command.
Do not rewrite the CLI or run Blender. requirements.txt is a read-only input.
Return one strict JSON object with message and files containing the created scene path.
""", "worker", "acceptance-routine")
        scene = workspace / "artifacts/fallback-bench.scene.json"
        spec = load_scene_spec(scene)
        template = built_in_scene_template("experiment-setup")
        require(spec["render"]["width"] == 1280 and spec["render"]["height"] == 720, "Initial resolution incorrect")
        require(spec["elements"][:-1] == template["elements"][:-1], "Existing routine geometry was rewritten")
        require(scene.name in result_files(first), "Worker did not return the real artifact")
        second = chat_turn(workspace, """
Update only artifacts/fallback-bench.scene.json render resolution to 960x540. Keep its title, slug, optics,
and read-only requirements unchanged. Revalidate using the existing dry-run routine.
Return one strict JSON object with message and files. No rendering or publication.
""", "worker", "acceptance-routine")
        updated = load_scene_spec(scene)
        require(updated["render"]["width"] == 960 and updated["render"]["height"] == 540, "Follow-up was lost")
        require(updated["elements"] == spec["elements"] and updated["title"] == spec["title"], "Resume changed unrelated geometry")
        require(first["thread_id"] == second["thread_id"] and second["resumed"], "Worker did not resume")
        require(digest(source) == original, "Read-only source changed")
        require(all(path.exists() and digest(path) == before for path, before in fixture_hashes.items()),
                "Existing CLI implementation changed")
        evidence = session_evidence(workspace, second["thread_id"])
        require(evidence["tools"], "Worker claimed completion without tool evidence")
        require(not any(Path(path).name == source.name or "src" in Path(path).parts for path in evidence["file_writes"]),
                "Worker attempted to edit a read-only input or tool fixture")
        return {"scene": str(scene), **evidence}

    def studio_resume():
        workspace = output / "studio-resume"
        workspace.mkdir()
        storage = workspace / "host-state"
        storage.mkdir()
        (storage / "settings.json").write_text(json.dumps({"aginti": config}))
        note = workspace / "notes.txt"
        note.write_text("The Paris clip needs EN/JP/ZH/FR subtitles, French at the bottom. No re-publication.\n")
        risk = workspace / "risks.txt"
        risk.write_text("The previous login needed QR confirmation. No payment is authorized.\n")
        hashes = [digest(note), digest(risk)]
        task_dir = workspace / "artifacts"
        task_dir.mkdir()
        (workspace / "AGENTS.md").write_text(
            "Read the named inputs without editing them. Put only requested deliverables in artifacts/.\n"
        )

        def turn(prompt):
            policy = {"timeout_seconds": args.timeout, "mode": "execute", "backend": "aginti",
                      "model": "provider-default", "reasoning_effort": "low"}
            packet = build_agent_prompt(prompt, root=workspace, task_dir=task_dir, policy=policy,
                                        conversation_id="acceptance-studio")
            result = run_aginti_turn(
                packet, policy=policy,
                conversation_id="acceptance-studio", task_dir=task_dir,
                storage_dir=storage, root=workspace, pid_callback=None,
            )
            require(result.get("ok"), str(result.get("reason") or result.get("stderr_tail")))
            return result

        first = turn("Read notes.txt and risks.txt. Create artifacts/fallback-summary.md with a short summary and next safe step. Leave both inputs untouched. Do not publish or pay.")
        second = turn("Login is now confirmed; the old QR blocker is resolved. Update artifacts/fallback-summary.md in Chinese, keep the four-language requirement and no re-publication. Leave notes.txt and risks.txt untouched.")
        summary = (task_dir / "fallback-summary.md").read_text()
        require("法语" in summary and ("底" in summary or "最下" in summary), "Studio lost subtitle context")
        require(first["thread_id"] == second["thread_id"], "Studio did not resume")
        require([digest(note), digest(risk)] == hashes, "Studio edited read-only inputs")
        require(not (task_dir / note.name).exists() and not (task_dir / risk.name).exists(),
                "Studio fabricated unnecessary input-copy deliverables")
        evidence = session_evidence(workspace, second["thread_id"])
        require(not any(Path(path).name in {note.name, risk.name} for path in evidence["file_writes"]),
                "Studio temporarily edited an input before restoring it")
        return {"summary": summary, **evidence}

    with ExitStack() as stack:
        stack.enter_context(patch.object(backend, "AGINTI_SESSION_DIR", output / "chat-registry"))
        stack.enter_context(patch.object(backend, "AGINTI_REGISTRY", output / "chat-registry/sessions.json"))
        stack.enter_context(patch.dict(os.environ, {
            "LABCANVAS_AGINTI_PROVIDER_CHAIN": "deepseek", "WECHAT_AGINTI_PROVIDER_CHAIN": "deepseek",
            "PYTHONPATH": "src", "WECHAT_AGINTI_REUSE_SESSIONS": "1",
        }))
        for name, callback in (
            ("grouped-chat-and-quote", grouped_chat), ("daily-memo-pdf", daily_memo),
            ("routine-worker-and-resume", routine_worker), ("studio-and-resume", studio_resume),
        ):
            check(name, callback)
    report["ok"] = all(row["ok"] for row in report["cases"])
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Evidence: {output / 'report.json'}", flush=True)
    return 0 if report["ok"] else 1


def result_files(result: dict) -> set[str]:
    return {Path(path).name for path in result_payload(result)["files"]}


def result_payload(result: dict) -> dict:
    backend = importlib.import_module("wechat_agent_backend")
    payload = backend.extract_aginti_json_object(result["message"])
    require(payload is not None, "Agent returned no usable JSON payload")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
