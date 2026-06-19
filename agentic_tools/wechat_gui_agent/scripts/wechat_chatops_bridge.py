#!/usr/bin/env python3
"""Monitor a visible WeChat chat, mirror messages, and optionally reply with Codex."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from wechat_gui_send import find_wechat_window, focus, paste_text, run as run_gui
from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private" / "wechat_chatops_state.json"


@dataclass(frozen=True)
class CodexConfig:
    model: str = "gpt-5.5"
    reasoning_effort: str = "medium"
    sandbox: str = "read-only"
    workdir: Path = ROOT
    timeout_seconds: int = 180


@dataclass(frozen=True)
class ChatOpsConfig:
    chat_name: str
    display: str = ":97"
    poll_seconds: float = 8.0
    reply_enabled: bool = False
    respond_to_all: bool = False
    vision_digest: bool = True
    trigger_prefixes: tuple[str, ...] = (
        "@lachchen",
        "＠lachchen",
        "@陈喵瞄秒妙",
        "＠陈喵瞄秒妙",
        "@陈喵喵秒妙",
        "＠陈喵喵秒妙",
        "@codex",
        "codex:",
        "Codex:",
    )
    max_reply_chars: int = 1200
    ocr_lang: str = "chi_sim+chi_tra+eng"
    db_path: Path = DEFAULT_DB
    state_path: Path = DEFAULT_STATE
    output_dir: Path = ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F")
    codex: CodexConfig = CodexConfig()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="JSON config. Private configs should live under .private/.")
    parser.add_argument("--display", default=None)
    parser.add_argument("--chat", default=None)
    parser.add_argument("--once", action="store_true", help="Run one poll and exit.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--send", action="store_true", help="Send Codex replies back to the active chat.")
    parser.add_argument("--respond-to-all", action="store_true", help="Send OCR changes to Codex without requiring a trigger.")
    parser.add_argument("--message", help="Send this message to the current chat and record it, then exit.")
    parser.add_argument("--file", type=Path, help="Send a file/image to the current chat through the file picker, then exit.")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.display:
        config = replace_config(config, display=args.display)
    if args.chat:
        config = replace_config(config, chat_name=args.chat)
    if args.send:
        config = replace_config(config, reply_enabled=True)
    if args.respond_to_all:
        config = replace_config(config, respond_to_all=True)

    require_tools("xdotool", "xclip", "import", "convert", "tesseract", "codex")
    env = display_env(config.display)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.state_path.parent.mkdir(parents=True, exist_ok=True)

    window = find_wechat_window(env)
    if not window:
        raise SystemExit(f"No visible WeChat window found on DISPLAY={config.display}.")
    focus(env, window)

    if args.message:
        evidence = send_current_chat(env, window, args.message, config.output_dir, "manual-send")
        record_event(
            chat_name=config.chat_name,
            action="send",
            direction="outbound",
            message=args.message,
            status="sent",
            db_path=config.db_path,
            screenshot_path=str(evidence),
            metadata={"source": "wechat_chatops_bridge", "manual_message": True},
        )
        print(json.dumps({"status": "sent", "screenshot": str(evidence)}, ensure_ascii=False, indent=2))
        return 0
    if args.file:
        evidence = send_file_current_chat(env, window, args.file, config.output_dir, "manual-file")
        record_event(
            chat_name=config.chat_name,
            action="send_file",
            direction="outbound",
            message=str(args.file.resolve()),
            status="sent-file-clicked",
            db_path=config.db_path,
            screenshot_path=str(evidence),
            metadata={"source": "wechat_chatops_bridge", "path": str(args.file.resolve())},
        )
        print(json.dumps({"status": "sent-file-clicked", "screenshot": str(evidence)}, ensure_ascii=False, indent=2))
        return 0

    if not args.once and not args.loop:
        args.once = True

    state = load_state(config.state_path)
    while True:
        state = poll_once(config, env, state)
        save_state(config.state_path, state)
        if args.once:
            return 0
        time.sleep(config.poll_seconds)


def load_config(path: Path | None) -> ChatOpsConfig:
    if not path:
        return ChatOpsConfig(chat_name="wechat-chat")
    raw = json.loads(path.read_text(encoding="utf-8"))
    codex_raw = raw.get("codex", {})
    codex = CodexConfig(
        model=str(codex_raw.get("model", "gpt-5.5")),
        reasoning_effort=str(codex_raw.get("reasoning_effort", "medium")),
        sandbox=str(codex_raw.get("sandbox", "read-only")),
        workdir=Path(codex_raw.get("workdir", str(ROOT))),
        timeout_seconds=int(codex_raw.get("timeout_seconds", 180)),
    )
    return ChatOpsConfig(
        chat_name=str(raw.get("chat_name") or raw.get("chat") or "wechat-chat"),
        display=str(raw.get("display", ":97")),
        poll_seconds=float(raw.get("poll_seconds", 8.0)),
        reply_enabled=bool(raw.get("reply_enabled", False)),
        respond_to_all=bool(raw.get("respond_to_all", False)),
        vision_digest=bool(raw.get("vision_digest", True)),
        trigger_prefixes=tuple(
            raw.get(
                "trigger_prefixes",
                [
                    "@lachchen",
                    "＠lachchen",
                    "@陈喵瞄秒妙",
                    "＠陈喵瞄秒妙",
                    "@陈喵喵秒妙",
                    "＠陈喵喵秒妙",
                    "@codex",
                    "codex:",
                    "Codex:",
                ],
            )
        ),
        max_reply_chars=int(raw.get("max_reply_chars", 1200)),
        ocr_lang=str(raw.get("ocr_lang", "chi_sim+chi_tra+eng")),
        db_path=Path(raw.get("db_path", str(DEFAULT_DB))),
        state_path=Path(raw.get("state_path", str(DEFAULT_STATE))),
        output_dir=Path(raw.get("output_dir", str(ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F")))),
        codex=codex,
    )


def replace_config(config: ChatOpsConfig, **changes: Any) -> ChatOpsConfig:
    values = config.__dict__.copy()
    values.update(changes)
    return ChatOpsConfig(**values)


def poll_once(config: ChatOpsConfig, env: dict[str, str], state: dict[str, Any]) -> dict[str, Any]:
    window = find_wechat_window(env)
    if not window:
        raise SystemExit(f"No visible WeChat window found on DISPLAY={config.display}.")
    focus(env, window)
    stamp = datetime.now().strftime("%H%M%S")
    run_dir = config.output_dir / f"{stamp}-chatops"
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshot = run_dir / "chat.png"
    run_gui(["import", "-window", "root", str(screenshot)], env=env, check=False)
    ocr_image = preprocess_chat_crop(screenshot, run_dir / "chat-ocr.png", window)
    ocr_text = run_ocr(ocr_image, config.ocr_lang)
    text_hash = sha256_text(ocr_text)
    previous_hash = state.get("last_ocr_hash")
    previous_ocr = str(state.get("last_ocr_text") or "")

    if text_hash == previous_hash:
        print(json.dumps({"status": "unchanged", "hash": text_hash, "screenshot": str(screenshot)}, ensure_ascii=False))
        return state

    event_id = record_event(
        chat_name=config.chat_name,
        action="read",
        direction="inbound",
        status="captured-changed",
        db_path=config.db_path,
        screenshot_path=str(screenshot),
        ocr_text=ocr_text,
        metadata={
            "source": "wechat_chatops_bridge",
            "hash": text_hash,
            "previous_hash": previous_hash,
            "ocr_image": str(ocr_image),
            "reply_enabled": config.reply_enabled,
            "respond_to_all": config.respond_to_all,
            "vision_digest": config.vision_digest,
        },
    )
    state["last_ocr_hash"] = text_hash
    state["last_ocr_text"] = ocr_text
    state["last_read_event_id"] = event_id
    state["last_seen_at"] = datetime.now().isoformat(timespec="seconds")

    should_reply, trigger_text = should_process(ocr_text, state, config)
    image_digest = False
    if not should_reply and config.vision_digest:
        should_reply = True
        image_digest = True
        trigger_text = ""
    if not should_reply:
        print(json.dumps({"status": "captured", "reply": "skipped", "event_id": event_id}, ensure_ascii=False))
        state["previous_ocr_text"] = previous_ocr
        return state

    response = run_codex(
        config,
        previous_ocr=previous_ocr,
        current_ocr=ocr_text,
        trigger_text=trigger_text,
        screenshot=ocr_image if image_digest else None,
        image_digest=image_digest,
    )
    response = clean_response(response, config.max_reply_chars)
    state["last_codex_response"] = response
    state["last_codex_at"] = datetime.now().isoformat(timespec="seconds")
    if not response or response == "NO_REPLY":
        record_event(
            chat_name=config.chat_name,
            action="codex_reply",
            direction="outbound",
            message=response or "NO_REPLY",
            status="no-reply",
            db_path=config.db_path,
            screenshot_path=str(screenshot),
            metadata={"source_event_id": event_id},
        )
        print(json.dumps({"status": "codex-no-reply", "event_id": event_id}, ensure_ascii=False))
        state["previous_ocr_text"] = previous_ocr
        return state

    if config.reply_enabled:
        sent_path = send_current_chat(env, window, response, run_dir, "codex-reply")
        status = "sent"
        screenshot_path = sent_path
    else:
        status = "dry-run-response"
        screenshot_path = screenshot
    record_event(
        chat_name=config.chat_name,
        action="codex_reply",
        direction="outbound",
        message=response,
        status=status,
        db_path=config.db_path,
        screenshot_path=str(screenshot_path),
        metadata={"source_event_id": event_id, "reply_enabled": config.reply_enabled},
    )
    state["last_sent_response"] = response if config.reply_enabled else ""
    state["previous_ocr_text"] = previous_ocr
    print(json.dumps({"status": status, "event_id": event_id, "response": response}, ensure_ascii=False, indent=2))
    return state


def should_process(ocr_text: str, state: dict[str, Any], config: ChatOpsConfig) -> tuple[bool, str]:
    if not ocr_text.strip():
        return False, ""
    last_sent = str(state.get("last_sent_response") or "")
    if last_sent and last_sent[:160] in ocr_text:
        return False, ""
    for prefix in config.trigger_prefixes:
        index = ocr_text.rfind(prefix)
        if index >= 0:
            return True, ocr_text[index + len(prefix) :].strip()
    if config.respond_to_all:
        return True, ocr_text.strip()
    return False, ""


def run_codex(
    config: ChatOpsConfig,
    *,
    previous_ocr: str,
    current_ocr: str,
    trigger_text: str,
    screenshot: Path | None,
    image_digest: bool,
) -> str:
    prompt = f"""You are LabCanvas Codex replying inside a small WeChat group.
Use the OCR transcript to infer the latest user request. Reply with a concise chat message.
Only reply if the latest visible group message mentions @lachchen, ＠lachchen, the account's visible group name, @codex, or clearly asks this account/Codex to respond.
If there is no real new request for this account, reply exactly: NO_REPLY
Do not mention screenshots or OCR. Do not include markdown tables.
Image digest enabled: {image_digest}

Previous OCR:
{previous_ocr[-3000:]}

Current OCR:
{current_ocr[-5000:]}

Triggered text:
{trigger_text[-3000:]}
"""
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as out:
        output_path = Path(out.name)
    command = [
        "codex",
        "exec",
        "-m",
        config.codex.model,
        "-c",
        f'model_reasoning_effort="{config.codex.reasoning_effort}"',
        "--sandbox",
        config.codex.sandbox,
        "-C",
        str(config.codex.workdir),
        "-o",
        str(output_path),
    ]
    if screenshot:
        command.extend(["-i", str(screenshot)])
    command.append(prompt)
    proc = subprocess.run(command, capture_output=True, text=True, timeout=config.codex.timeout_seconds, check=False)
    if proc.returncode != 0:
        return f"Codex bridge error: {proc.stderr.strip()[:500] or proc.stdout.strip()[:500]}"
    response = output_path.read_text(encoding="utf-8", errors="replace").strip()
    output_path.unlink(missing_ok=True)
    return response


def clean_response(response: str, max_chars: int) -> str:
    text = response.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`").strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20].rstrip() + "\n...[truncated]"
    return text


def send_current_chat(env: dict[str, str], window: Any, message: str, output_dir: Path, prefix: str) -> Path:
    focus(env, window)
    run_gui(
        [
            "xdotool",
            "mousemove",
            str(window.x + int(window.width * 0.66)),
            str(window.y + window.height - 90),
            "click",
            "1",
        ],
        env=env,
    )
    time.sleep(0.4)
    paste_text(env, message)
    time.sleep(0.4)
    composed = output_dir / f"{prefix}-composed.png"
    run_gui(["import", "-window", "root", str(composed)], env=env, check=False)
    run_gui(["xdotool", "key", "Return"], env=env)
    time.sleep(1.0)
    sent = output_dir / f"{prefix}-sent.png"
    run_gui(["import", "-window", "root", str(sent)], env=env, check=False)
    return sent


def send_file_current_chat(env: dict[str, str], window: Any, file_path: Path, output_dir: Path, prefix: str) -> Path:
    path = file_path.resolve()
    if not path.exists():
        raise SystemExit(f"File does not exist: {path}")
    focus(env, window)
    # Native WeChat Linux exposes a folder icon in the composer toolbar. This
    # opens a GTK/Qt file chooser where Ctrl+L accepts an absolute path.
    run_gui(
        [
            "xdotool",
            "mousemove",
            str(window.x + int(window.width * 0.47)),
            str(window.y + window.height - 132),
            "click",
            "1",
        ],
        env=env,
    )
    time.sleep(1.0)
    paste_path_into_file_chooser(env, path)
    time.sleep(1.0)
    selected = output_dir / f"{prefix}-selected.png"
    run_gui(["import", "-window", "root", str(selected)], env=env, check=False)
    run_gui(["xdotool", "key", "Return"], env=env, check=False)
    time.sleep(1.2)
    sent = output_dir / f"{prefix}-sent.png"
    run_gui(["import", "-window", "root", str(sent)], env=env, check=False)
    return sent


def preprocess_chat_crop(screenshot: Path, output_path: Path, window: Any) -> Path:
    crop_x = window.x + int(window.width * 0.36)
    crop_y = window.y + 62
    crop_w = max(200, int(window.width * 0.64))
    crop_h = max(200, window.height - 190)
    crop = f"{crop_w}x{crop_h}+{crop_x}+{crop_y}"
    proc = subprocess.run(
        [
            "convert",
            str(screenshot),
            "-crop",
            crop,
            "-resize",
            "220%",
            "-colorspace",
            "Gray",
            "-contrast-stretch",
            "2%x2%",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return screenshot
    return output_path


def paste_path_into_file_chooser(env: dict[str, str], path: Path) -> None:
    # Ctrl+L works in GTK file choosers; direct paste still leaves the visible
    # filename for operator review when a different dialog backend is used.
    run_gui(["xdotool", "key", "ctrl+l"], env=env, check=False)
    time.sleep(0.2)
    paste_text(env, str(path))
    time.sleep(0.2)
    run_gui(["xdotool", "key", "Return"], env=env, check=False)


def run_ocr(image_path: Path, lang: str) -> str:
    proc = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", lang],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def display_env(display: str) -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    return env


def require_tools(*names: str) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"Missing required tool(s): {', '.join(missing)}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
