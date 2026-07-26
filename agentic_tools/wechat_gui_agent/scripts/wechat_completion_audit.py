#!/usr/bin/env python3
"""Bounded completion audit for consecutive WeChat and WeCom task messages."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Callable

from wechat_agent_backend import run_agent_session


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = "gpt-5.3-codex-spark"
DEFAULT_FALLBACK_MODEL = "gpt-5.6-sol"
DEFAULT_TIMEOUT_SECONDS = 35
DEFAULT_BATCH_SIZE = 20
NEGATED_PDF_RE = re.compile(
    r"(?:\b(?:no|without|do\s+not|don't|dont|need(?:s)?\s+no)\b|不要|不用|无需|不需要)"
    r".{0,16}(?:pdf|\.pdf)",
    re.I | re.S,
)
PDF_REQUEST_RE = re.compile(r"(?:\bpdf\b|\.pdf\b|PDF)", re.I)


def extract_current_request(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(
        r"Current coalesced request:\n(?P<body>.*?)(?:\n\nRecent history:|"
        r"\n\nSame-chat reference media/context rows:|\n\nSame-chat interruption/update|\Z)",
        text,
        flags=re.DOTALL,
    )
    return match.group("body").strip() if match else text


def coverage_items(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve each authoritative message as an independently auditable item."""
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    original = str(task.get("original_request") or "").strip()
    if not original:
        original = extract_current_request(task.get("request"))
    items: list[dict[str, Any]] = []
    if original:
        items.append(
            {
                "item_id": f"task:{str(task.get('id') or source_identity(source, fallback='source'))}",
                "kind": "source",
                "sender": str(source.get("sender_display") or source.get("sender") or ""),
                "source_id": source_identity(source, fallback=""),
                "text": bounded_text(original),
            }
        )
    for index, interruption in enumerate(task.get("interruptions") or [], start=1):
        if not isinstance(interruption, dict):
            continue
        interruption_source = (
            interruption.get("source")
            if isinstance(interruption.get("source"), dict)
            else {}
        )
        text = str(
            interruption.get("request")
            or interruption.get("request_excerpt")
            or ""
        ).strip()
        if not text:
            continue
        items.append(
            {
                "item_id": (
                    f"task:{str(interruption.get('incoming_task_id') or source_identity(interruption_source, fallback=index))}"
                ),
                "kind": "interruption",
                "sender": str(
                    interruption_source.get("sender_display")
                    or interruption_source.get("sender")
                    or ""
                ),
                "source_id": source_identity(interruption_source, fallback=""),
                "text": bounded_text(extract_current_request(text)),
            }
        )
    numbered = deduplicate_items(items)
    for sequence, item in enumerate(numbered, start=1):
        item["sequence"] = sequence
    return numbered


def source_identity(source: dict[str, Any], *, fallback: Any) -> str:
    return str(
        source.get("server_id")
        or source.get("local_id")
        or source.get("create_time")
        or fallback
    )


def bounded_text(value: Any, *, max_chars: int = 2600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def deduplicate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("item_id") or ""), str(item.get("text") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def explicit_pdf_requested(items: list[dict[str, Any]]) -> bool:
    for item in items:
        text = str(item.get("text") or "")
        if PDF_REQUEST_RE.search(text) and not NEGATED_PDF_RE.search(text):
            return True
    return False


def result_file_suffixes(result: dict[str, Any]) -> set[str]:
    raw = result.get("files") if isinstance(result.get("files"), list) else []
    return {
        Path(str(value or "")).suffix.casefold()
        for value in raw
        if str(value or "").strip()
    }


def deterministic_missing_requirements(
    task: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    items = coverage_items(task)
    missing: list[dict[str, str]] = []
    if explicit_pdf_requested(items) and ".pdf" not in result_file_suffixes(result):
        missing.append(
            {
                "item_id": first_pdf_item_id(items),
                "requirement": "Create and return the explicitly requested PDF artifact.",
                "kind": "artifact",
            }
        )
    if explicit_pdf_requested(items) and not (
        str(result.get("message") or "").strip()
        or str(result.get("confirmation") or "").strip()
    ):
        missing.append(
            {
                "item_id": first_pdf_item_id(items),
                "requirement": "Provide a direct human answer or concise report summary with the PDF.",
                "kind": "reply",
            }
        )
    return missing


def first_pdf_item_id(items: list[dict[str, Any]]) -> str:
    for item in items:
        text = str(item.get("text") or "")
        if PDF_REQUEST_RE.search(text) and not NEGATED_PDF_RE.search(text):
            return str(item.get("item_id") or "source")
    return "source"


def run_completion_audit(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    runner: Callable[..., dict[str, Any]] = run_agent_session,
) -> dict[str, Any]:
    """Audit one result once; audit failure never blocks the original result."""
    items = coverage_items(task)
    expected_ids = [str(item.get("item_id") or "") for item in items]
    deterministic_missing = deterministic_missing_requirements(task, result)
    if os.environ.get("WECHAT_COMPLETION_AUDIT_ENABLED", "1") != "1":
        return {
            "status": "disabled",
            "coverage_complete": not deterministic_missing,
            "expected_item_ids": expected_ids,
            "covered_item_ids": [],
            "missing": deterministic_missing,
            "repair_recommended": bool(deterministic_missing),
        }
    if not items:
        return {
            "status": "no-items",
            "coverage_complete": not deterministic_missing,
            "expected_item_ids": [],
            "covered_item_ids": [],
            "missing": deterministic_missing,
            "repair_recommended": bool(deterministic_missing),
        }
    batch_size = max(
        1,
        int(
            os.environ.get(
                "WECHAT_COMPLETION_AUDIT_BATCH_SIZE",
                str(DEFAULT_BATCH_SIZE),
            )
        ),
    )
    audits = [
        run_completion_audit_batch(
            task,
            result,
            items[index : index + batch_size],
            runner=runner,
        )
        for index in range(0, len(items), batch_size)
    ]
    legitimately_blocked_ids = {
        item_id
        for audit in audits
        if bool(audit.get("legitimate_blocker"))
        for item_id in audit.get("covered_item_ids") or []
    }
    deterministic_missing = [
        item
        for item in deterministic_missing
        if str(item.get("item_id") or "") not in legitimately_blocked_ids
    ]
    missing = merge_missing(
        deterministic_missing,
        [
            item
            for audit in audits
            for item in audit.get("missing") or []
            if isinstance(item, dict)
        ],
    )
    missing_ids = {str(item.get("item_id") or "") for item in missing}
    covered_ids = [
        item_id
        for item_id in expected_ids
        if item_id not in missing_ids
        and any(item_id in (audit.get("covered_item_ids") or []) for audit in audits)
    ]
    decided_ids = set(covered_ids) | missing_ids
    for item in items:
        item_id = str(item.get("item_id") or "")
        if item_id and item_id not in decided_ids:
            missing.append(
                {
                    "item_id": item_id,
                    "requirement": "The checker did not confirm that this numbered message was covered.",
                    "kind": "action",
                }
            )
    missing = merge_missing(missing, [])
    missing_ids = {str(item.get("item_id") or "") for item in missing}
    covered_ids = [item_id for item_id in covered_ids if item_id not in missing_ids]
    statuses = {str(audit.get("status") or "") for audit in audits}
    status = "checked" if statuses == {"checked"} else "partial"
    if statuses == {"unavailable"}:
        status = "unavailable"
    complexities = [
        normalize_complexity(audit.get("complexity"))
        for audit in audits
    ]
    complexity = max(
        complexities or ["low"],
        key={"low": 0, "medium": 1, "high": 2}.get,
    )
    return {
        "status": status,
        "model": ",".join(
            dict.fromkeys(
                str(audit.get("model") or "")
                for audit in audits
                if str(audit.get("model") or "")
            )
        ),
        "backend": "codex",
        "coverage_complete": not missing,
        "expected_item_ids": expected_ids,
        "covered_item_ids": covered_ids,
        "missing": missing,
        "legitimate_blocker": any(
            bool(audit.get("legitimate_blocker")) for audit in audits
        ),
        "repair_recommended": bool(missing),
        "complexity": complexity,
        "summary": "; ".join(
            str(audit.get("summary") or "")
            for audit in audits
            if str(audit.get("summary") or "")
        )[:600],
        "batch_count": len(audits),
    }


def run_completion_audit_batch(
    task: dict[str, Any],
    result: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    runner: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Audit a bounded numbered slice without dropping rows from long bursts."""
    prompt = completion_audit_prompt(task, result, items)
    try:
        response = runner(
            prompt,
            backend="codex",
            chat_name=str(task.get("chat") or "wechat-chat"),
            role="completion_audit",
            model=os.environ.get("WECHAT_COMPLETION_AUDIT_MODEL", DEFAULT_MODEL),
            reasoning_effort="low",
            sandbox="read-only",
            timeout_seconds=int(
                os.environ.get(
                    "WECHAT_COMPLETION_AUDIT_TIMEOUT_SECONDS",
                    str(DEFAULT_TIMEOUT_SECONDS),
                )
            ),
            workdir=ROOT,
            reuse=True,
            fallback_model=os.environ.get(
                "WECHAT_COMPLETION_AUDIT_FALLBACK_MODEL",
                DEFAULT_FALLBACK_MODEL,
            ),
            fallback_reasoning_effort="low",
            backend_config={
                "agent_fallbacks": {
                    "fallback_to_aginti": False,
                    "purchased_credit_retry": True,
                }
            },
        )
    except Exception as exc:
        return unavailable_audit(items, exc)
    if not response.get("ok"):
        return unavailable_audit(
            items,
            RuntimeError(
                str(response.get("message") or response.get("stderr_tail") or "audit backend failed")
            ),
        )
    payload = extract_json_object(str(response.get("message") or ""))
    if not isinstance(payload, dict):
        return unavailable_audit(
            items,
            ValueError("completion audit returned no JSON object"),
        )
    missing = normalize_missing(payload.get("missing"))
    expected_ids = [str(item.get("item_id") or "") for item in items]
    covered_ids = [
        item_id
        for item_id in normalize_string_list(payload.get("covered_item_ids"))
        if item_id in expected_ids
    ]
    decided_ids = set(covered_ids) | {
        str(item.get("item_id") or "") for item in missing
    }
    for item in items:
        item_id = str(item.get("item_id") or "")
        if item_id and item_id not in decided_ids:
            missing.append(
                {
                    "item_id": item_id,
                    "requirement": "The checker did not confirm that this numbered message was covered.",
                    "kind": "action",
                }
            )
    missing_ids = {str(item.get("item_id") or "") for item in missing}
    covered_ids = [item_id for item_id in covered_ids if item_id not in missing_ids]
    blocker = bool(payload.get("legitimate_blocker"))
    return {
        "status": "checked",
        "model": str(response.get("model") or DEFAULT_MODEL),
        "backend": str(response.get("backend") or "codex"),
        "coverage_complete": not missing,
        "expected_item_ids": expected_ids,
        "covered_item_ids": covered_ids,
        "missing": missing,
        "legitimate_blocker": blocker,
        "repair_recommended": bool(missing),
        "complexity": normalize_complexity(payload.get("complexity")),
        "summary": bounded_text(payload.get("summary"), max_chars=600),
    }


def unavailable_audit(
    items: list[dict[str, Any]],
    exc: Exception,
) -> dict[str, Any]:
    expected_ids = [str(item.get("item_id") or "") for item in items]
    return {
        "status": "unavailable",
        "coverage_complete": False,
        "expected_item_ids": expected_ids,
        "covered_item_ids": [],
        "missing": [
            {
                "item_id": item_id,
                "requirement": "Completion checker unavailable; this numbered message remains unverified.",
                "kind": "action",
            }
            for item_id in expected_ids
        ],
        "repair_recommended": False,
        "complexity": "low",
        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
    }


def completion_audit_prompt(
    task: dict[str, Any],
    result: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    route = task.get("route_decision") if isinstance(task.get("route_decision"), dict) else {}
    payload = {
        "task_id": str(task.get("id") or ""),
        "chat": str(task.get("chat") or ""),
        "route_kind": str(route.get("route_kind") or ""),
        "request_items": items,
        "candidate_result": {
            "message": bounded_text(result.get("message"), max_chars=6000),
            "confirmation": bounded_text(result.get("confirmation"), max_chars=1600),
            "files": [
                {
                    "name": Path(str(path)).name,
                    "suffix": Path(str(path)).suffix.casefold(),
                }
                for path in (result.get("files") or [])
            ],
        },
    }
    return f"""You are a fast completion auditor for one exact WeChat or WeCom task.
Do not perform the task and do not write files. Check whether the candidate result covers every still-valid, safe request in every request item.

Rules:
- Keep consecutive messages as separate checklist items. Never silently drop an earlier independent request because a newer message exists.
- A newer explicit contradiction may update an older detail, but unrelated requirements remain active.
- Preserve sender attribution. Do not transfer one member's request or preference to another member.
- A direct answer may summarize the work, but claiming a file exists is not coverage unless that file appears in candidate_result.files.
- If a member explicitly requested a PDF, coverage requires both a useful direct answer and a `.pdf` artifact, unless a real login, approval, missing-source, or safety blocker is clearly stated.
- A quoted message is context unless the current request asks the agent to act on it.
- Do not demand publication, payment, account changes, deletion, or another irreversible action unless explicitly authorized by the current request.
- Mark a legitimate blocker only when the candidate clearly explains why safe completion cannot proceed.
- When a legitimate blocker directly answers one request item, include that item in `covered_item_ids`; do not use one blocked item to cover unrelated messages.

Return JSON only:
{{
  "covered_item_ids": ["source:123"],
  "missing": [{{"item_id":"interruption:456","requirement":"specific omitted action","kind":"reply|artifact|action"}}],
  "legitimate_blocker": false,
  "complexity": "low|medium|high",
  "summary": "one short private diagnostic"
}}

Task packet:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    candidates = [stripped]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            stripped,
            flags=re.I | re.S,
        )
    )
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            value = None
        if isinstance(value, dict):
            return value
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
            except Exception:
                continue
            if isinstance(value, dict):
                return value
    return None


def normalize_missing(value: Any) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            requirement = bounded_text(item, max_chars=600)
            if requirement:
                result.append(
                    {
                        "item_id": "unspecified",
                        "requirement": requirement,
                        "kind": "action",
                    }
                )
            continue
        if not isinstance(item, dict):
            continue
        requirement = bounded_text(item.get("requirement"), max_chars=600)
        if not requirement:
            continue
        kind = str(item.get("kind") or "action").casefold()
        if kind not in {"reply", "artifact", "action"}:
            kind = "action"
        result.append(
            {
                "item_id": bounded_text(item.get("item_id"), max_chars=160)
                or "unspecified",
                "requirement": requirement,
                "kind": kind,
            }
        )
    return result


def merge_missing(
    first: list[dict[str, str]],
    second: list[dict[str, str]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in [*first, *second]:
        key = (
            str(item.get("item_id") or ""),
            str(item.get("requirement") or "").casefold(),
        )
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_string_list(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else []
    return [bounded_text(item, max_chars=160) for item in raw[:20] if bounded_text(item, max_chars=160)]


def normalize_complexity(value: Any) -> str:
    normalized = str(value or "low").casefold()
    return normalized if normalized in {"low", "medium", "high"} else "low"
