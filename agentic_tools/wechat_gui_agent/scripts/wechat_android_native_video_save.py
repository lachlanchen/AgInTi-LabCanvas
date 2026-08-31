#!/usr/bin/env python3
"""Save one exact WeChat video through the native album export and pull it."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
ANDROID_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"
for directory in (SCRIPTS, ANDROID_SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from android_control_lease import priority_android_control  # noqa: E402
from wechat_android_send import (  # noqa: E402
    AndroidWechatError,
    AndroidWechatSender,
    DEFAULT_PRIORITY,
    DEFAULT_STATE_DB,
    DEFAULT_TARGETS,
    image_size,
    load_target,
    ocr_plain,
    resolve_serial,
    sha256_file,
)


MANIFEST_NAME = "native-video-export.json"
MEDIA_URI = "content://media/external/video/media"


class NativeVideoSaveError(RuntimeError):
    """A bounded failure that must not fall back to recording the display."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--target", required=True, help="Allowlisted WeChat target key.")
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--filename", default="wechat-native-video.mp4")
    parser.add_argument("--video-tap", required=True, help="Exact visible video center as x,y.")
    parser.add_argument("--older-pages", type=int, default=0)
    parser.add_argument("--expected-duration-seconds", type=float, default=0.0)
    parser.add_argument("--duration-tolerance-seconds", type=float, default=2.0)
    parser.add_argument("--expected-original-size-mb", type=float, default=0.0)
    parser.add_argument("--original-download-timeout", type=float, default=600.0)
    parser.add_argument("--album-export-timeout", type=float, default=120.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    result: dict[str, Any]
    try:
        serial = resolve_serial(args.adb, args.serial)
        target = load_target(args.target, args.targets_file)
        sender = AndroidWechatSender(
            adb=args.adb,
            serial=serial,
            target=target,
            task_id=args.task_id,
            state_db=DEFAULT_STATE_DB,
            output_dir=output_dir,
            max_list_pages=8,
        )
        tap = parse_point(args.video_tap)
        with priority_android_control(
            lock_path=sender.device_lock_path(),
            priority_path=DEFAULT_PRIORITY,
            purpose=f"wechat_native_video_save:{args.task_id[:96]}",
            timeout_seconds=float(os.environ.get("WECHAT_ANDROID_LOCK_TIMEOUT", "180")),
            lease_seconds=max(600.0, args.original_download_timeout + 300.0),
        ):
            try:
                result = recover_native_video(sender, args=args, output_dir=output_dir, video_tap=tap)
            finally:
                try:
                    sender.restore_wecom()
                except Exception:
                    pass
    except Exception as exc:
        result = {
            "ok": False,
            "status": "native-source-unavailable",
            "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
            "screen_capture_fallback_allowed": False,
            "next_action": "Stop without processing or publishing until the exact native video is available.",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result.get("status"))
    return 0 if result.get("ok") else 2


def recover_native_video(
    sender: AndroidWechatSender,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    video_tap: tuple[int, int],
) -> dict[str, Any]:
    silence_phone(sender)
    sender.ensure_exact_chat()
    for page in range(max(0, int(args.older_pages))):
        sender.swipe(540, 500, 540, 1750, 700)
        time.sleep(0.8)
        sender.screenshot(f"older-page-{page + 1}")
    exact_chat = sender.screenshot("exact-chat-before-video")
    if not sender.current_chat_matches(exact_chat):
        raise NativeVideoSaveError("exact chat title guard failed before opening video")

    before_rows = query_media_rows(sender)
    sender.tap(*video_tap)
    time.sleep(2.0)
    player = sender.screenshot("native-player-open")
    width, height = image_size(player)
    if sender.current_chat_matches(player):
        raise NativeVideoSaveError("the requested tap did not open a video player")

    original = request_original_if_available(
        sender,
        player=player,
        timeout_seconds=float(args.original_download_timeout),
    )
    sender.tap(int(width * 0.704), int(height * 0.941))
    exported = wait_for_album_export(
        sender,
        before_ids=set(before_rows),
        timeout_seconds=float(args.album_export_timeout),
    )

    filename = safe_filename(args.filename)
    host_path = output_dir / filename
    pull_device_file(sender, exported["path"], host_path)
    probe = probe_video(host_path)
    advertised_size_mb = float(original.get("advertised_size_mb") or 0.0)
    expected_size_mb = float(args.expected_original_size_mb) or advertised_size_mb
    validate_video(
        host_path,
        probe,
        expected_duration=float(args.expected_duration_seconds),
        duration_tolerance=float(args.duration_tolerance_seconds),
        expected_size_mb=expected_size_mb,
    )
    manifest = {
        "status": "host-verified-cleanup-pending",
        "source_kind": "wechat_android_native_album_export",
        "source_chat": sender.chat,
        "task_id": args.task_id,
        "host_path": str(host_path),
        "sha256": sha256_file(host_path),
        "bytes": host_path.stat().st_size,
        "probe": probe,
        "native_original_requested": bool(original.get("requested")),
        "advertised_original_size_mb": advertised_size_mb,
        "expected_original_size_mb": expected_size_mb,
        "automation_screen_capture": False,
        "screen_capture_fallback_allowed": False,
        "device_export_name": exported["name"],
        "device_copy_removed": False,
        "verified_at": utc_now(),
    }
    manifest_path = output_dir / MANIFEST_NAME
    write_manifest(manifest_path, manifest)
    try:
        remove_device_export(sender, exported)
    except Exception as exc:
        manifest["device_cleanup_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        manifest["cleanup_checked_at"] = utc_now()
        write_manifest(manifest_path, manifest)
        raise
    manifest.update(
        {
            "status": "verified",
            "device_copy_removed": True,
            "device_cleanup_error": "",
            "cleanup_checked_at": utc_now(),
        }
    )
    write_manifest(manifest_path, manifest)
    return {
        "ok": True,
        "status": "verified-native-source",
        "path": str(host_path),
        "manifest_path": str(manifest_path),
        "bytes": host_path.stat().st_size,
        "sha256": manifest["sha256"],
        "probe": probe,
        "device_copy_removed": True,
        "screen_capture_used": False,
    }


def request_original_if_available(
    sender: AndroidWechatSender,
    *,
    player: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    width, height = image_size(player)
    crop = player.with_name(f"{player.stem}-original-control.png")
    run_convert_crop(player, crop, width=width, height=height)
    text = normalized_ocr(crop)
    original_visible = "查看原视频" in text or "查看原視頻" in text
    advertised_size_mb = parse_advertised_size_mb(text)
    if not original_visible:
        return {"requested": False, "advertised_size_mb": advertised_size_mb}

    sender.tap(int(width * 0.17), int(height * 0.941))
    deadline = time.monotonic() + max(10.0, timeout_seconds)
    progress_seen = False
    completion_streak = 0
    while time.monotonic() < deadline:
        time.sleep(2.0)
        shot = sender.screenshot("native-original-progress")
        progress_crop = shot.with_name(f"{shot.stem}-control.png")
        run_convert_crop(shot, progress_crop, width=width, height=height)
        control_text = normalized_ocr(progress_crop)
        percentages = [int(value) for value in re.findall(r"(\d{1,3})\s*%", control_text)]
        if percentages:
            progress_seen = True
            completion_streak = 0
            continue
        still_offered = "查看原视频" in control_text or "查看原視頻" in control_text
        if still_offered and not progress_seen:
            sender.tap(int(width * 0.17), int(height * 0.941))
            continue
        if progress_seen or original_visible:
            completion_streak += 1
            if completion_streak >= 2:
                return {"requested": True, "advertised_size_mb": advertised_size_mb}
    raise NativeVideoSaveError("native original download did not finish before timeout")


def parse_advertised_size_mb(text: str) -> float:
    match = re.search(r"(?:查看原视频|查看原視頻).*?(\d+(?:\.\d+)?)\s*(?:MB|M)", text, re.I)
    return float(match.group(1)) if match else 0.0


def run_convert_crop(source: Path, target: Path, *, width: int, height: int) -> None:
    subprocess.run(
        [
            "convert",
            str(source),
            "-crop",
            f"{int(width * 0.38)}x{int(height * 0.10)}+0+{int(height * 0.88)}",
            str(target),
        ],
        capture_output=True,
        check=False,
        timeout=20,
    )


def normalized_ocr(path: Path) -> str:
    try:
        text = ocr_plain(path, psm="6")
    except Exception:
        return ""
    return re.sub(r"\s+", "", text)


def silence_phone(sender: AndroidWechatSender) -> None:
    for stream in (1, 2, 3):
        sender.shell(
            ["media", "volume", "--stream", str(stream), "--set", "0"],
            check=False,
        )


def query_media_rows(sender: AndroidWechatSender) -> dict[int, dict[str, Any]]:
    proc = sender.shell(
        [
            "content",
            "query",
            "--uri",
            MEDIA_URI,
            "--projection",
            "_id:_display_name:_size:date_added:_data",
        ],
        timeout=30,
        check=False,
    )
    return parse_media_rows(str(proc.stdout or ""))


def parse_media_rows(text: str) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    pattern = re.compile(
        r"_id=(?P<id>\d+),\s+_display_name=(?P<name>.*?),\s+"
        r"_size=(?P<size>NULL|\d+),\s+date_added=(?P<date>\d+),\s+_data=(?P<path>.*)$"
    )
    for line in text.splitlines():
        match = pattern.search(line.strip())
        if not match:
            continue
        media_id = int(match.group("id"))
        rows[media_id] = {
            "id": media_id,
            "name": match.group("name").strip(),
            "size": 0 if match.group("size") == "NULL" else int(match.group("size")),
            "date_added": int(match.group("date")),
            "path": match.group("path").strip(),
        }
    return rows


def wait_for_album_export(
    sender: AndroidWechatSender,
    *,
    before_ids: set[int],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(10.0, timeout_seconds)
    last_size = -1
    stable = 0
    selected: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        rows = query_media_rows(sender)
        new_rows = [
            row
            for media_id, row in rows.items()
            if media_id not in before_ids
            and str(row.get("name") or "").lower().startswith("mmexport")
            and "/weixin/" in str(row.get("path") or "").lower()
        ]
        if new_rows:
            selected = max(new_rows, key=lambda row: (int(row["date_added"]), int(row["id"])))
            current_size = int(selected.get("size") or 0)
            if current_size > 0 and current_size == last_size:
                stable += 1
            else:
                stable = 0
            last_size = current_size
            if stable >= 1:
                return selected
        time.sleep(2.0)
    raise NativeVideoSaveError("native album export did not appear before timeout")


def pull_device_file(sender: AndroidWechatSender, remote_path: str, host_path: Path) -> None:
    host_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    proc = sender.adb_run(["pull", remote_path, str(host_path)], timeout=300, check=False)
    if proc.returncode != 0 or not host_path.is_file():
        raise NativeVideoSaveError(f"could not pull native album export: {str(proc.stderr or '')[:400]}")


def probe_video(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate",
            "-show_entries",
            "stream=index,codec_name,codec_type,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if proc.returncode != 0:
        raise NativeVideoSaveError(f"ffprobe rejected native export: {proc.stderr[:400]}")
    payload = json.loads(proc.stdout)
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    if not any(item.get("codec_type") == "video" for item in streams if isinstance(item, dict)):
        raise NativeVideoSaveError("native export has no readable video stream")
    return payload


def validate_video(
    path: Path,
    probe: dict[str, Any],
    *,
    expected_duration: float,
    duration_tolerance: float,
    expected_size_mb: float,
) -> None:
    format_info = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    duration = float(format_info.get("duration") or 0.0)
    size = int(format_info.get("size") or path.stat().st_size)
    if expected_duration > 0 and abs(duration - expected_duration) > max(0.25, duration_tolerance):
        raise NativeVideoSaveError(
            f"native export duration {duration:.3f}s does not match expected {expected_duration:.3f}s"
        )
    if expected_size_mb > 0:
        expected_bytes = expected_size_mb * 1024 * 1024
        if size < expected_bytes * 0.80:
            raise NativeVideoSaveError(
                f"album export is only {size} bytes; expected original is about {expected_size_mb:g} MiB"
            )


def remove_device_export(sender: AndroidWechatSender, row: dict[str, Any]) -> None:
    remote_path = str(row["path"])
    media_id = int(row["id"])
    for _ in range(4):
        sender.shell(["rm", "-f", remote_path], check=False)
        sender.shell(
            ["content", "delete", "--uri", MEDIA_URI, "--where", f"_id={media_id}"],
            check=False,
        )
        file_gone = sender.shell(["ls", remote_path], check=False).returncode != 0
        row_gone = media_id not in query_media_rows(sender)
        if file_gone and row_gone:
            return
        time.sleep(0.5)
    raise NativeVideoSaveError("host copy is verified but the phone-side album export was not removed")


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def parse_point(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", value)
    if not match:
        raise argparse.ArgumentTypeError("--video-tap must be x,y")
    return int(match.group(1)), int(match.group(2))


def safe_filename(value: str) -> str:
    name = Path(value).name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(name).stem).strip("-._") or "wechat-native-video"
    suffix = Path(name).suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v"}:
        suffix = ".mp4"
    return f"{stem}{suffix}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
