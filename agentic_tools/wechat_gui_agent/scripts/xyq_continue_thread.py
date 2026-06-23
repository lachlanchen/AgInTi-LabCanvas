#!/usr/bin/env python3
"""Continue a Xiaoyunque thread that is waiting for user confirmation.

The helper is deliberately narrow: it attaches to the exact thread/page, checks
that the current visible thread is asking for continuation, fills the bottom
composer with a short approval, clicks the enabled send button, and returns
monitor state for the queue. It does not create a new task or switch threads.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import websocket


DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_DOTENV = Path("/home/lachlan/ProjectsLFS/LALACHAN/.env")
DEFAULT_XYQ_SKILL_SCRIPTS = Path("/home/lachlan/.agents/skills/xyq-nest-skill/scripts")


class CdpPage:
    def __init__(self, page_id: str, cdp_url: str = DEFAULT_CDP_URL) -> None:
        target = next((item for item in list_pages(cdp_url) if item.get("id") == page_id), None)
        if not target:
            raise SystemExit(f"Page id not found: {page_id}")
        self.page_id = page_id
        self.cdp_url = cdp_url.rstrip("/")
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=20)
        self.next_id = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.next_id += 1
        msg_id = self.next_id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise RuntimeError(json.dumps(msg["error"], ensure_ascii=False))
            return msg.get("result", {})

    def eval(self, expression: str, *, await_promise: bool = False) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
        )
        remote = result.get("result") or {}
        return remote.get("value", remote)

    def screenshot(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        data = self.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})["data"]
        output.write_bytes(base64.b64decode(data))

    def bring_to_front(self) -> None:
        self.call("Page.bringToFront")


def list_pages(cdp_url: str) -> list[dict[str, Any]]:
    return json.load(urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=10))


def extract_thread_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url or "")
    query = urllib.parse.parse_qs(parsed.query)
    return (query.get("thread_id") or [""])[0]


def find_page_for_thread(cdp_url: str, thread_url: str, page_id: str = "") -> str:
    thread_id = extract_thread_id(thread_url)
    pages = list_pages(cdp_url)
    if page_id and any(item.get("id") == page_id for item in pages):
        return page_id
    if not thread_id:
        raise SystemExit("thread_url does not contain thread_id")
    matches = [
        item
        for item in pages
        if item.get("type") == "page" and extract_thread_id(str(item.get("url") or "")) == thread_id
    ]
    if matches:
        # Prefer the canonical full thread URL; source/home clones may lag the
        # active thread and make us type into an old page.
        matches.sort(key=lambda item: ("source=home_prompt" in str(item.get("url") or ""), str(item.get("id") or "")))
        return str(matches[0]["id"])
    encoded = urllib.parse.quote(thread_url, safe="")
    request = urllib.request.Request(f"{cdp_url.rstrip('/')}/json/new?{encoded}", method="PUT")
    page = json.load(urllib.request.urlopen(request, timeout=10))
    time.sleep(2)
    return str(page["id"])


STATE_JS = r"""
(() => {
  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const text = el => (el && (el.innerText || el.textContent || el.title || el.getAttribute('aria-label') || '') || '').trim();
  const rect = el => {
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height), cx:Math.round(r.x + r.width / 2), cy:Math.round(r.y + r.height / 2)};
  };
  const bodyText = document.body ? (document.body.innerText || '') : '';
  const tail = bodyText.slice(-3500);
  const editables = [...document.querySelectorAll('textarea,input,[contenteditable=true],[contenteditable=plaintext-only]')]
    .filter(visible)
    .map((el, i) => ({i, tag:el.tagName, role:el.getAttribute('role'), placeholder:el.getAttribute('placeholder'), aria:el.getAttribute('aria-label'), text:text(el).slice(0,160), value:(el.value || '').slice(0,160), rect:rect(el)}));
  const buttons = [...document.querySelectorAll('button,[role=button]')]
    .filter(visible)
    .map((el, i) => ({i, text:text(el).replace(/\s+/g, ' ').slice(0,180), className:String(el.className || '').slice(0,180), disabled:!!el.disabled || el.getAttribute('aria-disabled') === 'true', rect:rect(el)}));
  const status = (tail.match(/(排队等待中|优先处理中|生成中|大约还需\s*\d+\s*分钟|还需\s*\d+\s*分钟|下载|完成|请确认|符合预期|继续帮您生成视频|生成失败|任务失败|内部错误|积分不足|余额不足|审核|合规|重新生成)/g) || []).slice(-120);
  return {href: location.href, title: document.title, tail, status, editables, buttons, videoCount: document.querySelectorAll('video').length};
})()
"""


FOCUS_COMPOSER_JS = r"""
(() => {
  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const text = el => (el && (el.innerText || el.textContent || el.title || el.getAttribute('aria-label') || '') || '').trim();
  const editables = [...document.querySelectorAll('textarea,input,[contenteditable=true],[contenteditable=plaintext-only]')]
    .filter(visible)
    .filter(el => !/查找|search/i.test(el.getAttribute('placeholder') || ''))
    .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom);
  const composer = editables[0];
  if (!composer) return {ok:false, reason:'composer not found'};
  composer.focus();
  if (composer.isContentEditable) {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(composer);
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand('delete');
    composer.textContent = '';
  } else {
    composer.value = '';
  }
  composer.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'deleteContentBackward'}));
  const r = composer.getBoundingClientRect();
  return {ok:true, beforeText:text(composer), rect:{x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height), cx:Math.round(r.x + r.width / 2), cy:Math.round(r.y + r.height / 2)}};
})()
"""


CLICK_SEND_JS = r"""
(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const text = el => (el && (el.innerText || el.textContent || el.title || el.getAttribute('aria-label') || '') || '').trim();
  const rect = el => {
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height), cx:Math.round(r.x + r.width / 2), cy:Math.round(r.y + r.height / 2)};
  };
  const editables = [...document.querySelectorAll('textarea,input,[contenteditable=true],[contenteditable=plaintext-only]')]
    .filter(visible)
    .filter(el => !/查找|search/i.test(el.getAttribute('placeholder') || ''))
    .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom);
  const composer = editables[0];
  if (!composer) return {ok:false, reason:'composer not found'};
  composer.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text(composer).slice(0,32)}));
  composer.dispatchEvent(new Event('change', {bubbles:true}));
  await sleep(900);
  const r = composer.getBoundingClientRect();
  const buttons = [...document.querySelectorAll('button,[role=button]')]
    .filter(visible)
    .map(el => ({el, rect:el.getBoundingClientRect(), text:text(el), className:String(el.className || '')}))
    .filter(item => /sendMessageTool|send|发送/i.test(item.className + ' ' + item.text))
    .filter(item => item.rect.y >= r.y - 12 && item.rect.y <= r.y + 150 && item.rect.x >= r.x + r.width - 110)
    .sort((a, b) => b.rect.x - a.rect.x || b.rect.y - a.rect.y);
  const send = buttons[0] || null;
  const composerText = text(composer);
  if (!send) {
    return {ok:false, reason:'send button not found', composerText, composer:rect(composer)};
  }
  const disabled = !!send.el.disabled || send.el.getAttribute('aria-disabled') === 'true' || /disabled/i.test(send.className);
  if (disabled) {
    return {ok:false, reason:'send button disabled after text insertion', composerText, button:{text:send.text, className:send.className.slice(0,160), ...rect(send.el)}};
  }
  const x = send.rect.x + send.rect.width / 2;
  const y = send.rect.y + send.rect.height / 2;
  send.el.dispatchEvent(new MouseEvent('mouseover', {bubbles:true, clientX:x, clientY:y}));
  send.el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, clientX:x, clientY:y}));
  send.el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, clientX:x, clientY:y}));
  send.el.click();
  await sleep(1200);
  return {ok:true, method:'button', button:{text:send.text, className:send.className.slice(0,160), x:Math.round(send.rect.x), y:Math.round(send.rect.y), w:Math.round(send.rect.width), h:Math.round(send.rect.height)}};
})()
"""


def needs_continuation(state: dict[str, Any]) -> bool:
    tail = str(state.get("tail") or "")
    status = "\n".join(str(item) for item in state.get("status") or [])
    text = f"{tail}\n{status}"
    has_confirm = "请确认" in text or "符合预期" in text
    has_continue = "继续帮您生成视频" in text or ("继续" in text and "生成视频" in text)
    has_terminal_video = bool(state.get("videoCount")) or ("最终视频" in text and "下载" in text)
    return bool(has_confirm and has_continue and not has_terminal_video)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def api_continue_thread(thread_url: str, message: str, *, dotenv: Path, skill_scripts: Path) -> dict[str, Any]:
    load_dotenv(dotenv)
    if not os.environ.get("XYQ_ACCESS_KEY"):
        return {"ok": False, "skipped": True, "reason": "XYQ_ACCESS_KEY is not set"}
    thread_id = extract_thread_id(thread_url)
    if not thread_id:
        return {"ok": False, "skipped": True, "reason": "thread_url does not contain thread_id"}
    if not (skill_scripts / "_common.py").is_file():
        return {"ok": False, "skipped": True, "reason": f"missing Xiaoyunque helper scripts: {skill_scripts}"}
    sys.path.insert(0, str(skill_scripts))
    try:
        from _common import submit_run  # type: ignore

        data = submit_run(thread_id=thread_id, message=message, asset_ids=None)
    except SystemExit as exc:
        return {"ok": False, "reason": f"submit_run exited: {exc.code}"}
    except Exception as exc:  # noqa: BLE001 - keep fallback nonfatal.
        return {"ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:240]}"}
    run = data.get("run") if isinstance(data, dict) else {}
    return {
        "ok": bool(isinstance(run, dict) and run.get("thread_id") and run.get("run_id")),
        "thread_id": (run or {}).get("thread_id") if isinstance(run, dict) else "",
        "run_id": (run or {}).get("run_id") if isinstance(run, dict) else "",
        "web_thread_link": data.get("web_thread_link") if isinstance(data, dict) else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--page-id", default="")
    parser.add_argument("--thread-url", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--task-id", default="xyq-task")
    parser.add_argument("--message", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--api-continue", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dotenv", type=Path, default=DEFAULT_DOTENV)
    parser.add_argument("--skill-scripts", type=Path, default=DEFAULT_XYQ_SKILL_SCRIPTS)
    args = parser.parse_args()

    page_id = find_page_for_thread(args.cdp_url, args.thread_url, args.page_id)
    page = CdpPage(page_id, args.cdp_url)
    page.bring_to_front()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    before_path = args.artifact_dir / f"{args.task_id}_xyq_continue_before.png"
    after_path = args.artifact_dir / f"{args.task_id}_xyq_continue_after.png"
    state_path = args.artifact_dir / f"{args.task_id}_xyq_continue_state.json"
    page.screenshot(before_path)
    before = page.eval(STATE_JS)
    if not isinstance(before, dict):
        raise SystemExit("Unexpected browser state payload")

    needed = needs_continuation(before)
    result: dict[str, Any] = {"ok": True, "skipped": True, "reason": "dry_run"}
    after = before
    if not needed and not args.force:
        payload = {
            "ok": True,
            "status": "no_action",
            "reason": "thread is not asking for continuation",
            "page_id": page_id,
            "thread_url": before.get("href") or args.thread_url,
            "before": before,
            "screenshots": [str(before_path)],
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.submit:
        focus_raw = page.eval(FOCUS_COMPOSER_JS)
        focus_result = focus_raw if isinstance(focus_raw, dict) else {"ok": False, "raw": focus_raw}
        if focus_result.get("ok"):
            page.call("Input.insertText", {"text": args.message})
            time.sleep(0.5)
            result_raw = page.eval(CLICK_SEND_JS, await_promise=True)
            result = result_raw if isinstance(result_raw, dict) else {"ok": False, "raw": result_raw}
            result["focus"] = focus_result
        else:
            result = focus_result
        if args.api_continue:
            api_result = api_continue_thread(
                args.thread_url,
                args.message,
                dotenv=args.dotenv,
                skill_scripts=args.skill_scripts,
            )
            result["api"] = api_result
            if api_result.get("ok"):
                result["ok"] = True
        time.sleep(2)
        after = page.eval(STATE_JS)
    page.screenshot(after_path)
    payload = {
        "ok": bool(result.get("ok")),
        "status": "continued" if args.submit and result.get("ok") else "ready",
        "page_id": page_id,
        "thread_url": (after if isinstance(after, dict) else before).get("href") or args.thread_url,
        "thread_id": extract_thread_id(str((after if isinstance(after, dict) else before).get("href") or args.thread_url)),
        "needed": needed,
        "message": args.message,
        "before": before,
        "after": after,
        "submit": result,
        "screenshots": [str(before_path), str(after_path)],
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
