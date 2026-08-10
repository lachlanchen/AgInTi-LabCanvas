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
TRUNCATED_RESULT_RE = re.compile(
    r"(?:\.\.\.|…)?\s*\[(?:truncated|已截断|已截斷)\]\s*$|"
    r"(?:response|answer|output|回复|回答|内容|內容).{0,24}"
    r"(?:was\s+truncated|is\s+truncated|已截断|已截斷)\s*$",
    re.I | re.S,
)
PUBLISH_CONFIRMATION_REQUIREMENT_RE = re.compile(
    r"(?:publish|publication|public_publish|waiting_confirmation|"
    r"发布|發佈|公开|公開).{0,80}"
    r"(?:confirm|confirmation|approval|permission|wait|"
    r"确认|確認|同意|许可|許可|授权|授權|等待)"
    r"|(?:confirm|confirmation|approval|permission|wait|"
    r"确认|確認|同意|许可|許可|授权|授權|等待).{0,80}"
    r"(?:publish|publication|public_publish|waiting_confirmation|"
    r"发布|發佈|公开|公開)",
    re.I | re.S,
)
SYNTHETIC_ATTACHMENT_INTAKE_RE = re.compile(
    r"^(?:[^:\n]{1,80}:\s*)?New WeChat "
    r"(?P<kind>voice|audio|video|image|file/link|file upload|file|link|attachment) "
    r"(?:item )?(?:received|transcribed)\b.*$",
    re.I,
)
SYNTHETIC_ATTACHMENT_METADATA_RE = re.compile(
    r"^(?:metadata|title|url|channel|channel_description|filename|extension|"
    r"size_bytes|md5|sha256|mime|mime_type|local_id|server_id|object_id|"
    r"duration|duration_seconds):",
    re.I,
)
SYNTHETIC_ATTACHMENT_POLICY_RE = re.compile(
    r"^(?:Link/read-later inbox source received\.|Structured source text:)",
    re.I,
)


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
    original = exact_source_message_text(task.get("context"), source)
    if not original:
        original = str(task.get("original_request") or "").strip()
    if not original:
        original = extract_current_request(task.get("request"))
    else:
        original = extract_current_request(original)
    items: list[dict[str, Any]] = []
    if original:
        original = normalize_auditable_request(original)
        items.append(
            {
                "item_id": f"task:{str(task.get('id') or source_identity(source, fallback='source'))}",
                "kind": "source",
                "sender": str(source.get("sender_display") or source.get("sender") or ""),
                "source_id": source_identity(source, fallback=""),
                "text": bounded_text(original),
            }
        )
    reprocess_reason = str(task.get("reprocess_reason") or "").strip()
    if reprocess_reason and reprocess_reason not in {
        "manual_reprocess",
        "numbered_message_not_covered",
        "same_chat_interruption",
        "interruption_arrived_during_worker_turn",
    }:
        items.append(
            {
                "item_id": f"reprocess:{str(task.get('id') or source_identity(source, fallback='source'))}",
                "kind": "reprocess",
                "sender": "system-recovery",
                "source_id": str(task.get("id") or ""),
                "text": bounded_text(reprocess_reason),
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
        text = exact_source_message_text(
            interruption.get("context"),
            interruption_source,
        )
        if not text:
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
                "text": bounded_text(
                    normalize_auditable_request(extract_current_request(text))
                ),
            }
        )
    numbered = deduplicate_items(items)
    for sequence, item in enumerate(numbered, start=1):
        item["sequence"] = sequence
    return numbered


def exact_source_message_text(
    rows: Any,
    source: dict[str, Any],
) -> str:
    """Return the human message bound to one exact transport identity."""

    if not isinstance(rows, list) or not isinstance(source, dict):
        return ""
    server_id = str(source.get("server_id") or "").strip()
    local_id = str(source.get("local_id") or "").strip()
    match: dict[str, Any] | None = None
    if server_id:
        match = next(
            (
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("server_id") or "").strip() == server_id
            ),
            None,
        )
    if match is None and local_id:
        match = next(
            (
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("local_id") or "").strip() == local_id
            ),
            None,
        )
    if match is None:
        return ""
    text = str(match.get("content") or "").strip()
    for sender in (
        match.get("sender"),
        match.get("sender_display"),
        source.get("sender"),
        source.get("sender_display"),
    ):
        sender_text = str(sender or "").strip()
        if not sender_text:
            continue
        for separator in (":\n", ":\r\n", ": ", "：\n", "： "):
            prefix = sender_text + separator
            if text.startswith(prefix):
                return text[len(prefix) :].strip()
    return text


def normalize_auditable_request(value: Any) -> str:
    """Remove monitor-authored attachment instructions from human intent.

    The direct monitor prepends a synthetic intake sentence and raw metadata to
    incoming attachments. Those fields are execution context, not another
    request that the completion checker may turn into a duplicate summary.
    Preserve a small default-intake requirement only for a truly naked upload.
    """

    lines = str(value or "").splitlines()
    kept: list[str] = []
    attachment_kinds: list[str] = []
    skip_metadata = False
    for line in lines:
        stripped = line.strip()
        match = SYNTHETIC_ATTACHMENT_INTAKE_RE.fullmatch(stripped)
        if match:
            attachment_kinds.append(match.group("kind").casefold().replace(" upload", ""))
            skip_metadata = True
            continue
        if attachment_kinds and SYNTHETIC_ATTACHMENT_POLICY_RE.match(stripped):
            break
        if skip_metadata and SYNTHETIC_ATTACHMENT_METADATA_RE.match(stripped):
            continue
        skip_metadata = False
        kept.append(line)
    normalized = "\n".join(kept).strip()
    if normalized:
        return normalized
    if attachment_kinds:
        kind = attachment_kinds[-1]
        return (
            f"Incoming WeChat {kind} attachment: apply the configured default "
            "intake behavior for this chat."
        )
    return str(value or "").strip()


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


def local_artifact_inventory(
    task: dict[str, Any],
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Expose bounded task-local file evidence without exposing absolute paths."""
    raw = str(task.get("artifact_dir") or "").strip()
    if not raw:
        return []
    artifact_dir = Path(raw).expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = ROOT / artifact_dir
    try:
        artifact_dir = artifact_dir.resolve()
        artifact_dir.relative_to((ROOT / "output").resolve())
    except (OSError, ValueError):
        return []
    if not artifact_dir.is_dir():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(artifact_dir)
            size = path.stat().st_size
        except OSError:
            continue
        files.append(
            {
                "name": relative.as_posix(),
                "suffix": path.suffix.casefold(),
                "size": size,
            }
        )
        if len(files) >= max(1, limit):
            break
    return files


def deterministic_missing_requirements(
    task: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    items = coverage_items(task)
    missing: list[dict[str, str]] = []
    route = (
        task.get("route_decision")
        if isinstance(task.get("route_decision"), dict)
        else {}
    )
    message_only = bool(route.get("message_only"))
    if (
        not message_only
        and explicit_pdf_requested(items)
        and ".pdf" not in result_file_suffixes(result)
    ):
        missing.append(
            {
                "item_id": first_pdf_item_id(items),
                "requirement": "Create and return the explicitly requested PDF artifact.",
                "kind": "artifact",
            }
        )
    if not message_only and explicit_pdf_requested(items) and not (
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
    candidate_text = "\n\n".join(
        str(result.get(field) or "").strip()
        for field in ("message", "confirmation")
        if str(result.get(field) or "").strip()
    )
    if candidate_text and TRUNCATED_RESULT_RE.search(candidate_text):
        missing.append(
            {
                "item_id": str(items[0].get("item_id") or "source") if items else "source",
                "requirement": (
                    "Return the complete answer. The candidate ended with an explicit "
                    "truncation marker; do not send only the clipped prefix."
                ),
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
    statuses = {str(audit.get("status") or "") for audit in audits}
    if statuses == {"unavailable"}:
        missing_ids = {
            str(item.get("item_id") or "")
            for item in deterministic_missing
        }
        covered_ids = [
            item_id for item_id in expected_ids if item_id not in missing_ids
        ]
        return {
            "status": "unavailable",
            "model": "",
            "backend": "codex",
            "coverage_complete": not deterministic_missing,
            "expected_item_ids": expected_ids,
            "covered_item_ids": covered_ids,
            "missing": deterministic_missing,
            "legitimate_blocker": False,
            "repair_recommended": bool(deterministic_missing),
            "complexity": "low",
            "summary": "Completion checker unavailable; deterministic contracts only.",
            "batch_count": len(audits),
        }
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
    status = "checked" if statuses == {"checked"} else "partial"
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
    missing, rejected_missing_ids = ground_model_missing_requirements(
        task,
        items,
        normalize_missing(payload.get("missing")),
    )
    expected_ids = [str(item.get("item_id") or "") for item in items]
    covered_ids = [
        item_id
        for item_id in normalize_string_list(payload.get("covered_item_ids"))
        if item_id in expected_ids
    ]
    covered_ids.extend(
        item_id
        for item_id in rejected_missing_ids
        if item_id in expected_ids and item_id not in covered_ids
    )
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


def ground_model_missing_requirements(
    task: dict[str, Any],
    items: list[dict[str, Any]],
    missing: list[dict[str, str]],
) -> tuple[list[dict[str, str]], set[str]]:
    """Reject artifact requirements created only by the completion model."""

    by_id = {
        str(item.get("item_id") or ""): item
        for item in items
        if str(item.get("item_id") or "")
    }
    grounded: list[dict[str, str]] = []
    rejected_ids: set[str] = set()
    for item in missing:
        item_id = str(item.get("item_id") or "")
        requirement = str(item.get("requirement") or "")
        kind = str(item.get("kind") or "")
        source = by_id.get(item_id, {})
        source_text = str(source.get("text") or "")
        claims_pdf = bool(PDF_REQUEST_RE.search(requirement)) or (
            kind == "artifact" and ".pdf" in requirement.casefold()
        )
        source_requests_pdf = bool(PDF_REQUEST_RE.search(source_text)) and not bool(
            NEGATED_PDF_RE.search(source_text)
        )
        route = (
            task.get("route_decision")
            if isinstance(task.get("route_decision"), dict)
            else {}
        )
        if kind == "artifact" and bool(route.get("message_only")):
            if item_id:
                rejected_ids.add(item_id)
            continue
        if claims_pdf and not source_requests_pdf:
            if item_id:
                rejected_ids.add(item_id)
            continue
        route = (
            task.get("route_decision")
            if isinstance(task.get("route_decision"), dict)
            else {}
        )
        requester_override = bool(route.get("requester_publish_override"))
        current_publish_allowed = bool(route.get("public_publish_allowed"))
        current_confirmation_required = bool(
            route.get("requires_third_party_publish_confirmation")
        )
        if (
            PUBLISH_CONFIRMATION_REQUIREMENT_RE.search(requirement)
            and current_publish_allowed
            and requester_override
            and not current_confirmation_required
        ):
            if item_id:
                rejected_ids.add(item_id)
            continue
        grounded.append(item)
    return grounded, rejected_ids


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
        "current_route_state": {
            "public_publish_allowed": bool(route.get("public_publish_allowed")),
            "external_fact_grounding_required": bool(
                route.get("external_fact_grounding_required")
            ),
            "requires_third_party_publish_confirmation": bool(
                route.get("requires_third_party_publish_confirmation")
            ),
            "requester_publish_override": bool(
                route.get("requester_publish_override")
            ),
        },
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
            "publish_stage": publish_stage_for_audit(result),
        },
        "task_local_artifacts": local_artifact_inventory(task),
    }
    return f"""You are a fast completion auditor for one exact WeChat or WeCom task.
Do not perform the task and do not write files. Check whether the candidate result covers every still-valid, safe request in every request item.

Rules:
- Keep consecutive messages as separate checklist items. Never silently drop an earlier independent request because a newer message exists.
- A newer explicit contradiction may update an older detail, but unrelated requirements remain active.
- When `current_route_state.external_fact_grounding_required` is true, the candidate must establish the named external example's actual relevant identity, product, mechanism, or role with traceable authoritative evidence before extending the comparison. A generic analogy that assumes what the example means, or an answer that skips the named premise and discusses only the surrounding topic, is missing the core action.
- Preserve sender attribution. Do not transfer one member's request or preference to another member.
- `candidate_result.files` is the outbound attachment list. A requested chat
  delivery is covered only when the file appears there.
- `task_local_artifacts` is a private, bounded existence inventory. It may
  satisfy an explicit local-retention or source-file requirement, but never a
  request to send or attach that file.
- A direct answer may summarize the work, but claiming an outbound attachment
  exists is not coverage unless that file appears in `candidate_result.files`.
- If a member explicitly requested a PDF, coverage requires both a useful direct answer and a `.pdf` artifact, unless a real login, approval, missing-source, or safety blocker is clearly stated.
- Treat only `request_items[*].text` as human requirements. Words such as PDF,
  Markdown, publication, or artifacts in candidate explanations, route labels,
  system policies, or task-local filenames do not create a request.
- A request item that says no PDF/report is the opposite of a PDF request. Do
  not invent a missing artifact merely because the candidate correctly says it
  did not attach one.
- A quoted message is context unless the current request asks the agent to act on it.
- A candidate `publish_stage.stage=published_verified` with `verified=true` is
  terminal evidence for an explicit publication request. Do not demand a
  separate attachment-metadata summary unless the human request explicitly
  asks for one.
- `current_route_state` is the current authoritative gate state. If a mistaken
  older wrapper was superseded by `requester_publish_override=true` and
  `public_publish_allowed=true`, do not resurrect the obsolete confirmation
  requirement.
- `published_with_unrequested_platform` is terminal evidence that the requested
  platforms completed with a platform-set defect. It covers the requested
  action only when the candidate reports the extra platform honestly; never
  request a duplicate corrective publish.
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


def publish_stage_for_audit(result: dict[str, Any]) -> dict[str, Any]:
    stage = result.get("publish_stage")
    if not isinstance(stage, dict) and isinstance(result.get("data"), dict):
        stage = result["data"].get("publish_stage")
    if not isinstance(stage, dict):
        return {}
    local_jobs = stage.get("local_jobs") if isinstance(stage.get("local_jobs"), list) else []
    remote_jobs = stage.get("remote_jobs") if isinstance(stage.get("remote_jobs"), list) else []
    compact = {
        "verified": bool(stage.get("verified")),
        "stage": str(stage.get("stage") or ""),
        "video_id": stage.get("video_id"),
        "requested_platforms": normalize_string_list(stage.get("requested_platforms")),
        "verified_platforms": normalize_string_list(stage.get("verified_platforms")),
        "local_jobs": [
            {
                "id": item.get("id"),
                "status": str(item.get("status") or ""),
                "remote_status": str(item.get("remote_status") or ""),
            }
            for item in local_jobs[:8]
            if isinstance(item, dict)
        ],
        "remote_jobs": [
            {
                "id": item.get("id"),
                "status": str(item.get("status") or ""),
            }
            for item in remote_jobs[:8]
            if isinstance(item, dict)
        ],
    }
    if "unexpected_platforms" in stage:
        compact["unexpected_platforms"] = normalize_string_list(
            stage.get("unexpected_platforms")
        )
    if "requested_platforms_verified" in stage:
        compact["requested_platforms_verified"] = bool(
            stage.get("requested_platforms_verified")
        )
    if "platform_set_matches" in stage:
        compact["platform_set_matches"] = bool(stage.get("platform_set_matches"))
    return compact


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
