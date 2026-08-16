#!/usr/bin/env python3
"""Copy a mirrored WeChat video into the Nutstore AutoPublish import folder."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any, Iterator

from file_lock import fcntl_compat as fcntl

from wechat_message_shards import (
    list_message_db_paths,
    message_db_index,
    parse_message_ref,
)
from wechat_mirror import DEFAULT_DB
import wechat_gui_send as gui


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
GUI_LOCK = PRIVATE / "wechat_gui_send.lock"
DEFAULT_AUTOPUBLISH_DIR = Path(os.environ.get("LABCANVAS_AUTOPUBLISH_DIR", "/home/lachlan/Nutstore Files/AutoPublish/AutoPublish"))
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
THUMBNAIL_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TRANSCODE_SOURCE_WINDOW_SECONDS = 120


@dataclass(frozen=True)
class VideoCandidate:
    media_id: int
    chat_name: str
    path: Path
    suffix: str
    size_bytes: int
    source_mtime: float
    updated_at: str
    status: str
    matched_by: str
    message_db: str = ""
    message_local_id: int = 0


@dataclass(frozen=True)
class VideoMessage:
    chat_name: str
    local_id: int
    create_time: int
    stems: tuple[str, ...]
    sizes: tuple[int, ...]
    thumbnail_sizes: tuple[int, ...] = ()
    thumbnail_width: int = 0
    thumbnail_height: int = 0
    message_db: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", action="append", default=[], help="Chat/group name to search. Repeatable. Defaults to all mirrored chats.")
    parser.add_argument("--source", type=Path, help="Explicit local video path. Bypasses the mirror query.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dest", type=Path, default=DEFAULT_AUTOPUBLISH_DIR)
    parser.add_argument("--title", default="", help="Output basename. _COMPLETED is appended if missing.")
    parser.add_argument("--match-token", action="append", default=[], help="Filter mirror rows by token in path/metadata. Repeatable.")
    parser.add_argument("--message-local-id", action="append", type=int, default=[], help="Use an exact WeChat video message local_id instead of the newest mirrored video. Repeatable.")
    parser.add_argument(
        "--message-ref",
        action="append",
        default=[],
        help="Use an exact rotated message reference as message_N.db:local_id. Repeatable.",
    )
    parser.add_argument("--since-minutes", type=float, default=180, help="Only use mirror rows updated or modified recently. Default: 180.")
    parser.add_argument("--limit", type=int, default=10, help="Candidate count for --list. Default: 10.")
    parser.add_argument("--sync", action="store_true", help="Run WeChat media-sync before selecting the video.")
    parser.add_argument("--fetch-gui", action="store_true", help="Open the chat in WeChat and click the latest video to make the client download it.")
    parser.add_argument("--fetch-timeout", type=float, default=90, help="Seconds to wait for GUI-triggered video cache. Default: 90.")
    parser.add_argument("--display", default=":97", help="X display running WeChat for --fetch-gui. Default: :97.")
    parser.add_argument("--video-click", default="", help="Relative x,y click inside the WeChat window for the latest visible video. Repeatable through semicolon form x,y;x,y. Default tries common recent-video positions.")
    parser.add_argument("--no-auto-source", action="store_true", help="Disable --auto-source when --sync is used.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing AutoPublish file with the same name.")
    parser.add_argument("--list", action="store_true", help="List matching candidates instead of copying.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    message_refs = parse_message_refs(args.message_ref)

    if args.sync:
        sync_chats = args.chat or configured_chats()
        if not sync_chats and not args.source:
            raise SystemExit("No chat names available for --sync. Pass --chat or start the WeChat supervisor once.")
        for chat in sync_chats:
            run_media_sync(chat, args.since_minutes, auto_source=not args.no_auto_source)

    if args.source:
        candidates = [candidate_from_source(args.source, args.chat[0] if args.chat else "manual")]
    elif args.message_local_id or message_refs:
        candidates = exact_message_candidates(
            chats=args.chat,
            since_minutes=args.since_minutes,
            message_local_ids=args.message_local_id,
            message_refs=message_refs,
            db_path=args.db,
        )
        if not candidates and args.fetch_gui and not args.dry_run:
            fetch_payload = fetch_latest_video_via_gui(
                chats=args.chat,
                since_minutes=args.since_minutes,
                display=args.display,
                timeout=args.fetch_timeout,
                video_clicks=parse_clicks(args.video_click) or default_video_clicks(),
                message_local_ids=args.message_local_id,
                message_refs=message_refs,
            )
            if fetch_payload.get("ok") and fetch_payload.get("path"):
                candidates = [
                    candidate_from_source(
                        Path(str(fetch_payload["path"])),
                        str(fetch_payload.get("chat") or (args.chat[0] if args.chat else "manual")),
                    )
                ]
            if fetch_payload.get("ok"):
                for chat in args.chat or [str(fetch_payload.get("chat") or "")]:
                    if chat:
                        run_media_sync(chat, args.since_minutes, auto_source=not args.no_auto_source)
            if not candidates:
                candidates = exact_message_candidates(
                    chats=args.chat,
                    since_minutes=args.since_minutes,
                    message_local_ids=args.message_local_id,
                    message_refs=message_refs,
                    db_path=args.db,
                )
    else:
        candidates = find_video_candidates(
            db_path=args.db,
            chats=args.chat,
            match_tokens=args.match_token,
            since_minutes=args.since_minutes,
            limit=max(args.limit, 1),
        )
        if not candidates and args.fetch_gui and not args.dry_run:
            fetch_payload = fetch_latest_video_via_gui(
                chats=args.chat,
                since_minutes=args.since_minutes,
                display=args.display,
                timeout=args.fetch_timeout,
                video_clicks=parse_clicks(args.video_click) or default_video_clicks(),
            )
            if fetch_payload.get("ok"):
                for chat in args.chat or [str(fetch_payload.get("chat") or "")]:
                    if chat:
                        run_media_sync(chat, args.since_minutes, auto_source=not args.no_auto_source)
                candidates = find_video_candidates(
                    db_path=args.db,
                    chats=args.chat,
                    match_tokens=args.match_token,
                    since_minutes=args.since_minutes,
                    limit=max(args.limit, 1),
                )

    if args.list:
        payload = {"ok": True, "count": len(candidates), "candidates": [candidate_summary(item) for item in candidates]}
        print_payload(payload, args.json, f"{len(candidates)} video candidate(s)")
        return 0

    if not candidates:
        recent_messages = recent_video_message_summary(
            args.chat,
            args.since_minutes,
            message_local_ids=args.message_local_id,
            message_refs=message_refs,
        )
        payload = {
            "ok": False,
            "error": "no matching mirrored video found",
            "recent_video_messages": recent_messages,
            "hint": "If recent_video_messages is non-empty, rerun with --fetch-gui or open/download the video in WeChat once, then rerun this command.",
        }
        print_payload(payload, args.json, payload["error"])
        return 1

    result = copy_candidate(
        candidates[0],
        dest_dir=args.dest,
        title=args.title,
        replace=args.replace,
        dry_run=args.dry_run,
    )
    print_payload(result, args.json, f"{result['status']}: {result['target_name']}")
    return 0 if result["ok"] else 1


def exact_message_candidates(
    *,
    chats: list[str],
    since_minutes: float,
    message_local_ids: list[int],
    message_refs: list[tuple[str, int]] | None = None,
    db_path: Path = DEFAULT_DB,
) -> list[VideoCandidate]:
    messages = recent_video_messages(
        chats,
        since_minutes,
        message_local_ids=message_local_ids,
        message_refs=message_refs,
    )
    candidates: list[VideoCandidate] = []
    for message in messages:
        paths = matching_video_files(message, since_minutes=since_minutes, started_at=0)
        paths.extend(mirrored_message_video_files(db_path, message))
        matched_by = (
            f"message-ref:{message.message_db}:{message.local_id}"
            if message.message_db
            else f"message-local-id:{message.local_id}"
        )
        for path in deduplicate_paths(paths):
            try:
                stat = path.stat()
            except OSError:
                continue
            candidates.append(
                VideoCandidate(
                    media_id=0,
                    chat_name=message.chat_name,
                    path=path.resolve(),
                    suffix=path.suffix.lower(),
                    size_bytes=stat.st_size,
                    source_mtime=stat.st_mtime,
                    updated_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    status="message-match",
                    matched_by=matched_by,
                    message_db=message.message_db,
                    message_local_id=message.local_id,
                )
            )
    message_by_key = {
        (item.chat_name, item.message_db, item.local_id): item
        for item in messages
    }
    candidates.sort(
        key=lambda item: exact_message_candidate_rank(
            item.path,
            message_by_key[(item.chat_name, item.message_db, item.message_local_id)],
        ),
        reverse=True,
    )
    return candidates


def mirrored_message_video_files(db_path: Path, message: VideoMessage) -> list[Path]:
    if not db_path.exists():
        return []
    suffixes = tuple(sorted(VIDEO_SUFFIXES))
    sql = f"""
        SELECT media_files.source_path, media_files.mirror_path,
               media_files.size_bytes, media_files.source_mtime
        FROM media_files
        JOIN chats ON chats.id = media_files.chat_id
        WHERE chats.name = ?
          AND LOWER(media_files.suffix) IN ({",".join("?" for _ in suffixes)})
          AND media_files.status IN ('copied', 'decoded', 'exists')
    """
    paths: list[Path] = []
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(sql, [message.chat_name, *suffixes]).fetchall()
    except sqlite3.Error:
        return []
    local_id_pattern = re.compile(rf"(?:^|/){message.local_id}_[^/]+$", re.IGNORECASE)
    for source_path, mirror_path, size_bytes, source_mtime in rows:
        for raw_path in (mirror_path, source_path):
            if not raw_path:
                continue
            path = Path(str(raw_path))
            name_matches = bool(local_id_pattern.search(path.as_posix()))
            size_matches = int(size_bytes or 0) in message.sizes
            time_matches = bool(
                message.create_time
                and source_mtime
                and abs(float(source_mtime) - message.create_time) <= TRANSCODE_SOURCE_WINDOW_SECONDS
            )
            stem_matches = path.stem.lower() in message.stems
            if (name_matches and (size_matches or time_matches)) or stem_matches:
                if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
                    paths.append(path)
    return deduplicate_paths(paths)


def deduplicate_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def exact_message_candidate_rank(path: Path, message: VideoMessage) -> tuple[int, int, int, int, int, float, float]:
    stat = path.stat()
    normalized = path.as_posix().lower()
    filename = path.name.lower()
    local_id_match = bool(re.match(rf"{message.local_id}(?:_|-)", filename))
    size_match = stat.st_size in message.sizes
    send_temp = "/sendtemp/" in normalized or "send_temp" in filename
    raw_original = path.stem.lower().endswith("_raw")
    stem_match = path.stem.lower() in message.stems
    time_distance = abs(stat.st_mtime - message.create_time) if message.create_time else 0.0
    return (
        int(local_id_match),
        int(size_match),
        int(send_temp or raw_original),
        int(stem_match),
        stat.st_size,
        -time_distance,
        stat.st_mtime,
    )


def run_media_sync(chat: str, since_minutes: float, *, auto_source: bool) -> None:
    command = [
        sys.executable,
        str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_media_sync.py"),
        "--chat",
        chat,
        "--since-minutes",
        str(since_minutes),
        "--summary-only",
        "--record-empty",
    ]
    if auto_source:
        command.append("--auto-source")
    subprocess.run(command, cwd=ROOT, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def configured_chats() -> list[str]:
    private = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
    names: list[str] = []
    for config in sorted(private.glob("*-direct-chatops.local.json")):
        try:
            name = json.loads(config.read_text(encoding="utf-8")).get("chat_name") or ""
        except (OSError, json.JSONDecodeError):
            name = ""
        if name and name not in names:
            names.append(str(name))
    return names


def load_direct_config(chat: str) -> dict[str, Any]:
    private = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
    for config in sorted(private.glob("*-direct-chatops.local.json")):
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("chat_name") or "") == chat:
            return payload
    return {}


def find_video_candidates(
    *,
    db_path: Path,
    chats: list[str],
    match_tokens: list[str],
    since_minutes: float,
    limit: int,
) -> list[VideoCandidate]:
    if not db_path.exists():
        return []
    cutoff_epoch = (datetime.now() - timedelta(minutes=since_minutes)).timestamp()
    cutoff_iso = datetime.fromtimestamp(cutoff_epoch).isoformat(timespec="seconds")
    suffixes = tuple(sorted(VIDEO_SUFFIXES))
    where = [
        "LOWER(media_files.suffix) IN ({})".format(",".join("?" for _ in suffixes)),
        "media_files.status IN ('copied', 'decoded', 'exists')",
        "(COALESCE(media_files.source_mtime, 0) >= ? OR media_files.updated_at >= ?)",
    ]
    params: list[object] = list(suffixes) + [cutoff_epoch, cutoff_iso]
    if chats:
        where.append("chats.name IN ({})".format(",".join("?" for _ in chats)))
        params.extend(chats)
    for token in match_tokens:
        lowered = f"%{token.lower()}%"
        where.append(
            "(LOWER(media_files.source_path) LIKE ? OR LOWER(media_files.mirror_path) LIKE ? OR LOWER(media_files.metadata_json) LIKE ?)"
        )
        params.extend([lowered, lowered, lowered])
    sql = f"""
        SELECT media_files.id, chats.name, media_files.mirror_path, media_files.suffix,
               media_files.size_bytes, media_files.source_mtime, media_files.updated_at,
               media_files.status, media_files.matched_by
        FROM media_files
        JOIN chats ON chats.id = media_files.chat_id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(media_files.source_mtime, 0) DESC, media_files.updated_at DESC
        LIMIT ?
    """
    params.append(max(limit * 4, limit))
    candidates: list[VideoCandidate] = []
    with sqlite3.connect(db_path) as conn:
        for row in conn.execute(sql, params):
            candidate = VideoCandidate(
                media_id=int(row[0]),
                chat_name=str(row[1]),
                path=Path(str(row[2])),
                suffix=str(row[3] or "").lower(),
                size_bytes=int(row[4] or 0),
                source_mtime=float(row[5] or 0.0),
                updated_at=str(row[6] or ""),
                status=str(row[7] or ""),
                matched_by=str(row[8] or ""),
            )
            if candidate.path.is_file():
                candidates.append(candidate)
            if len(candidates) >= limit:
                break
    return candidates


def candidate_from_source(path: Path, chat_name: str) -> VideoCandidate:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SystemExit(f"Source video not found: {path}")
    suffix = resolved.suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise SystemExit(f"Unsupported video suffix: {suffix or '<none>'}")
    stat = resolved.stat()
    return VideoCandidate(
        media_id=0,
        chat_name=chat_name,
        path=resolved,
        suffix=suffix,
        size_bytes=stat.st_size,
        source_mtime=stat.st_mtime,
        updated_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        status="manual",
        matched_by="source",
    )


def fetch_latest_video_via_gui(
    *,
    chats: list[str],
    since_minutes: float,
    display: str,
    timeout: float,
    video_clicks: list[tuple[int, int]],
    message_local_ids: list[int] | None = None,
    message_refs: list[tuple[str, int]] | None = None,
) -> dict:
    messages = recent_video_messages(
        chats,
        since_minutes,
        message_local_ids=message_local_ids,
        message_refs=message_refs,
    )
    if not messages:
        return {"ok": False, "error": "no recent video message"}
    message = messages[0]
    existing = matching_video_files(message, since_minutes=since_minutes, started_at=0)
    if existing:
        return {"ok": True, "chat": message.chat_name, "status": "already-cached", "name": existing[0].name, "path": str(existing[0])}
    start = time.time()
    deadline = time.monotonic() + max(1.0, timeout)
    attempts: list[dict[str, object]] = []
    click_points = video_clicks or default_video_clicks()
    per_click_wait = max(2.0, float(os.environ.get("WECHAT_AUTOPUBLISH_VIDEO_CLICK_WAIT_SECONDS", "12")))
    strict_identity = bool(message_local_ids or message_refs)
    try:
        with exclusive_gui_lock(GUI_LOCK, timeout_seconds=max(1.0, deadline - time.monotonic())):
            try:
                matched_attempts = open_chat_and_click_exact_video(
                    message,
                    display=display,
                    deadline=deadline,
                )
            except RuntimeError as exc:
                return {"ok": False, "chat": message.chat_name, "error": str(exc), "attempts": attempts}
            attempts.extend(matched_attempts)
            if not matched_attempts and strict_identity:
                return {
                    "ok": False,
                    "chat": message.chat_name,
                    "error": "exact source video thumbnail was not visible in the guarded chat history",
                    "attempts": attempts,
                }
            if not matched_attempts and not strict_identity:
                for click_point in click_points:
                    if time.monotonic() >= deadline:
                        break
                    open_chat_and_click_video(message.chat_name, display=display, video_click=click_point)
                    attempts.append({"click": click_point, "method": "legacy-point", "at": datetime.now().isoformat(timespec="seconds")})
                    click_deadline = min(deadline, time.monotonic() + per_click_wait)
                    match = wait_for_matching_video(
                        message,
                        since_minutes=since_minutes,
                        started_at=start,
                        deadline=click_deadline,
                        strict_identity=False,
                    )
                    if match:
                        return fetched_payload(message, match, attempts)
            elif matched_attempts:
                match = wait_for_matching_video(
                    message,
                    since_minutes=since_minutes,
                    started_at=start,
                    deadline=deadline,
                    strict_identity=strict_identity,
                )
                if match:
                    return fetched_payload(message, match, attempts)
    except TimeoutError as exc:
        return {"ok": False, "chat": message.chat_name, "error": str(exc), "attempts": attempts}
    return {"ok": False, "chat": message.chat_name, "error": "video cache did not appear before timeout", "attempts": attempts}


def fetched_payload(message: VideoMessage, match: Path, attempts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "ok": True,
        "chat": message.chat_name,
        "status": "fetched",
        "name": match.name,
        "bytes": match.stat().st_size,
        "path": str(match),
        "attempts": attempts,
    }


def wait_for_matching_video(
    message: VideoMessage,
    *,
    since_minutes: float,
    started_at: float,
    deadline: float,
    strict_identity: bool,
) -> Path | None:
    while time.monotonic() < deadline:
        matches = matching_video_files(
            message,
            since_minutes=since_minutes,
            started_at=started_at,
            strict_identity=strict_identity,
        )
        if matches:
            return matches[0]
        time.sleep(1.0)
    return None


def parse_message_refs(values: list[str]) -> list[tuple[str, int]]:
    refs: list[tuple[str, int]] = []
    for raw in values:
        try:
            ref = parse_message_ref(raw)
        except ValueError as exc:
            raise SystemExit(f"Invalid --message-ref {raw!r}; {exc}") from exc
        if ref not in refs:
            refs.append(ref)
    return refs


def available_message_db_paths(message_db_dir: Path, *, names: set[str] | None = None) -> list[Path]:
    return list_message_db_paths(message_db_dir, names=names)


def recent_video_messages(
    chats: list[str],
    since_minutes: float,
    *,
    message_local_ids: list[int] | None = None,
    message_refs: list[tuple[str, int]] | None = None,
    message_db_dir: Path | None = None,
    per_table_limit: int = 3,
) -> list[VideoMessage]:
    private = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
    db_dir = message_db_dir or (private / "wechat_decrypt" / "decrypted" / "message")
    ref_map: dict[str, set[int]] = {}
    for db_name, local_id in message_refs or []:
        try:
            parsed_db, parsed_local_id = parse_message_ref(f"{db_name}:{local_id}")
        except ValueError:
            continue
        ref_map.setdefault(parsed_db, set()).add(parsed_local_id)
    db_paths = available_message_db_paths(db_dir, names=set(ref_map) or None)
    if not db_paths:
        return []
    cutoff = int((datetime.now() - timedelta(minutes=since_minutes)).timestamp())
    allowed = set(chats)
    messages: list[VideoMessage] = []
    configs: list[tuple[str, str]] = []
    for config in sorted(private.glob("*-direct-chatops.local.json")):
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        chat_name = str(payload.get("chat_name") or "")
        table = str(payload.get("message_table") or "")
        if allowed and chat_name not in allowed:
            continue
        if not table.replace("_", "").isalnum():
            continue
        configs.append((chat_name, table))
    for db_path in db_paths:
        paired_ids = sorted(ref_map.get(db_path.name) or [])
        if ref_map and not paired_ids:
            continue
        legacy_ids = sorted({int(item) for item in (message_local_ids or []) if int(item) > 0})
        selected_ids = paired_ids if ref_map else legacy_ids
        with sqlite3.connect(db_path) as conn:
            for chat_name, table in configs:
                try:
                    local_id_filter = ""
                    params: list[object] = [cutoff]
                    if selected_ids:
                        local_id_filter = " AND local_id IN ({})".format(",".join("?" for _ in selected_ids))
                        params.extend(selected_ids)
                    params.append(max(1, int(per_table_limit)))
                    rows = conn.execute(
                        f"""
                        SELECT local_id, create_time, message_content, source, packed_info_data
                        FROM {table}
                        WHERE create_time >= ? AND (local_type & 4294967295) = 43{local_id_filter}
                        ORDER BY create_time DESC
                        LIMIT ?
                        """,
                        params,
                    ).fetchall()
                except sqlite3.Error:
                    continue
                for row in rows:
                    stems, sizes = parse_video_metadata(row[2], row[3], row[4])
                    thumbnail_sizes, thumbnail_width, thumbnail_height = parse_video_thumbnail_metadata(
                        row[2], row[3], row[4]
                    )
                    messages.append(
                        VideoMessage(
                            chat_name=chat_name,
                            local_id=int(row[0] or 0),
                            create_time=int(row[1] or 0),
                            stems=tuple(stems),
                            sizes=tuple(sizes),
                            thumbnail_sizes=tuple(thumbnail_sizes),
                            thumbnail_width=thumbnail_width,
                            thumbnail_height=thumbnail_height,
                            message_db=db_path.name,
                        )
                    )
    unique: dict[tuple[str, str, int, int], VideoMessage] = {}
    for message in messages:
        unique[(message.chat_name, message.message_db, message.local_id, message.create_time)] = message
    messages = list(unique.values())
    messages.sort(key=lambda item: (item.create_time, message_db_index(item.message_db)), reverse=True)
    return messages


def parse_video_metadata(message_content: Any, source: Any, packed_info_data: Any) -> tuple[list[str], list[int]]:
    text = "\n".join(decode_blob(item) for item in (message_content, source, packed_info_data))
    stems: list[str] = []
    sizes: list[int] = []
    for key in ("md5", "newmd5", "rawmd5", "originsourcemd5"):
        for value in re.findall(rf'{key}="([0-9a-fA-F]{{32}})"', text):
            add_unique(stems, value.lower())
    for value in re.findall(r"\b([0-9a-fA-F]{32})\b", text):
        add_unique(stems, value.lower())
    for key in ("length", "rawlength", "cdnvideourl_size"):
        for value in re.findall(rf'{key}="([0-9]+)"', text):
            number = int(value)
            if number > 1024:
                add_unique(sizes, number)
    return stems, sizes


def parse_video_thumbnail_metadata(
    message_content: Any,
    source: Any,
    packed_info_data: Any,
) -> tuple[list[int], int, int]:
    text = "\n".join(decode_blob(item) for item in (message_content, source, packed_info_data))
    sizes: list[int] = []
    for value in re.findall(r'cdnthumblength="([0-9]+)"', text):
        number = int(value)
        if number > 0:
            add_unique(sizes, number)
    width_match = re.search(r'cdnthumbwidth="([0-9]+)"', text)
    height_match = re.search(r'cdnthumbheight="([0-9]+)"', text)
    return (
        sizes,
        int(width_match.group(1)) if width_match else 0,
        int(height_match.group(1)) if height_match else 0,
    )


def decode_blob(value: Any) -> str:
    if value is None:
        return ""
    data = value.encode("utf-8", errors="ignore") if isinstance(value, str) else bytes(value)
    if not data:
        return ""
    if data.startswith(b"\x28\xb5\x2f\xfd"):
        try:
            proc = subprocess.run(["zstd", "-q", "-dc"], input=data, capture_output=True, check=True)
            return proc.stdout.decode("utf-8", errors="ignore")
        except (OSError, subprocess.CalledProcessError):
            return data.decode("utf-8", errors="ignore")
    return data.decode("utf-8", errors="ignore")


def matching_video_files(
    message: VideoMessage,
    *,
    since_minutes: float,
    started_at: float,
    strict_identity: bool = True,
) -> list[Path]:
    cutoff = (datetime.now() - timedelta(minutes=since_minutes)).timestamp()
    month = datetime.fromtimestamp(message.create_time).strftime("%Y-%m") if message.create_time else ""
    roots = video_roots(month)
    thumbnail_stems = {
        thumbnail_video_stem(path)
        for path in message_thumbnail_files(message)
    }
    matches: list[Path] = []
    for root in roots:
        for path in root.iterdir() if root.is_dir() else []:
            if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime < cutoff:
                continue
            stem_match = path.stem.lower() in message.stems or path.stem.lower() in thumbnail_stems
            size_match = stat.st_size in message.sizes
            new_match = bool(not strict_identity and started_at and stat.st_mtime >= started_at)
            if stem_match or size_match or new_match:
                matches.append(path)
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return matches


def message_thumbnail_files(message: VideoMessage) -> list[Path]:
    month = datetime.fromtimestamp(message.create_time).strftime("%Y-%m") if message.create_time else ""
    matches: list[Path] = []
    for root in video_roots(month):
        for path in root.iterdir() if root.is_dir() else []:
            if not path.is_file() or path.suffix.lower() not in THUMBNAIL_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            size_match = bool(message.thumbnail_sizes and stat.st_size in message.thumbnail_sizes)
            time_match = bool(
                message.create_time
                and abs(stat.st_mtime - message.create_time) <= TRANSCODE_SOURCE_WINDOW_SECONDS
            )
            if "thumb" in path.stem.lower() and size_match and time_match:
                matches.append(path)
    matches.sort(
        key=lambda item: (
            int(item.stat().st_size in message.thumbnail_sizes),
            -abs(item.stat().st_mtime - message.create_time),
        ),
        reverse=True,
    )
    return matches


def thumbnail_video_stem(path: Path) -> str:
    return re.sub(r"(?:[_-]?thumb(?:nail)?)$", "", path.stem.lower())


def video_roots(month: str) -> list[Path]:
    base = Path.home() / "Documents" / "xwechat_files"
    roots: list[Path] = []
    if not base.exists():
        return roots
    for profile in base.iterdir():
        root = profile / "msg" / "video"
        if month:
            root = root / month
        if root.is_dir():
            roots.append(root)
    return roots


def open_chat_and_click_exact_video(
    message: VideoMessage,
    *,
    display: str,
    deadline: float,
) -> list[dict[str, object]]:
    thumbnails = message_thumbnail_files(message)
    if not thumbnails:
        return []
    env = gui_environment(display)
    window = find_wechat_window(env)
    if not window:
        raise RuntimeError(f"No visible WeChat window found on DISPLAY={display}")
    open_chat(message.chat_name, env=env, window=window)
    evidence_dir = (
        ROOT
        / "output"
        / "wechat_gui_agent"
        / "video_fetch"
        / f"{safe_filename(message.chat_name)}-{message.message_db or 'message'}-{message.local_id}"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    max_pages = max(1, int(os.environ.get("WECHAT_AUTOPUBLISH_VIDEO_SCAN_PAGES", "10")))
    threshold = float(os.environ.get("WECHAT_AUTOPUBLISH_VIDEO_TEMPLATE_THRESHOLD", "0.52"))
    best_score = 0.0
    for page in range(max_pages):
        if time.monotonic() >= deadline:
            break
        screenshot_path = evidence_dir / f"page-{page:02d}.png"
        capture_window(env, window, screenshot_path)
        for thumbnail in thumbnails:
            match = match_thumbnail_in_chat(
                screenshot_path,
                thumbnail,
                window_width=window[3],
                window_height=window[4],
            )
            if not match:
                continue
            best_score = max(best_score, float(match["score"]))
            if float(match["score"]) < threshold:
                continue
            point = (int(match["center_x"]), int(match["center_y"]))
            click(env, window[1] + point[0], window[2] + point[1])
            return [
                {
                    "click": point,
                    "method": "exact-thumbnail-template",
                    "score": round(float(match["score"]), 4),
                    "thumbnail": thumbnail.name,
                    "page": page,
                    "screenshot": str(screenshot_path),
                    "at": datetime.now().isoformat(timespec="seconds"),
                }
            ]
        scroll_chat_history_up(env, window)
        time.sleep(0.65)
    raise RuntimeError(
        "exact source video thumbnail was not found after guarded history scan "
        f"(best template score {best_score:.3f})"
    )


def match_thumbnail_in_chat(
    screenshot_path: Path,
    thumbnail_path: Path,
    *,
    window_width: int,
    window_height: int,
) -> dict[str, float | int] | None:
    try:
        import cv2
    except ImportError:
        return None
    screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
    thumbnail = cv2.imread(str(thumbnail_path), cv2.IMREAD_COLOR)
    if screen is None or thumbnail is None:
        return None
    height, width = screen.shape[:2]
    width = min(width, window_width)
    height = min(height, window_height)
    left = min(width - 1, max(0, int(width * 0.35)))
    top = min(height - 1, max(0, int(height * 0.12)))
    right = width
    bottom = min(height, max(top + 1, int(height * 0.82)))
    roi = screen[top:bottom, left:right]
    if roi.size == 0:
        return None
    best: dict[str, float | int] | None = None
    for scale in (0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.0, 1.05, 1.15):
        candidate_width = max(8, int(thumbnail.shape[1] * scale))
        candidate_height = max(8, int(thumbnail.shape[0] * scale))
        if candidate_width > roi.shape[1] or candidate_height > roi.shape[0]:
            continue
        resized = cv2.resize(thumbnail, (candidate_width, candidate_height), interpolation=cv2.INTER_AREA)
        scores = cv2.matchTemplate(roi, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(scores)
        current = {
            "score": float(score),
            "center_x": int(left + location[0] + candidate_width / 2),
            "center_y": int(top + location[1] + candidate_height / 2),
            "width": candidate_width,
            "height": candidate_height,
            "scale": scale,
        }
        if best is None or float(current["score"]) > float(best["score"]):
            best = current
    return best


def scroll_chat_history_up(env: dict[str, str], window: tuple[str, int, int, int, int]) -> None:
    x = window[1] + int(window[3] * 0.68)
    y = window[2] + int(window[4] * 0.42)
    run(
        [
            "xdotool",
            "mousemove",
            str(x),
            str(y),
            "click",
            "--repeat",
            "6",
            "--delay",
            "70",
            "4",
        ],
        env=env,
    )


def capture_window(env: dict[str, str], window: tuple[str, int, int, int, int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["import", "-window", window[0], str(path)], env=env)


def open_chat_and_click_video(chat: str, *, display: str, video_click: tuple[int, int]) -> None:
    env = gui_environment(display)
    window = find_wechat_window(env)
    if not window:
        raise RuntimeError(f"No visible WeChat window found on DISPLAY={display}")
    open_chat(chat, env=env, window=window)
    click(env, window[1] + video_click[0], window[2] + video_click[1])


def open_chat(
    chat: str,
    *,
    env: dict[str, str],
    window: tuple[str, int, int, int, int],
) -> None:
    targets_file = PRIVATE / "wechat_send_targets.local.json"
    targets, _ = gui.load_targets([chat], targets_file if targets_file.exists() else None, "")
    if len(targets) != 1:
        raise RuntimeError(f"No unique guarded WeChat target is configured for {chat}")
    target = targets[0]
    out_dir = ROOT / "output" / "wechat_gui_agent" / "video_fetch" / safe_filename(chat) / "chat-open"
    out_dir.mkdir(parents=True, exist_ok=True)
    gui_window = gui.Window(window[0], window[1], window[2], window[3], window[4])
    gui.focus(env, gui_window)
    guard = gui.open_target(
        env,
        gui_window,
        target,
        pause=0.45,
        out_dir=out_dir,
        shot_prefix="exact-video",
        skip_title_guard=False,
        prefer_current=True,
        allow_search=True,
        relaxed_visible_fallback_allowed=target.allow_title_guard_fallback,
    )
    if not guard.get("ok"):
        method = str(guard.get("method") or "unknown")
        observed = str(guard.get("ocr_text") or "").strip().replace("\n", " ")
        raise RuntimeError(
            f"Could not open exact WeChat chat {chat!r} (method={method}, observed={observed[:160]!r})"
        )


def gui_environment(display: str) -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    return env


@contextmanager
def exclusive_gui_lock(path: Path, *, timeout_seconds: float) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "WECHAT_SEND_BUSY: exact video fetch could not acquire the shared GUI lane"
                    ) from exc
                time.sleep(0.25)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def find_wechat_window(env: dict[str, str]) -> tuple[str, int, int, int, int] | None:
    proc = run(["xdotool", "search", "--onlyvisible", "--class", "wechat"], env=env, check=False)
    best: tuple[str, int, int, int, int] | None = None
    best_area = 0
    for wid in proc.stdout.split():
        geom = run(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False).stdout
        values = dict(line.split("=", 1) for line in geom.splitlines() if "=" in line)
        try:
            x, y, width, height = (int(values.get(key, "0")) for key in ("X", "Y", "WIDTH", "HEIGHT"))
        except ValueError:
            continue
        area = width * height
        if area > best_area:
            best = (wid, x, y, width, height)
            best_area = area
    return best


def run(command: list[str], *, env: dict[str, str] | None = None, check: bool = True, input: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            env=env,
            input=input,
            text=False if input is not None else True,
            capture_output=True,
            check=check,
            timeout=float(os.environ.get("WECHAT_GUI_COMMAND_TIMEOUT", "8")),
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        stdout = exc.stdout.decode(errors="ignore") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        detail = (stderr or stdout or str(exc)).strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail[:500]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{' '.join(command)} timed out after {exc.timeout}s") from exc


def focus(env: dict[str, str], wid: str) -> None:
    proc = run(["xdotool", "windowactivate", "--sync", wid], env=env, check=False)
    if proc.returncode == 0:
        return
    proc = run(["xdotool", "windowfocus", wid], env=env, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode(errors="ignore")
        raise RuntimeError(f"Could not focus WeChat window {wid}: {stderr.strip()[:500]}")
    time.sleep(0.2)


def click(env: dict[str, str], x: int, y: int) -> None:
    run(["xdotool", "mousemove", str(x), str(y), "click", "1"], env=env)


def key(env: dict[str, str], keys: str) -> None:
    run(["xdotool", "key", "--clearmodifiers", keys], env=env)


def paste_text(env: dict[str, str], text: str) -> None:
    timeout = float(os.environ.get("WECHAT_CLIPBOARD_TIMEOUT", "6"))
    try:
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-loops", "1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except OSError as exc:
        raise RuntimeError(f"xclip failed to start: {exc}") from exc
    assert proc.stdin is not None
    proc.stdin.write(text)
    proc.stdin.close()
    time.sleep(0.15)
    key(env, "ctrl+v")
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
        return
    stdout = proc.stdout.read() if proc.stdout else ""
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.returncode not in (0, None):
        raise RuntimeError(f"xclip failed while preparing WeChat search text: {(stderr or stdout or '').strip()[:500]}")


def parse_click(raw: Any) -> tuple[int, int] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        parts = [item.strip() for item in raw.split(",")]
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return int(raw[0]), int(raw[1])
    return None


def parse_clicks(raw: Any) -> list[tuple[int, int]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        clicks: list[tuple[int, int]] = []
        for item in raw.split(";"):
            parsed = parse_click(item.strip())
            if parsed and parsed not in clicks:
                clicks.append(parsed)
        return clicks
    parsed = parse_click(raw)
    return [parsed] if parsed else []


def default_video_clicks() -> list[tuple[int, int]]:
    raw = os.environ.get("WECHAT_AUTOPUBLISH_VIDEO_CLICKS", "")
    parsed = parse_clicks(raw)
    if parsed:
        return parsed
    return [
        (510, 430),  # common center of the newest visible video bubble
        (510, 360),
        (510, 520),
        (510, 280),  # legacy default retained as fallback
        (610, 430),
    ]


def add_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def recent_video_message_summary(
    chats: list[str],
    since_minutes: float,
    message_local_ids: list[int] | None = None,
    message_refs: list[tuple[str, int]] | None = None,
) -> list[dict]:
    messages = recent_video_messages(
        chats,
        since_minutes,
        message_local_ids=message_local_ids,
        message_refs=message_refs,
        per_table_limit=100,
    )
    by_chat: dict[str, list[VideoMessage]] = {}
    for message in messages:
        by_chat.setdefault(message.chat_name, []).append(message)
    summaries: list[dict] = []
    for chat_name, rows in sorted(by_chat.items()):
        latest = max((item.create_time for item in rows), default=0)
        refs = sorted(
            {
                f"{item.message_db}:{item.local_id}"
                for item in rows
                if item.message_db and item.local_id > 0
            }
        )
        summaries.append(
            {
                "chat": chat_name,
                "recent_video_rows": len(rows),
                "latest_video_at": datetime.fromtimestamp(latest).isoformat(timespec="seconds") if latest else "",
                "message_refs": refs,
            }
        )
    return summaries


def copy_candidate(candidate: VideoCandidate, *, dest_dir: Path, title: str, replace: bool, dry_run: bool) -> dict:
    dest_dir = dest_dir.expanduser().resolve()
    target_name = completed_filename(title or candidate.path.name, candidate.suffix)
    target = dest_dir / target_name
    payload = {
        "ok": True,
        "status": "dry-run" if dry_run else "copied",
        "chat": candidate.chat_name,
        "source_name": candidate.path.name,
        "target_name": target.name,
        "target": str(target),
        "bytes": candidate.size_bytes,
        "media_id": candidate.media_id,
    }
    if candidate.message_db:
        payload["message_ref"] = f"{candidate.message_db}:{candidate.message_local_id}"
    if dry_run:
        return payload
    if target.exists():
        if target.stat().st_size == candidate.path.stat().st_size and not replace:
            payload["status"] = "exists"
            return payload
        if not replace:
            payload.update({"ok": False, "status": "exists", "error": "target exists; pass --replace to overwrite"})
            return payload
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = dest_dir.parent / ".tmp_autopub_copy"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / (target.name + ".tmp")
    shutil.copy2(candidate.path, tmp)
    if tmp.stat().st_size != candidate.path.stat().st_size:
        tmp.unlink(missing_ok=True)
        payload.update({"ok": False, "status": "error", "error": "copied size mismatch"})
        return payload
    os.replace(tmp, target)
    return payload


def completed_filename(name: str, suffix: str) -> str:
    raw = Path(name).name
    stem = Path(raw).stem or "wechat_video"
    ext = Path(raw).suffix or suffix or ".mp4"
    stem = safe_filename(stem)
    if "_completed" not in stem.lower():
        stem = f"{stem}_COMPLETED"
    return stem + ext


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "wechat_video"


def candidate_summary(candidate: VideoCandidate) -> dict:
    payload = {
        "media_id": candidate.media_id,
        "chat": candidate.chat_name,
        "name": candidate.path.name,
        "suffix": candidate.suffix,
        "bytes": candidate.size_bytes,
        "source_mtime": candidate.source_mtime,
        "updated_at": candidate.updated_at,
        "status": candidate.status,
        "matched_by": candidate.matched_by,
    }
    if candidate.message_db:
        payload["message_ref"] = f"{candidate.message_db}:{candidate.message_local_id}"
    return payload


def print_payload(payload: dict, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    raise SystemExit(main())
