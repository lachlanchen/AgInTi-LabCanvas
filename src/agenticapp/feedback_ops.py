from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
import unicodedata


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPORT_KINDS = ("bug", "feature", "handoff")
REPORT_STATUSES = (
    "open",
    "needs-reproduction",
    "accepted",
    "resolved",
    "declined",
)
MAX_FIELD_CHARS = 20_000
MAX_LIST_ITEMS = 100


@dataclass(frozen=True)
class FeedbackTarget:
    id: str
    title: str
    root: Path

    @property
    def report_dir(self) -> Path:
        return self.root / "handoff" / "labcanvas"


def add_feedback_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "feedback",
        help="Write private, evidence-based integration reports into allowlisted repositories.",
    )
    commands = parser.add_subparsers(dest="feedback_command", required=True)

    targets = commands.add_parser(
        "targets",
        help="List repositories that may receive local LabCanvas reports.",
    )
    targets.add_argument("--json", action="store_true")
    targets.set_defaults(func=cmd_feedback_targets)

    write = commands.add_parser(
        "write",
        help="Create or update an idempotent bug, feature, or handoff report.",
    )
    write.add_argument("target", nargs="?")
    write.add_argument("kind", nargs="?", choices=REPORT_KINDS)
    write.add_argument("title", nargs="?")
    write.add_argument(
        "--payload",
        type=Path,
        help="Read the structured report fields from a local JSON object.",
    )
    write.add_argument("--summary", default="")
    write.add_argument("--expected", default="")
    write.add_argument("--observed", default="")
    write.add_argument("--evidence", action="append", default=[])
    write.add_argument("--acceptance", action="append", default=[])
    write.add_argument("--workaround", default="")
    write.add_argument("--source-ref", default="")
    write.add_argument("--status", choices=REPORT_STATUSES, default="")
    write.add_argument(
        "--verified",
        action="store_true",
        help="Mark the behavior as reproduced or otherwise supported by concrete evidence.",
    )
    write.add_argument("--json", action="store_true")
    write.set_defaults(func=cmd_feedback_write)

    reports = commands.add_parser(
        "list",
        help="List bounded report metadata for one allowlisted repository.",
    )
    reports.add_argument("target")
    reports.add_argument("--kind", choices=REPORT_KINDS, default="")
    reports.add_argument("--json", action="store_true")
    reports.set_defaults(func=cmd_feedback_list)


def target_registry(
    labcanvas_root: Path | None = None,
) -> dict[str, FeedbackTarget]:
    labcanvas = (labcanvas_root or PACKAGE_ROOT).expanduser().resolve()
    projects = labcanvas.parent

    def configured_root(target_id: str, default: Path) -> Path:
        env_name = f"LABCANVAS_FEEDBACK_{target_id.upper()}_ROOT"
        return Path(os.environ.get(env_name) or default).expanduser().resolve()

    specs = (
        ("labcanvas", "AgInTi LabCanvas", labcanvas),
        (
            "lazyedit",
            "LazyEdit",
            Path(os.environ.get("LAZYEDIT_ROOT") or "/home/lachlan/DiskMech/Projects/lazyedit"),
        ),
        ("musia", "Musia", projects / "Musia"),
        ("books", "Books / AgenticBrowser", projects / "Books"),
        ("zhjpbook", "ZhJpBook / PocketPolyglot", projects / "ZhJpBook"),
        ("lalachan", "LALACHAN / Xiaoyunque", projects / "LALACHAN"),
        ("proteinstructure", "ProteinStructure", projects / "ProteinStructure"),
        ("agintiflow", "AgInTiFlow", projects / "Agent" / "AgInTiFlow"),
    )
    return {
        target_id: FeedbackTarget(
            id=target_id,
            title=title,
            root=configured_root(target_id, Path(default)),
        )
        for target_id, title, default in specs
    }


def resolve_target(
    target_id: str,
    *,
    registry: Mapping[str, FeedbackTarget] | None = None,
) -> FeedbackTarget:
    targets = dict(registry or target_registry())
    normalized = str(target_id or "").strip().casefold()
    if normalized not in targets:
        allowed = ", ".join(sorted(targets))
        raise ValueError(f"Unknown feedback target {target_id!r}; allowed targets: {allowed}")
    target = targets[normalized]
    if not target.root.is_dir():
        raise ValueError(f"Feedback target repository is unavailable: {target.title}")
    return target


def normalize_kind(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized not in REPORT_KINDS:
        raise ValueError(f"Unsupported report kind {value!r}")
    return normalized


def normalize_status(value: str, *, verified: bool) -> str:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return "open" if verified else "needs-reproduction"
    if normalized not in REPORT_STATUSES:
        raise ValueError(f"Unsupported report status {value!r}")
    if normalized == "open" and not verified:
        return "needs-reproduction"
    return normalized


def slugify(value: str, *, fallback: str = "integration-feedback") -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return (slug or fallback)[:72].rstrip("-")


def stable_report_id(target: str, kind: str, title: str) -> str:
    identity = json.dumps(
        {
            "target": str(target).strip().casefold(),
            "kind": str(kind).strip().casefold(),
            "title": " ".join(str(title).split()).casefold(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"lc-feedback-{digest}"


SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|passkey|token|secret|cookie|authorization|api[_ -]?key)"
    r"\s*([:=])\s*([^,\s;]+)"
)
RAW_ID_RE = re.compile(
    r"(?i)\b(wxid_[a-z0-9_]+|[a-z0-9_-]{8,}@chatroom)\b"
)
LABELED_NUMERIC_ID_RE = re.compile(
    r"(?i)\b(local_id|server_id|chat_id|message_id|msg_id|task_id)\s*[:=]\s*[a-z0-9_-]+"
)
SIGNED_URL_RE = re.compile(r"https?://[^\s<>()]+")


def sanitize_text(value: Any, *, max_chars: int = MAX_FIELD_CHARS) -> str:
    text = str(value or "").replace("\x00", "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = RAW_ID_RE.sub("<private-chat-id>", text)
    text = LABELED_NUMERIC_ID_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    home = str(Path.home())
    if home:
        text = text.replace(home, "<HOME>")

    def scrub_url(match: re.Match[str]) -> str:
        url = match.group(0)
        if "?" not in url:
            return url
        base, query = url.split("?", 1)
        if re.search(r"(?i)(token|sig|signature|key|auth|cookie|expires|skey)=", query):
            return f"{base}?<redacted>"
        return url

    text = SIGNED_URL_RE.sub(scrub_url, text)
    return text[:max_chars].rstrip()


def normalize_items(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    items: list[str] = []
    for raw in raw_items[:MAX_LIST_ITEMS]:
        if isinstance(raw, dict):
            raw = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        text = sanitize_text(raw, max_chars=4_000)
        if text and text not in items:
            items.append(text)
    return items


def source_reference_digest(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def normalize_report_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    title = sanitize_text(payload.get("title"), max_chars=240)
    if not title:
        raise ValueError("Feedback report title is required")
    target = str(payload.get("target") or "").strip().casefold()
    kind = normalize_kind(str(payload.get("kind") or ""))
    verified = bool(payload.get("verified"))
    transient = bool(payload.get("transient"))
    if transient:
        verified = False
    return {
        "target": target,
        "kind": kind,
        "title": title,
        "summary": sanitize_text(payload.get("summary")),
        "expected": sanitize_text(payload.get("expected")),
        "observed": sanitize_text(payload.get("observed")),
        "evidence": normalize_items(payload.get("evidence")),
        "acceptance": normalize_items(
            payload.get("acceptance")
            if payload.get("acceptance") is not None
            else payload.get("acceptance_criteria")
        ),
        "workaround": sanitize_text(payload.get("workaround")),
        "status": normalize_status(str(payload.get("status") or ""), verified=verified),
        "verified": verified,
        "transient": transient,
        "source_digest": source_reference_digest(str(payload.get("source_ref") or "")),
    }


def payload_fingerprint(payload: Mapping[str, Any]) -> str:
    stable = {
        key: payload.get(key)
        for key in (
            "target",
            "kind",
            "title",
            "summary",
            "expected",
            "observed",
            "evidence",
            "acceptance",
            "workaround",
            "status",
            "verified",
            "transient",
            "source_digest",
        )
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def metadata_value(markdown: str, label: str) -> str:
    match = re.search(
        rf"(?m)^- {re.escape(label)}:\s*`?([^`\n]+)`?\s*$",
        str(markdown or ""),
    )
    return match.group(1).strip() if match else ""


def markdown_section(title: str, text: str) -> list[str]:
    return [f"## {title}", "", text or "Not provided.", ""]


def markdown_list_section(title: str, items: list[str]) -> list[str]:
    lines = [f"## {title}", ""]
    lines.extend(f"- {item}" for item in items)
    if not items:
        lines.append("- Not provided.")
    lines.append("")
    return lines


def render_report(
    payload: Mapping[str, Any],
    *,
    target: FeedbackTarget,
    report_id: str,
    revision: int,
    fingerprint: str,
    created_at: str,
    updated_at: str,
) -> str:
    kind_label = {
        "bug": "Bug",
        "feature": "Feature Request",
        "handoff": "Integration Handoff",
    }[str(payload["kind"])]
    lines = [
        f"# {kind_label}: {payload['title']}",
        "",
        f"- Report ID: `{report_id}`",
        f"- Target: `{target.id}`",
        f"- Kind: `{payload['kind']}`",
        f"- Status: `{payload['status']}`",
        f"- Evidence status: `{'verified' if payload['verified'] else 'needs-reproduction'}`",
        f"- Revision: `{revision}`",
        f"- Fingerprint: `{fingerprint}`",
        f"- Created: `{created_at}`",
        f"- Updated: `{updated_at}`",
        "- Origin: `AgInTi LabCanvas`",
    ]
    if payload.get("source_digest"):
        lines.append(f"- Private source reference: `sha256:{payload['source_digest']}`")
    lines.append("")
    lines.extend(markdown_section("Summary", str(payload.get("summary") or "")))
    lines.extend(markdown_section("Expected Behavior", str(payload.get("expected") or "")))
    lines.extend(markdown_section("Observed Behavior", str(payload.get("observed") or "")))
    lines.extend(markdown_list_section("Reproduction And Evidence", list(payload.get("evidence") or [])))
    lines.extend(markdown_list_section("Acceptance Criteria", list(payload.get("acceptance") or [])))
    lines.extend(markdown_section("Current Workaround", str(payload.get("workaround") or "")))
    lines.extend(
        [
            "## Action Boundary",
            "",
            "This repository-local report does not authorize a public issue, commit, push, "
            "release, publication, payment, credential change, or other irreversible action.",
            "",
        ]
    )
    return "\n".join(lines)


def write_feedback_report(
    payload: Mapping[str, Any],
    *,
    registry: Mapping[str, FeedbackTarget] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = normalize_report_payload(payload)
    target = resolve_target(normalized["target"], registry=registry)
    report_id = stable_report_id(target.id, normalized["kind"], normalized["title"])
    filename = (
        f"{normalized['kind']}-{slugify(normalized['title'])}-{report_id.rsplit('-', 1)[-1]}.md"
    )
    report_dir = target.report_dir.resolve()
    try:
        report_dir.relative_to(target.root.resolve())
    except ValueError as exc:
        raise ValueError("Feedback report directory escaped the target repository") from exc
    if report_dir.exists() and report_dir.is_symlink():
        raise ValueError("Feedback report directory cannot be a symlink")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / filename
    previous = path.read_text(encoding="utf-8") if path.is_file() else ""
    fingerprint = payload_fingerprint(normalized)
    previous_fingerprint = metadata_value(previous, "Fingerprint")
    previous_revision = metadata_value(previous, "Revision")
    previous_created = metadata_value(previous, "Created")
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    if previous and previous_fingerprint == fingerprint:
        return {
            "ok": True,
            "target": target.id,
            "kind": normalized["kind"],
            "report_id": report_id,
            "path": str(path),
            "created": False,
            "changed": False,
            "revision": int(previous_revision or 1),
            "verified": normalized["verified"],
            "status": normalized["status"],
        }
    revision = int(previous_revision or 0) + 1
    created_at = previous_created or timestamp
    markdown = render_report(
        normalized,
        target=target,
        report_id=report_id,
        revision=revision,
        fingerprint=fingerprint,
        created_at=created_at,
        updated_at=timestamp,
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=report_dir,
        prefix=f".{filename}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(markdown)
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return {
        "ok": True,
        "target": target.id,
        "kind": normalized["kind"],
        "report_id": report_id,
        "path": str(path),
        "created": not bool(previous),
        "changed": True,
        "revision": revision,
        "verified": normalized["verified"],
        "status": normalized["status"],
    }


def load_payload_file(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Feedback payload must be one JSON object")
    return data


def payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = load_payload_file(args.payload) if args.payload else {}
    overrides = {
        "target": args.target,
        "kind": args.kind,
        "title": args.title,
        "summary": args.summary,
        "expected": args.expected,
        "observed": args.observed,
        "evidence": args.evidence,
        "acceptance": args.acceptance,
        "workaround": args.workaround,
        "source_ref": args.source_ref,
        "status": args.status,
    }
    for key, value in overrides.items():
        if value not in (None, "", []):
            payload[key] = value
    if args.verified:
        payload["verified"] = True
    return payload


def cmd_feedback_targets(args: argparse.Namespace) -> int:
    rows = [
        {
            "id": target.id,
            "title": target.title,
            "available": target.root.is_dir(),
            "report_dir": str(target.report_dir),
        }
        for target in target_registry().values()
    ]
    payload = {"ok": all(row["available"] for row in rows), "targets": rows}
    emit(payload, bool(args.json))
    return 0


def cmd_feedback_write(args: argparse.Namespace) -> int:
    try:
        payload = payload_from_args(args)
        result = write_feedback_report(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
        emit(result, bool(args.json))
        return 1
    emit(result, bool(args.json))
    return 0


def cmd_feedback_list(args: argparse.Namespace) -> int:
    try:
        target = resolve_target(args.target)
    except ValueError as exc:
        emit({"ok": False, "error": str(exc)}, bool(args.json))
        return 1
    reports = []
    if target.report_dir.is_dir():
        for path in sorted(target.report_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            kind = metadata_value(text, "Kind")
            if args.kind and kind != args.kind:
                continue
            reports.append(
                {
                    "path": str(path),
                    "report_id": metadata_value(text, "Report ID"),
                    "kind": kind,
                    "status": metadata_value(text, "Status"),
                    "revision": int(metadata_value(text, "Revision") or 1),
                    "updated_at": metadata_value(text, "Updated"),
                }
            )
    emit({"ok": True, "target": target.id, "reports": reports}, bool(args.json))
    return 0


def emit(payload: Mapping[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if payload.get("ok") is False:
        print(f"error: {payload.get('error') or 'feedback operation failed'}")
        return
    if "targets" in payload:
        for row in payload["targets"]:
            marker = "ready" if row["available"] else "missing"
            print(f"{marker:7} {row['id']}: {row['title']} -> {row['report_dir']}")
        return
    if "reports" in payload:
        for row in payload["reports"]:
            print(
                f"{row['kind']:7} {row['status']:18} r{row['revision']} "
                f"{row['report_id']} {row['path']}"
            )
        return
    print(str(payload.get("path") or payload.get("report_id") or "ok"))
