#!/usr/bin/env python3
"""Run EchoMind's independent three-hour language-learning schedule."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
if str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"))

import wechat_direct_chatops as direct  # noqa: E402
from wechat_agent_backend import run_agent_session  # noqa: E402

CONFIG = PRIVATE / "echomind-direct-chatops.local.json"
STATE = PRIVATE / "echomind-language-schedule.state.json"
INTERVAL = 3 * 60 * 60


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_row() -> dict:
    now = int(time.time())
    return {
        "local_id": 0,
        "server_id": f"scheduled-echomind-{now}",
        "sender": "echomind-language-scheduler",
        "sender_display": "EchoMind language scheduler",
        "sender_userid": "echomind-language-scheduler",
        "is_self": False,
        "is_bot": False,
        "kind": "text",
        "text": (
            "@LazyingArt 请根据 EchoMind 最近的完整聊天上下文，上一节实用的中文、日文、英文语言学习小课。"
            "选择一个群里真实出现过、或最适合当前学习方向的表达；不要重复最近课程。"
            "完整给出自然改写、中文含义、英文表达、日文表达、日文假名、发音提示、语法重点、"
            "常见误用和一个简短练习。像正常朋友聊天，内容有实质，不要机械模板。"
        ),
        "content": "",
        "create_time": now,
    }


def run_once() -> dict:
    config = direct.load_config(CONFIG)
    context = direct.read_recent_history(config, 10**18, limit=int(config.get("history_limit", 24)))
    history = "\n".join(f"{item.get('sender_display', 'member')}: {direct.visible_message_text(item)}" for item in context[-24:])
    prompt = f"""You are EchoMind, a patient language teacher. This is an internal scheduled lesson, not a status check.
Use the group's recent history below to choose one useful, non-repeated Chinese/Japanese/English lesson.
Analyze a real expression from the history when possible. Include natural wording, meaning, English, Japanese, furigana, pronunciation, grammar, common mistake, and one short exercise. Be concise but substantive and write like a helpful friend. Do not say NO_REPLY.

Recent EchoMind history:
{history}
"""
    result = run_agent_session(
        prompt,
        backend="codex",
        chat_name="EchoMind",
        role="scheduled_language_teacher",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        sandbox="read-only",
        timeout_seconds=900,
        reuse=True,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    message = str(result.get("message") or "").strip()
    if not message:
        raise RuntimeError("EchoMind language teacher returned no lesson")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = load_state()
    state.update({"last_run_at": now, "last_message": message, "interval_seconds": INTERVAL, "last_agent": result.get("backend", "codex")})
    save_state(state)
    return {"ok": True, "chat": config["chat_name"], "sent_at": now, "message": message, "internal": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run immediately once.")
    parser.add_argument("--loop", action="store_true", help="Run immediately, then every three hours.")
    parser.add_argument("--interval-seconds", type=int, default=INTERVAL)
    args = parser.parse_args()
    interval = max(300, args.interval_seconds)
    if not args.once and not args.loop:
        parser.error("use --once or --loop")
    while True:
        try:
            print(json.dumps(run_once(), ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
