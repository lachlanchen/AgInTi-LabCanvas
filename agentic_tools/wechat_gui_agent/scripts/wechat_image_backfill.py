#!/usr/bin/env python3
"""Backfill recent WeChat image reads for one direct-monitor chat."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import wechat_direct_chatops as direct  # noqa: E402
import wechat_task_worker as worker  # noqa: E402


DEFAULT_CONFIG = Path(
    os.environ.get(
        "WECHAT_IMAGE_BACKFILL_CONFIG",
        str(ROOT / "agentic_tools" / "wechat_gui_agent" / ".private" / "direct-chatops.local.json"),
    )
)
DEFAULT_OUTPUT = ROOT / "output" / "wechat_image_backfill"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--history-limit", type=int, default=500)
    parser.add_argument("--include-self", action="store_true", help="Include rows sent by the configured self_wxid.")
    parser.add_argument("--send", action="store_true", help="Send the combined report to the WeChat chat.")
    parser.add_argument("--send-targets", type=Path, default=worker.DEFAULT_SEND_TARGETS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=os.environ.get("WECHAT_IMAGE_READ_MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning-effort", default=os.environ.get("WECHAT_IMAGE_READ_EFFORT", "low"))
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args()

    config = direct.load_config(args.config)
    os.environ["WECHAT_IMAGE_READ_MODEL"] = args.model
    os.environ["WECHAT_IMAGE_READ_EFFORT"] = args.reasoning_effort
    rows = direct.read_recent_history(config, 10**12, limit=max(args.history_limit, args.limit * 16))
    selected = select_recent_image_rows(config, rows, limit=args.limit, include_self=args.include_self)
    run_dir = args.output_dir / datetime.now().strftime("%Y-%m-%d") / datetime.now().strftime("%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    newest_local_id = selected[-1].get("local_id") if selected else None
    for index, row in enumerate(selected, start=1):
        artifact_dir = run_dir / f"{index:02d}-local-{row.get('local_id')}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        task = build_image_task(config, row, rows)
        if row.get("local_id") == newest_local_id:
            task.setdefault("source", {})["allow_visible_crop_fallback"] = True
        result = process_image_row(task, artifact_dir)
        result["row"] = row_public_snapshot(row)
        results.append(result)

    report = build_report(config, results)
    report_path = run_dir / "image_backfill_report.txt"
    manifest_path = run_dir / "image_backfill_manifest.json"
    report_path.write_text(report + "\n", encoding="utf-8")
    manifest = {
        "chat": config.get("chat_name"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "limit": args.limit,
        "selected_local_ids": [item.get("local_id") for item in selected],
        "report_path": str(report_path),
        "results": results,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    send_errors: list[str] = []
    if args.send and report.strip():
        send_errors = worker.send_result_with_retries(
            {"message": report, "files": [], "confirmation": ""},
            str(config.get("chat_name") or ""),
            args.send_targets,
            task={
                "id": f"image-backfill-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "chat": config.get("chat_name"),
                "route": direct.build_route_contract(config),
                "source": {"chat": config.get("chat_name")},
            },
        )
    payload = {
        "status": "sent" if args.send and not send_errors else "done",
        "send_errors": send_errors,
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "selected_count": len(selected),
        "ok_count": sum(1 for item in results if item.get("status") == "ok"),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(report)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if send_errors else 0


def select_recent_image_rows(
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    limit: int,
    include_self: bool = False,
) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for row in rows:
        base_type, _ = direct.split_message_type(row.get("local_type"))
        if base_type != 3:
            continue
        if not include_self and not direct.is_inbound_user_row(config, row):
            continue
        images.append(row)
    return images[-max(0, limit):]


def build_image_task(config: dict[str, Any], row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    local_id = row.get("local_id")
    context = nearby_rows(rows, int(local_id or 0), radius=3)
    resource_md5 = image_resource_md5(config, row)
    request = (
        "Current coalesced request:\n"
        f"Backfill image reading for WeChat image local_id={local_id}. "
        "Read the exact image with Codex vision using gpt-5.5 low. Return visible text and an image caption.\n"
        f"Resource MD5: {resource_md5 or '(missing)'}\n\n"
        "Same-chat reference media/context rows:\n"
        + direct.reference_row_context([row])
    )
    task = {
        "id": f"image-backfill-{datetime.now().strftime('%Y%m%d%H%M%S')}-{local_id}",
        "chat": config.get("chat_name"),
        "request": request,
        "status": "in_progress",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "route": direct.build_route_contract(config),
        "route_decision": {
            "route_kind": "research_or_summary",
            "worker_needed": True,
            "needs_recent_media": True,
            "source_policy": "current_plus_explicit_refs",
            "reason": "image backfill read",
        },
        "source": {
            "chat": config.get("chat_name"),
            "config_id": config.get("config_id") or "",
            "message_table": config.get("message_table") or "",
            "server_id": row.get("server_id"),
            "local_id": row.get("local_id"),
            "local_type": row.get("local_type"),
            "create_time": row.get("create_time"),
            "kind": direct.message_kind(row),
            "sender": row.get("sender"),
            "sender_display": row.get("sender_display"),
            "resource_md5": resource_md5,
        },
        "context": [
            {
                "local_id": item.get("local_id"),
                "server_id": item.get("server_id"),
                "sender": item.get("sender"),
                "sender_display": item.get("sender_display"),
                "local_type": item.get("local_type"),
                "create_time": item.get("create_time"),
                "kind": direct.message_kind(item),
                "content": item.get("content") or "",
            }
            for item in context[-8:]
        ],
    }
    worker.ensure_task_routine_contract(task)
    return task


def image_resource_md5(config: dict[str, Any], row: dict[str, Any]) -> str:
    db_path = direct.DECRYPTED / "message" / "message_resource.db"
    if not db_path.is_file():
        return ""
    chatroom_id = str(config.get("chatroom_id") or "")
    local_id = row.get("local_id")
    if not chatroom_id or local_id in (None, ""):
        return ""
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            chat_row = conn.execute("SELECT rowid FROM ChatName2Id WHERE user_name = ?", (chatroom_id,)).fetchone()
            if not chat_row:
                return ""
            resource = conn.execute(
                """
                SELECT packed_info
                FROM MessageResourceInfo
                WHERE chat_id = ? AND message_local_id = ?
                  AND (message_local_type = 3 OR message_local_type % 4294967296 = 3)
                ORDER BY message_create_time DESC
                LIMIT 1
                """,
                (chat_row[0], local_id),
            ).fetchone()
    except sqlite3.Error:
        return ""
    return extract_resource_md5(resource[0] if resource else None)


def extract_resource_md5(blob: Any) -> str:
    if not isinstance(blob, bytes):
        return ""
    marker = b"\x12\x22\x0a\x20"
    index = blob.find(marker)
    if index >= 0 and index + len(marker) + 32 <= len(blob):
        candidate = blob[index + len(marker): index + len(marker) + 32]
        try:
            text = candidate.decode("ascii").lower()
            int(text, 16)
            return text
        except (UnicodeDecodeError, ValueError):
            pass
    for match in re.finditer(rb"[0-9a-f]{32}", blob):
        try:
            text = match.group(0).decode("ascii").lower()
            int(text, 16)
            return text
        except (UnicodeDecodeError, ValueError):
            continue
    return ""


def nearby_rows(rows: list[dict[str, Any]], local_id: int, *, radius: int) -> list[dict[str, Any]]:
    if not local_id:
        return []
    for index, row in enumerate(rows):
        if int(row.get("local_id") or 0) == local_id:
            return rows[max(0, index - radius): index + radius + 1]
    return []


def process_image_row(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    resolution_task = source_scoped_resolution_task(task)
    refresh = worker.refresh_media_sync_for_task(resolution_task)
    candidates = image_candidates_for_task(resolution_task)
    gui_cache_probe: dict[str, Any] = {}
    second_refresh: dict[str, Any] = {}
    gui_reason = worker.media_gui_cache_probe_reason(resolution_task, candidates)
    allow_visible_crop = bool((task.get("source") or {}).get("allow_visible_crop_fallback"))
    if gui_reason and allow_visible_crop and worker.should_probe_gui_media_cache(resolution_task):
        gui_cache_probe = worker.materialize_chat_for_media_cache(resolution_task, artifact_dir)
        gui_cache_probe["reason"] = gui_reason
        second_refresh = worker.refresh_media_sync_for_task(resolution_task)
        candidates = image_candidates_for_task(resolution_task)
        crop_candidates = worker.gui_probe_image_crop_candidates(resolution_task, candidates, gui_cache_probe)
        if crop_candidates:
            candidates.extend(crop_candidates)
    best = best_image_candidate(candidates)
    copied: dict[str, Any] = {}
    skipped: list[dict[str, str]] = []
    if best:
        copied = copy_and_read_candidate(best, artifact_dir)
    else:
        skipped.append({"reason": "no_source_scoped_image_candidate"})
    manifest = {
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "source": task.get("source"),
        "status": "ok" if copied else "missing",
        "refresh": refresh,
        "second_refresh": second_refresh,
        "gui_cache_probe": gui_cache_probe,
        "tokens": worker.extract_media_tokens_from_task(resolution_task),
        "source_windows": worker.task_media_source_windows(resolution_task),
        "candidate_count": len(candidates),
        "selected": copied,
        "skipped": skipped,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "policy": "last-image backfill uses same-chat local_id/media tokens/time window and reads one best image candidate",
    }
    manifest_json = artifact_dir / "image_backfill_manifest.json"
    manifest_md = artifact_dir / "image_backfill_manifest.md"
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest_md.write_text(image_manifest_markdown(manifest), encoding="utf-8")
    return {
        "status": manifest["status"],
        "manifest_json": str(manifest_json),
        "manifest_md": str(manifest_md),
        "selected": copied,
        "candidate_count": len(candidates),
    }


def source_scoped_resolution_task(task: dict[str, Any]) -> dict[str, Any]:
    """Return a media-resolution task scoped only to the source image row.

    Nearby chat rows are useful for human context, but they must not widen the
    media timestamp window or a backfill can borrow a neighboring image.
    """
    scoped = dict(task)
    scoped["context"] = []
    return scoped


def image_candidates_for_task(task: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = worker.resolve_synced_media_from_mirror(task, limit=48, suffixes=set(worker.OCR_IMAGE_SUFFIXES))
    resource_md5 = str((task.get("source") or {}).get("resource_md5") or "").lower()
    if not resource_md5:
        return candidates
    exact = [item for item in candidates if candidate_matches_resource_md5(item, resource_md5)]
    return exact or candidates


def candidate_matches_resource_md5(item: dict[str, Any], resource_md5: str) -> bool:
    text = " ".join(
        str(value or "").lower()
        for value in (
            item.get("source_path"),
            item.get("mirror_path"),
            item.get("matched_by"),
            item.get("metadata"),
        )
    )
    return bool(resource_md5 and resource_md5 in text)


def best_image_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    readable = []
    for item in candidates:
        path = Path(str(item.get("mirror_path") or "")).expanduser()
        if not path.is_file():
            continue
        suffix = str(item.get("suffix") or path.suffix).lower()
        if suffix not in worker.OCR_IMAGE_SUFFIXES:
            continue
        readable.append(item)
    if not readable:
        return None
    return max(readable, key=image_candidate_score)


def image_candidate_score(item: dict[str, Any]) -> tuple[float, int, int, float, str]:
    path = Path(str(item.get("mirror_path") or "")).expanduser()
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    path_text = path.as_posix().lower()
    stem = path.stem.lower()
    score = float(item.get("score") or 0)
    if "/img/" in path_text and not re.search(r"_(?:t|h|b|w)$", stem):
        score += 80
    if "/bubble/" in path_text:
        score += 30
    if "/thumb/" in path_text or stem.endswith("_thumb"):
        score -= 80
    if re.search(r"_(?:t|h|w)$", stem):
        score -= 60
    metadata = worker.image_file_metadata(path)
    if metadata.get("status") == "ok":
        score += 500
        width = int(metadata.get("width") or 0)
        height = int(metadata.get("height") or 0)
        if image_looks_like_placeholder(path):
            score -= 380
    else:
        score -= 500
        width = 0
        height = 0
    return score, width * height, size, float(item.get("source_mtime") or 0.0), path.name


def image_looks_like_placeholder(path: Path) -> bool:
    try:
        from PIL import Image, ImageFile, ImageStat
    except Exception:
        return False
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stat = ImageStat.Stat(rgb)
    except Exception:
        return False
    mean = [float(item) for item in stat.mean]
    stddev = [float(item) for item in stat.stddev]
    avg_std = sum(stddev) / len(stddev)
    gray_spread = max(mean) - min(mean)
    gray_mean = sum(mean) / len(mean)
    return avg_std < 45.0 and gray_spread < 8.0 and 80.0 <= gray_mean <= 180.0


def copy_and_read_candidate(candidate: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    source = Path(str(candidate.get("mirror_path") or "")).expanduser()
    source_dir = artifact_dir / "source_media"
    source_dir.mkdir(parents=True, exist_ok=True)
    target = worker.unique_intake_target(source_dir, source.name, index=1)
    shutil.copy2(source, target)
    selected = {
        **candidate,
        "task_copy_path": str(target),
        "filename": source.name,
        "suffix": source.suffix.lower(),
        "size_bytes": target.stat().st_size,
        "sha256": worker.sha256_file(target),
    }
    metadata = worker.image_file_metadata(target)
    selected["image_metadata"] = metadata
    selected["quality_flags"] = {"placeholder_like": image_looks_like_placeholder(target)}
    if metadata.get("status") in {"ok", "metadata_unavailable"}:
        selected["vision"] = worker.codex_read_image_file(target, artifact_dir / "image_text")
        selected["ocr"] = worker.ocr_image_file(target, artifact_dir / "image_text")
    else:
        selected["vision"] = {"status": "skipped", "reason": metadata.get("status") or "image_unreadable"}
        selected["ocr"] = {"status": "skipped", "reason": metadata.get("status") or "image_unreadable"}
    return selected


def row_public_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "local_id": row.get("local_id"),
        "server_id": row.get("server_id"),
        "local_type": row.get("local_type"),
        "kind": direct.message_kind(row),
        "sender_display": row.get("sender_display"),
        "create_time": row.get("create_time"),
        "visible": direct.visible_message_text(row),
    }


def build_report(config: dict[str, Any], results: list[dict[str, Any]]) -> str:
    chat = str(config.get("chat_name") or "chat")
    lines = [f"已回填读取 {chat} 最近 {len(results)} 张图片："]
    for index, result in enumerate(results, start=1):
        row = result.get("row") if isinstance(result.get("row"), dict) else {}
        selected = result.get("selected") if isinstance(result.get("selected"), dict) else {}
        local_id = row.get("local_id") or "?"
        metadata = selected.get("image_metadata") if isinstance(selected.get("image_metadata"), dict) else {}
        dims = ""
        if metadata.get("width") and metadata.get("height"):
            dims = f"{metadata.get('width')}x{metadata.get('height')}"
        vision = selected.get("vision") if isinstance(selected.get("vision"), dict) else {}
        ocr = selected.get("ocr") if isinstance(selected.get("ocr"), dict) else {}
        text = str(vision.get("text_preview") or "").strip()
        if not text:
            text = str(ocr.get("text_preview") or "").strip()
        if not text:
            text = "未读到清晰文字或图像说明。"
        lines.append(f"{index}. local_id={local_id} {dims}".rstrip())
        lines.append(truncate_for_chat(text, 650))
    return "\n\n".join(lines).strip()


def image_manifest_markdown(manifest: dict[str, Any]) -> str:
    selected = manifest.get("selected") if isinstance(manifest.get("selected"), dict) else {}
    lines = [
        "# WeChat Image Backfill",
        "",
        f"- Task: `{manifest.get('task_id') or ''}`",
        f"- Chat: `{manifest.get('chat') or ''}`",
        f"- Status: `{manifest.get('status') or ''}`",
        f"- Candidate count: `{manifest.get('candidate_count') or 0}`",
        "",
        "## Selected Image",
    ]
    if selected:
        lines.append(f"- Path: `{selected.get('task_copy_path') or ''}`")
        lines.append(f"- SHA256: `{selected.get('sha256') or ''}`")
        metadata = selected.get("image_metadata") if isinstance(selected.get("image_metadata"), dict) else {}
        if metadata:
            lines.append(f"- Metadata: `{metadata.get('status')}` {metadata.get('width')}x{metadata.get('height')} {metadata.get('format')}")
        vision = selected.get("vision") if isinstance(selected.get("vision"), dict) else {}
        if vision:
            lines.append(f"- Codex image read: `{vision.get('status')}` `{vision.get('text_path') or ''}`")
            if vision.get("text_preview"):
                lines.append("")
                lines.append("```text")
                lines.append(str(vision.get("text_preview") or ""))
                lines.append("```")
        ocr = selected.get("ocr") if isinstance(selected.get("ocr"), dict) else {}
        if ocr:
            lines.append(f"- OCR: `{ocr.get('status')}` `{ocr.get('text_path') or ''}`")
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def truncate_for_chat(text: str, limit: int) -> str:
    value = re.sub(r"\n{3,}", "\n\n", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
