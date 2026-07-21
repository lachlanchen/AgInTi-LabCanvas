#!/usr/bin/env python3
"""Run EchoMind's independent language-learning schedule and deliver lessons."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
if str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"))

import wechat_direct_chatops as direct  # noqa: E402
from wechat_agent_backend import run_agent_session  # noqa: E402

CONFIG = PRIVATE / "echomind-direct-chatops.local.json"
STATE = PRIVATE / "echomind-language-schedule.state.json"
INTERVAL = 60 * 60
LOCAL_TZ = ZoneInfo("Asia/Hong_Kong")
QUIET_START = 20
QUIET_END = 6
TOPICS = (
    "food, cooking, and ordering at a restaurant",
    "clothes, shopping, sizes, and prices",
    "hotels, reservations, and travel arrangements",
    "directions, public transport, and commuting",
    "school, study, and asking for clarification",
    "work, meetings, deadlines, and polite requests",
    "home life, chores, and daily routines",
    "weather, seasons, and outdoor plans",
    "health, appointments, and describing symptoms",
    "social plans, invitations, and making arrangements",
    "feelings, opinions, and supportive conversation",
    "pronunciation, listening, and a useful sound contrast",
    "grammar in practical conversation",
    "writing a clear short message or email",
    "politeness, register, and cultural nuance",
)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def quiet_seconds() -> float:
    """Return remaining quiet-hours time, or zero during allowed hours."""
    now = datetime.now(LOCAL_TZ)
    if QUIET_END <= now.hour < QUIET_START:
        return 0.0
    wake = (now + timedelta(days=1)).replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
    return max(60.0, (wake - now).total_seconds())


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
            "主题可以广泛选择：日常交流、工作、研究、写作、旅行、文化、情绪表达、发音、语法，"
            "以及群成员反复出现的错误。选择一个群里真实出现过、或最适合当前学习方向的表达；不要重复最近课程。"
            "完整给出自然改写、中文含义、英文表达、日文表达、日文假名、发音提示、语法重点、"
            "常见误用和一个简短练习。像正常朋友聊天，内容有实质，不要机械模板。"
        ),
        "content": "",
        "create_time": now,
    }


def run_once(*, deliver: bool = True) -> dict:
    config = direct.load_config(CONFIG)
    context = direct.read_recent_history(config, 10**18, limit=int(config.get("history_limit", 24)))
    history = "\n".join(f"{item.get('sender_display', 'member')}: {direct.visible_message_text(item)}" for item in context[-24:])
    state = load_state()
    topic_index = int(state.get("topic_index", 0)) % len(TOPICS)
    topic = TOPICS[topic_index]
    previous = state.get("last_message", "")
    prompt = f"""You are EchoMind, a patient language teacher. This is an internal scheduled lesson, not a status check.
Today's required domain is: **{topic}**. Teach a broad, practical lesson in this domain rather than reacting to the group chat. Do not switch back to the previous domain merely because it appears in the history.

The recent chat is only a weak personalization signal. Use at most one short example from it when helpful; otherwise ignore it. Do not summarize the chat, make its latest message the topic, or keep dwelling on one recurring subject. Avoid repeating the previous lesson and vary the everyday domain from recent lessons.

Give a complete Chinese/Japanese/English mini-lesson: natural example, meaning, Japanese kana/furigana, pronunciation guidance, grammar or usage point, one common mistake, and one short exercise. Be concise but substantive and write like a helpful friend. Do not say NO_REPLY.

Recent EchoMind history:
{history}

Previous scheduled lesson (avoid repeating its topic):
{previous}
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
    delivery: dict[str, object] = {"requested": deliver, "status": "internal_only"}
    if deliver:
        screenshot = direct.send_gui_message(config, message)
        if not screenshot or not Path(screenshot).is_file():
            raise RuntimeError(f"EchoMind lesson send was not verified: {screenshot or 'no screenshot'}")
        delivery = {"requested": True, "status": "sent_verified", "screenshot": screenshot}
    state.update({
        "last_run_at": now,
        "last_message": message,
        "interval_seconds": INTERVAL,
        "last_agent": result.get("backend", "codex"),
        "last_delivery": delivery,
        "topic": topic,
        "topic_index": (topic_index + 1) % len(TOPICS),
    })
    save_state(state)
    return {"ok": True, "chat": config["chat_name"], "sent_at": now, "message": message, "delivery": delivery}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run immediately once.")
    parser.add_argument("--loop", action="store_true", help="Run immediately, then every hour.")
    parser.add_argument("--no-send", action="store_true", help="Keep the lesson internal instead of sending it to EchoMind.")
    parser.add_argument("--interval-seconds", type=int, default=INTERVAL)
    args = parser.parse_args()
    interval = max(300, args.interval_seconds)
    if not args.once and not args.loop:
        parser.error("use --once or --loop")
    while True:
        quiet = quiet_seconds()
        if quiet:
            print(json.dumps({"ok": True, "status": "quiet_hours", "resume_in_seconds": int(quiet)}, ensure_ascii=False), flush=True)
            if not args.loop:
                return 0
            time.sleep(quiet)
            continue
        try:
            print(json.dumps(run_once(deliver=not args.no_send), ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
