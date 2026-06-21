#!/usr/bin/env python3
"""Copy a mirrored WeChat video into the Nutstore AutoPublish import folder."""

from __future__ import annotations

import argparse
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
from typing import Any

from wechat_mirror import DEFAULT_DB


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AUTOPUBLISH_DIR = Path(os.environ.get("LABCANVAS_AUTOPUBLISH_DIR", "/home/lachlan/Nutstore Files/AutoPublish/AutoPublish"))
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


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


@dataclass(frozen=True)
class VideoMessage:
    chat_name: str
    local_id: int
    create_time: int
    stems: tuple[str, ...]
    sizes: tuple[int, ...]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", action="append", default=[], help="Chat/group name to search. Repeatable. Defaults to all mirrored chats.")
    parser.add_argument("--source", type=Path, help="Explicit local video path. Bypasses the mirror query.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dest", type=Path, default=DEFAULT_AUTOPUBLISH_DIR)
    parser.add_argument("--title", default="", help="Output basename. _COMPLETED is appended if missing.")
    parser.add_argument("--match-token", action="append", default=[], help="Filter mirror rows by token in path/metadata. Repeatable.")
    parser.add_argument("--since-minutes", type=float, default=180, help="Only use mirror rows updated or modified recently. Default: 180.")
    parser.add_argument("--limit", type=int, default=10, help="Candidate count for --list. Default: 10.")
    parser.add_argument("--sync", action="store_true", help="Run WeChat media-sync before selecting the video.")
    parser.add_argument("--fetch-gui", action="store_true", help="Open the chat in WeChat and click the latest video to make the client download it.")
    parser.add_argument("--fetch-timeout", type=float, default=90, help="Seconds to wait for GUI-triggered video cache. Default: 90.")
    parser.add_argument("--display", default=":97", help="X display running WeChat for --fetch-gui. Default: :97.")
    parser.add_argument("--video-click", default="", help="Relative x,y click inside the WeChat window for the latest visible video. Default: 510,280.")
    parser.add_argument("--no-auto-source", action="store_true", help="Disable --auto-source when --sync is used.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing AutoPublish file with the same name.")
    parser.add_argument("--list", action="store_true", help="List matching candidates instead of copying.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.sync:
        sync_chats = args.chat or configured_chats()
        if not sync_chats and not args.source:
            raise SystemExit("No chat names available for --sync. Pass --chat or start the WeChat supervisor once.")
        for chat in sync_chats:
            run_media_sync(chat, args.since_minutes, auto_source=not args.no_auto_source)

    if args.source:
        candidates = [candidate_from_source(args.source, args.chat[0] if args.chat else "manual")]
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
                video_click=parse_click(args.video_click) or (510, 280),
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
        recent_messages = recent_video_message_summary(args.chat, args.since_minutes)
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
    video_click: tuple[int, int],
) -> dict:
    messages = recent_video_messages(chats, since_minutes)
    if not messages:
        return {"ok": False, "error": "no recent video message"}
    message = messages[0]
    existing = matching_video_files(message, since_minutes=since_minutes, started_at=0)
    if existing:
        return {"ok": True, "chat": message.chat_name, "status": "already-cached", "name": existing[0].name}
    start = time.time()
    try:
        open_chat_and_click_video(message.chat_name, display=display, video_click=video_click)
    except RuntimeError as exc:
        return {"ok": False, "chat": message.chat_name, "error": str(exc)}
    deadline = time.monotonic() + max(1.0, timeout)
    while time.monotonic() < deadline:
        matches = matching_video_files(message, since_minutes=since_minutes, started_at=start)
        if matches:
            return {"ok": True, "chat": message.chat_name, "status": "fetched", "name": matches[0].name, "bytes": matches[0].stat().st_size}
        time.sleep(1.0)
    return {"ok": False, "chat": message.chat_name, "error": "video cache did not appear before timeout"}


def recent_video_messages(chats: list[str], since_minutes: float) -> list[VideoMessage]:
    private = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
    db_path = private / "wechat_decrypt" / "decrypted" / "message" / "message_0.db"
    if not db_path.exists():
        return []
    cutoff = int((datetime.now() - timedelta(minutes=since_minutes)).timestamp())
    allowed = set(chats)
    messages: list[VideoMessage] = []
    with sqlite3.connect(db_path) as conn:
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
            try:
                rows = conn.execute(
                    f"""
                    SELECT local_id, create_time, message_content, source, packed_info_data
                    FROM {table}
                    WHERE create_time >= ? AND (local_type & 4294967295) = 43
                    ORDER BY create_time DESC
                    LIMIT 3
                    """,
                    (cutoff,),
                ).fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                stems, sizes = parse_video_metadata(row[2], row[3], row[4])
                messages.append(
                    VideoMessage(
                        chat_name=chat_name,
                        local_id=int(row[0] or 0),
                        create_time=int(row[1] or 0),
                        stems=tuple(stems),
                        sizes=tuple(sizes),
                    )
                )
    messages.sort(key=lambda item: item.create_time, reverse=True)
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


def matching_video_files(message: VideoMessage, *, since_minutes: float, started_at: float) -> list[Path]:
    cutoff = (datetime.now() - timedelta(minutes=since_minutes)).timestamp()
    month = datetime.fromtimestamp(message.create_time).strftime("%Y-%m") if message.create_time else ""
    roots = video_roots(month)
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
            stem_match = path.stem.lower() in message.stems
            size_match = stat.st_size in message.sizes
            new_match = bool(started_at and stat.st_mtime >= started_at)
            if stem_match or size_match or new_match:
                matches.append(path)
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return matches


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


def open_chat_and_click_video(chat: str, *, display: str, video_click: tuple[int, int]) -> None:
    target = (load_direct_config(chat).get("send_target") or {}) if chat else {}
    query = str(target.get("query") or chat)
    result_click = parse_click(target.get("result_click")) or (165, 125)
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    window = find_wechat_window(env)
    if not window:
        raise RuntimeError(f"No visible WeChat window found on DISPLAY={display}")
    focus(env, window[0])
    click(env, window[1] + 118, window[2] + 46)
    time.sleep(0.3)
    key(env, "ctrl+a")
    key(env, "BackSpace")
    paste_text(env, query)
    time.sleep(1.2)
    click(env, window[1] + result_click[0], window[2] + result_click[1])
    time.sleep(1.0)
    click(env, window[1] + video_click[0], window[2] + video_click[1])


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
    return subprocess.run(command, env=env, input=input, text=False if input is not None else True, capture_output=True, check=check)


def focus(env: dict[str, str], wid: str) -> None:
    run(["xdotool", "windowactivate", "--sync", wid], env=env)


def click(env: dict[str, str], x: int, y: int) -> None:
    run(["xdotool", "mousemove", str(x), str(y), "click", "1"], env=env)


def key(env: dict[str, str], keys: str) -> None:
    run(["xdotool", "key", "--clearmodifiers", keys], env=env)


def paste_text(env: dict[str, str], text: str) -> None:
    proc = subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, env=env, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("xclip failed while preparing WeChat search text")
    key(env, "ctrl+v")


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


def add_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def recent_video_message_summary(chats: list[str], since_minutes: float) -> list[dict]:
    private = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
    db_path = private / "wechat_decrypt" / "decrypted" / "message" / "message_0.db"
    if not db_path.exists():
        return []
    cutoff = int((datetime.now() - timedelta(minutes=since_minutes)).timestamp())
    summaries: list[dict] = []
    allowed = set(chats)
    with sqlite3.connect(db_path) as conn:
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
            try:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*), MAX(create_time)
                    FROM {table}
                    WHERE create_time >= ? AND (local_type & 4294967295) = 43
                    """,
                    (cutoff,),
                ).fetchone()
            except sqlite3.Error:
                continue
            count = int(row[0] or 0) if row else 0
            latest = int(row[1] or 0) if row else 0
            if count:
                summaries.append(
                    {
                        "chat": chat_name,
                        "recent_video_rows": count,
                        "latest_video_at": datetime.fromtimestamp(latest).isoformat(timespec="seconds") if latest else "",
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
    return {
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


def print_payload(payload: dict, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    raise SystemExit(main())
