#!/usr/bin/env python3
"""Submit a ready Xiaoyunque composer through Chrome DevTools once.

This helper is intentionally narrow. It does not build prompts, choose models,
or upload files. It only verifies an already-prepared composer, clicks the
enabled create button once, and returns enough thread/page state for the
generated-video monitor.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

import websocket


DEFAULT_CDP_URL = "http://127.0.0.1:9222"


class CdpPage:
    def __init__(self, page_id: str, cdp_url: str = DEFAULT_CDP_URL) -> None:
        target = next((item for item in list_pages(cdp_url) if item.get("id") == page_id), None)
        if not target:
            raise SystemExit(f"Page id not found: {page_id}")
        self.page_id = page_id
        self.cdp_url = cdp_url.rstrip("/")
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15)
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


def choose_page(cdp_url: str, page_id: str = "") -> str:
    if page_id:
        return page_id
    candidates = [
        item
        for item in list_pages(cdp_url)
        if item.get("type") == "page" and "xyq.jianying.com/home" in str(item.get("url") or "")
    ]
    if not candidates:
        raise SystemExit("No Xiaoyunque home page found")
    # Prefer a prepared composer over arbitrary history/thread pages. Detailed
    # readiness checks run after attaching, but this avoids picking blank pages
    # or old clicked history when multiple Xiaoyunque tabs are open.
    candidates.sort(
        key=lambda item: (
            "thread_id=" not in str(item.get("url") or ""),
            "tab_name=home" in str(item.get("url") or ""),
            item.get("id") or "",
        ),
        reverse=True,
    )
    return str(candidates[0]["id"])


def choose_page_by_state(
    cdp_url: str,
    *,
    page_id: str = "",
    request_text: str = "",
    expect_duration: int | None = None,
    min_attachments: int = 8,
    min_prompt_chars: int = 300,
) -> str:
    if page_id:
        return page_id
    pages = [
        item
        for item in list_pages(cdp_url)
        if item.get("type") == "page" and "xyq.jianying.com/home" in str(item.get("url") or "")
    ]
    scored: list[tuple[int, str]] = []
    for item in pages:
        candidate_id = str(item.get("id") or "")
        if not candidate_id:
            continue
        try:
            page = CdpPage(candidate_id, cdp_url)
            state = page.eval(STATE_JS)
        except Exception:
            continue
        if not isinstance(state, dict):
            continue
        match = task_match_score(state, request_text)
        errors = validate_state(state, expect_duration, min_attachments, min_prompt_chars)
        score = 0
        if state.get("threadId") and match >= 2:
            score += 1000 + match
        elif not state.get("threadId") and not errors:
            score += 2000 + int(state.get("promptLength") or 0) // 100 + int(state.get("attachmentCount") or 0)
        elif not state.get("threadId"):
            score += int(state.get("submitReady") or 0) * 100 + int(state.get("attachmentCount") or 0) * 10
        if "thread_id=" not in str(item.get("url") or ""):
            score += 5
        scored.append((score, candidate_id))
    if scored:
        scored.sort(reverse=True)
        if scored[0][0] > 0:
            return scored[0][1]
    return choose_page(cdp_url, page_id)


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
  const buttons = [...document.querySelectorAll('button,[role=button]')].filter(visible);
  const createCandidates = buttons
    .filter(el => /createButton/.test(String(el.className || '')))
    .map(el => ({el, className:String(el.className || ''), text:text(el), rect:rect(el), disabled:!!el.disabled || el.getAttribute('aria-disabled') === 'true'}))
    .sort((a, b) => b.rect.y - a.rect.y || b.rect.x - a.rect.x);
  const create = createCandidates[0] || null;
  const editor = [...document.querySelectorAll('.editor-HT1dqv,.ProseMirror,[contenteditable=true],[contenteditable=plaintext-only],textarea,input')]
    .filter(visible)
    .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0] || null;
  const toolbar = buttons
    .filter(el => rect(el).y > window.innerHeight * 0.55 && rect(el).y < window.innerHeight)
    .map(el => text(el).replace(/\s+/g, ' ').slice(0, 120))
    .filter(Boolean);
  const lowerText = [...document.querySelectorAll('body *')]
    .filter(visible)
    .filter(el => {
      const r = el.getBoundingClientRect();
      return r.y > window.innerHeight * 0.25 && r.y < window.innerHeight;
    })
    .map(el => text(el).replace(/\s+/g, ' ').slice(0, 160))
    .filter(Boolean)
    .slice(0, 120);
  const removeButtons = buttons.filter(el => /removeButton/.test(String(el.className || ''))).length;
  const mentionButtons = buttons.filter(el => /mentionButton/.test(String(el.className || ''))).length;
  const promptText = editor ? text(editor) : '';
  const url = location.href;
  const threadMatch = url.match(/[?&]thread_id=([^&]+)/);
  return {
    href: url,
    title: document.title,
    threadId: threadMatch ? decodeURIComponent(threadMatch[1]) : '',
    promptLength: promptText.length,
    promptExcerpt: promptText.slice(0, 500),
    attachmentCount: Math.max(removeButtons, mentionButtons),
    toolbar,
    lowerText,
    createButton: create ? {text:create.text, className:create.className.slice(0, 180), rect:create.rect, disabled:create.disabled, ready:/createButtonReady/.test(create.className)} : null,
    submitReady: !!create && !create.disabled && /createButtonReady/.test(create.className),
    costText: toolbar.find(item => item.includes('/秒') || item.includes('积分')) || '',
    durationText: toolbar.find(item => /\d+\s*秒/.test(item)) || '',
    modelText: toolbar.find(item => /Seedance|Mini|Fast|VIP/i.test(item)) || '',
  };
})()
"""


SUBMIT_JS = r"""
(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const rect = el => {
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height), cx:Math.round(r.x + r.width / 2), cy:Math.round(r.y + r.height / 2)};
  };
  const buttons = [...document.querySelectorAll('button,[role=button]')].filter(visible);
  const create = buttons
    .filter(el => /createButton/.test(String(el.className || '')))
    .filter(el => !el.disabled && el.getAttribute('aria-disabled') !== 'true')
    .filter(el => /createButtonReady/.test(String(el.className || '')))
    .sort((a, b) => b.getBoundingClientRect().y - a.getBoundingClientRect().y || b.getBoundingClientRect().x - a.getBoundingClientRect().x)[0] || null;
  if (!create) return {ok:false, reason:'ready create button not found'};
  const before = location.href;
  const clicked = {rect:rect(create), className:String(create.className || '').slice(0, 180)};
  create.dispatchEvent(new MouseEvent('mouseover', {bubbles:true, clientX:clicked.rect.cx, clientY:clicked.rect.cy}));
  create.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, clientX:clicked.rect.cx, clientY:clicked.rect.cy}));
  create.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, clientX:clicked.rect.cx, clientY:clicked.rect.cy}));
  create.click();
  await sleep(800);
  return {ok:true, before, after:location.href, clicked};
})()
"""


def expected_duration_seconds(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:s|sec|secs|second|seconds|秒)", text or "", flags=re.I)
    if not match:
        return None
    return int(match.group(1))


def salient_terms(text: str, *, limit: int = 20) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fffぁ-ゟァ-ヿ]{2,}", text or "")
    stop = {
        "could",
        "you",
        "with",
        "this",
        "video",
        "model",
        "mini",
        "give",
        "back",
        "group",
        "send",
        "lazyedit",
        "publish",
        "context",
        "generate",
        "current",
        "request",
        "coalesced",
        "优化后的版本",
        "每句尽量清楚",
        "直接",
    }
    terms: list[str] = []
    for term in raw_terms:
        folded = term.casefold()
        if folded in stop or len(term) < 3:
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def task_match_score(state: dict[str, Any], request_text: str) -> int:
    haystack = json.dumps(
        {
            "href": state.get("href"),
            "title": state.get("title"),
            "prompt": state.get("promptExcerpt"),
            "toolbar": state.get("toolbar"),
            "lowerText": state.get("lowerText"),
        },
        ensure_ascii=False,
    ).casefold()
    score = 0
    for term in salient_terms(request_text):
        if term.casefold() in haystack:
            score += 1
    return score


def validate_state(state: dict[str, Any], expect_duration: int | None, min_attachments: int, min_prompt_chars: int) -> list[str]:
    errors: list[str] = []
    if state.get("threadId"):
        return errors
    if not state.get("submitReady"):
        errors.append("create button is not ready")
    if int(state.get("promptLength") or 0) < min_prompt_chars:
        errors.append(f"prompt is too short: {state.get('promptLength') or 0}")
    if int(state.get("attachmentCount") or 0) < min_attachments:
        errors.append(f"not enough uploaded references: {state.get('attachmentCount') or 0} < {min_attachments}")
    if expect_duration:
        duration_text = visible_duration_text(state)
        if not duration_matches(duration_text, expect_duration):
            errors.append(f"expected duration {expect_duration}s not visible: {duration_text[:200]}")
    return errors


def visible_duration_text(state: dict[str, Any]) -> str:
    return json.dumps(
        {
            "durationText": state.get("durationText"),
            "toolbar": state.get("toolbar"),
            "lowerText": state.get("lowerText"),
            "promptExcerpt": state.get("promptExcerpt"),
        },
        ensure_ascii=False,
    )


def duration_matches(text: str, expect_duration: int) -> bool:
    compact = re.sub(r"\s+", "", text or "").casefold()
    value = str(expect_duration)
    markers = (
        f"{value}秒",
        f"{value}s",
        f"{value}sec",
        f"{value}secs",
        f"{value}second",
        f"{value}seconds",
    )
    return any(marker in compact for marker in markers)


def thread_url_from_state(state: dict[str, Any]) -> str:
    href = str(state.get("href") or "")
    return href if "thread_id=" in href else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--page-id", default="")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--task-id", default="xyq-task")
    parser.add_argument("--request-text", default="")
    parser.add_argument("--expect-duration", type=int, default=0)
    parser.add_argument("--min-attachments", type=int, default=8)
    parser.add_argument("--min-prompt-chars", type=int, default=300)
    parser.add_argument("--wait-seconds", type=float, default=25)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    expect_duration = args.expect_duration or expected_duration_seconds(args.request_text)
    page_id = choose_page_by_state(
        args.cdp_url,
        page_id=args.page_id,
        request_text=args.request_text,
        expect_duration=expect_duration,
        min_attachments=args.min_attachments,
        min_prompt_chars=args.min_prompt_chars,
    )
    page = CdpPage(page_id, args.cdp_url)
    page.bring_to_front()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    before_path = args.artifact_dir / f"{args.task_id}_xyq_submit_before.png"
    after_path = args.artifact_dir / f"{args.task_id}_xyq_submit_after.png"
    page.screenshot(before_path)
    before = page.eval(STATE_JS)
    if not isinstance(before, dict):
        raise SystemExit("Unexpected browser state payload")

    if before.get("threadId") and task_match_score(before, args.request_text) < 2:
        payload = {
            "ok": False,
            "status": "not_ready",
            "reason": "current page is an existing Xiaoyunque thread that does not match this task",
            "page_id": page_id,
            "before": before,
            "match_score": task_match_score(before, args.request_text),
            "screenshot": str(before_path),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    errors = validate_state(before, expect_duration, args.min_attachments, args.min_prompt_chars)
    if errors:
        payload = {
            "ok": False,
            "status": "not_ready",
            "reason": "; ".join(errors),
            "page_id": page_id,
            "before": before,
            "screenshot": str(before_path),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    submit_result: dict[str, Any] = {"ok": True, "skipped": True, "reason": "already on thread" if before.get("threadId") else "dry_run"}
    after = before
    if args.submit and not before.get("threadId"):
        submit_result_raw = page.eval(SUBMIT_JS, await_promise=True)
        submit_result = submit_result_raw if isinstance(submit_result_raw, dict) else {"ok": False, "raw": submit_result_raw}
        deadline = time.time() + args.wait_seconds
        while time.time() < deadline:
            time.sleep(1)
            current = page.eval(STATE_JS)
            if isinstance(current, dict):
                after = current
                if current.get("threadId") or "生成中" in json.dumps(current, ensure_ascii=False) or "排队" in json.dumps(current, ensure_ascii=False):
                    break
    page.screenshot(after_path)

    thread_url = thread_url_from_state(after)
    if thread_url or after.get("threadId"):
        status = "submitted"
    elif submit_result.get("ok") and submit_result.get("skipped"):
        status = "ready"
    else:
        status = "clicked" if submit_result.get("ok") else "blocked"
    payload = {
        "ok": bool(submit_result.get("ok")),
        "status": status,
        "page_id": page_id,
        "thread_url": thread_url,
        "thread_id": after.get("threadId") or "",
        "before": before,
        "after": after,
        "submit": submit_result,
        "screenshots": [str(before_path), str(after_path)],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
