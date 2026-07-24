#!/usr/bin/env python3
"""Control the visible LabCanvas Studio chat through a dedicated Chrome CDP session."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


TERMINAL_STATUSES = {"completed", "failed", "canceled", "waiting_confirmation"}


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-") or "evidence"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drive LabCanvas through its visible Studio controls and monitor exact agent tasks."
    )
    parser.add_argument("command", choices=("open", "status", "screenshot", "reload", "chat", "monitor"))
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9444")
    parser.add_argument("--app-url", default="http://127.0.0.1:19474")
    parser.add_argument("--evidence-dir", default="output/webapp/browser-evidence")
    parser.add_argument("--label", default="manual")
    parser.add_argument("--message")
    parser.add_argument("--message-file")
    parser.add_argument("--model", choices=("auto", "gpt-5.6-sol", "gpt-5.5"), default="auto")
    parser.add_argument("--effort", choices=("auto", "low", "medium"), default="auto")
    parser.add_argument("--mode", choices=("execute", "plan"), default="execute")
    parser.add_argument("--task-id")
    parser.add_argument("--wait-seconds", type=float, default=10800.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--no-wait", action="store_true")
    return parser.parse_args(argv)


def message_from_args(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).expanduser().read_text(encoding="utf-8").strip()
    return str(args.message or "").strip()


def connect_page(playwright: Any, cdp_url: str, app_url: str) -> tuple[Any, Any]:
    browser = playwright.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError(f"Chrome at {cdp_url} has no browser context")
    context = browser.contexts[0]
    origin = app_url.rstrip("/")
    matches = [page for page in context.pages if page.url.startswith(origin)]
    page = matches[0] if matches else next((item for item in context.pages if item.url == "about:blank"), None)
    if page is None:
        page = context.new_page()
    for duplicate in matches[1:]:
        duplicate.close()
    if not page.url.startswith(origin):
        page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
    page.bring_to_front()
    page.get_by_test_id("labcanvas-app").wait_for(state="visible", timeout=60_000)
    return browser, page


def save_screenshot(page: Any, evidence_dir: Path, label: str) -> str:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{timestamp()}-{safe_name(label)}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path.resolve())


def page_status(page: Any) -> dict[str, Any]:
    root = page.get_by_test_id("labcanvas-app")
    assistant = page.get_by_test_id("chat-message-assistant")
    artifacts = page.get_by_test_id("artifact-item")
    return {
        "url": page.url,
        "title": page.title(),
        "agent_status": root.get_attribute("data-agent-status") or "unknown",
        "active_task_id": root.get_attribute("data-active-task-id") or "",
        "last_task_id": root.get_attribute("data-last-task-id") or "",
        "last_task_status": root.get_attribute("data-last-task-status") or "",
        "status_text": page.get_by_test_id("agent-status").inner_text().strip(),
        "user_messages": page.get_by_test_id("chat-message-user").count(),
        "assistant_messages": assistant.count(),
        "last_assistant": assistant.last.inner_text().strip() if assistant.count() else "",
        "artifact_count": artifacts.count(),
        "selected_artifact": {
            "title": page.get_by_test_id("artifact-title").inner_text().strip(),
            "path": page.get_by_test_id("artifact-path").inner_text().strip(),
        },
    }


def read_task(page: Any, task_id: str) -> dict[str, Any]:
    return page.evaluate(
        """async (taskId) => {
          const response = await fetch(`/api/agent/tasks/${encodeURIComponent(taskId)}`);
          if (!response.ok) return {ok: false, error: `HTTP ${response.status}`};
          return await response.json();
        }""",
        task_id,
    )


def monitor_task(page: Any, task_id: str, *, wait_seconds: float, poll_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + max(1.0, wait_seconds)
    history: list[dict[str, str]] = []
    previous = ""
    final_task: dict[str, Any] = {}
    while time.monotonic() < deadline:
        visible = page_status(page)
        visible_status = visible["last_task_status"] if visible["last_task_id"] == task_id else ""
        task_payload = read_task(page, task_id)
        task = task_payload.get("task") if isinstance(task_payload, dict) else None
        if isinstance(task, dict):
            final_task = task
        api_status = str(final_task.get("status") or "")
        status = api_status or visible_status or "unknown"
        if status != previous:
            history.append({"at": timestamp(), "status": status or "unknown", "ui": visible["status_text"]})
            previous = status
        if api_status in TERMINAL_STATUSES:
            return {"task_id": task_id, "status": status, "history": history, "task": final_task, "ui": page_status(page)}
        time.sleep(max(0.2, poll_seconds))
    raise TimeoutError(f"Task {task_id} did not reach a terminal state within {wait_seconds:g} seconds")


def submit_chat(page: Any, args: argparse.Namespace) -> dict[str, Any]:
    message = message_from_args(args)
    if not message:
        raise ValueError("chat requires --message or --message-file")
    page.get_by_test_id("agent-model").select_option(args.model)
    page.get_by_test_id("agent-effort").select_option(args.effort)
    page.get_by_test_id("agent-mode").select_option(args.mode)
    page.get_by_test_id("chat-input").fill(message)
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/agent/chat"),
        timeout=60_000,
    ) as response_info:
        page.get_by_test_id("chat-send").click()
    payload = response_info.value.json()
    if not payload.get("ok") or not isinstance(payload.get("task"), dict):
        raise RuntimeError(str(payload.get("error") or "Studio did not create an agent task"))
    task_id = str(payload["task"].get("id") or "")
    if not task_id:
        raise RuntimeError("Studio created a task without an ID")
    page.wait_for_function(
        "taskId => document.querySelector('[data-testid=labcanvas-app]')?.dataset.lastTaskId === taskId",
        arg=task_id,
        timeout=30_000,
    )
    result: dict[str, Any] = {"submitted": True, "task_id": task_id, "policy": payload["task"].get("policy", {})}
    if not args.no_wait:
        result["monitor"] = monitor_task(
            page,
            task_id,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    evidence_dir = Path(args.evidence_dir).expanduser()
    page = None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            _browser, page = connect_page(playwright, args.cdp_url, args.app_url)
            before = save_screenshot(page, evidence_dir, f"{args.command}-before")
            if args.command in {"open", "status"}:
                result: dict[str, Any] = page_status(page)
            elif args.command == "screenshot":
                result = {"screenshot": save_screenshot(page, evidence_dir, args.label), "status": page_status(page)}
            elif args.command == "reload":
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.get_by_test_id("labcanvas-app").wait_for(state="visible", timeout=60_000)
                result = page_status(page)
            elif args.command == "chat":
                result = submit_chat(page, args)
            else:
                task_id = str(args.task_id or page_status(page)["last_task_id"])
                if not task_id:
                    raise ValueError("monitor requires --task-id when the Studio has no last task")
                result = monitor_task(page, task_id, wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds)
            after = save_screenshot(page, evidence_dir, f"{args.command}-after")
            print(json.dumps({"ok": True, "command": args.command, "evidence": [before, after], "result": result}, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - browser evidence must survive any controller failure.
        failure = None
        if page is not None:
            try:
                failure = save_screenshot(page, evidence_dir, f"{args.command}-failed")
            except Exception:
                failure = None
        print(json.dumps({"ok": False, "command": args.command, "error": str(exc), "evidence": failure}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
