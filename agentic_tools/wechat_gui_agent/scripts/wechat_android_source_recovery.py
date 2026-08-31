#!/usr/bin/env python3
"""Recover one exact WeChat article or Channels card through the MIX 2S app."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any
from urllib import parse as urlparse
import wave

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
ANDROID_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"
for directory in (SCRIPTS, ANDROID_SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from android_control_lease import priority_android_control, serialized_android_clipboard  # noqa: E402
from wechat_android_send import (  # noqa: E402
    AndroidWechatError,
    AndroidWechatSender,
    DEFAULT_CLIPBOARD_LOCK,
    DEFAULT_PRIORITY,
    DEFAULT_STATE_DB,
    DEFAULT_TARGETS,
    OcrLine,
    load_target,
    normalize_text,
    ocr_lines,
    resolve_serial,
    run_checked,
    sha256_file,
)
from wechat_source_recovery import (  # noqa: E402
    normalize_wechat_article_url,
    recover_mp_weixin_article,
)


PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_CACHE_ROOT = PRIVATE / "shipinhao_media_transcripts"
SNDCPY_PACKAGE = "com.rom1v.sndcpy"
SNDCPY_ACTIVITY = f"{SNDCPY_PACKAGE}/.MainActivity"
WECHAT_PACKAGE = "com.tencent.mm"


class NativeRecoveryError(RuntimeError):
    """A bounded exact-source recovery failure."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("shipinhao", "article"))
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--target", required=True, help="Allowlisted WeChat target registry key.")
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source-id", required=True, help="Exact inbound server/message identity.")
    parser.add_argument("--object-id", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--identity-term", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--max-scrolls", type=int, default=6)
    parser.add_argument("--max-seconds", type=float, default=120.0)
    parser.add_argument("--expected-duration-seconds", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    serial = resolve_serial(args.adb, args.serial)
    target = load_target(args.target, args.targets_file)
    sender = AndroidWechatSender(
        adb=args.adb,
        serial=serial,
        target=target,
        task_id=args.task_id,
        state_db=DEFAULT_STATE_DB,
        output_dir=output_dir,
        max_list_pages=max(2, min(10, args.max_scrolls)),
    )
    terms = unique_strings([*args.identity_term, args.author, args.title])
    result: dict[str, Any]
    try:
        with priority_android_control(
            lock_path=sender.device_lock_path(),
            priority_path=DEFAULT_PRIORITY,
            purpose=f"wechat_native_source:{args.task_id[:96]}",
            timeout_seconds=float(os.environ.get("WECHAT_ANDROID_LOCK_TIMEOUT", "180")),
            lease_seconds=max(300.0, args.max_seconds + 240.0),
        ):
            try:
                sender.wake_and_launch()
                if args.kind == "article":
                    sender.ensure_exact_chat()
                    if not args.title.strip():
                        raise NativeRecoveryError("article title is required", code="missing_article_title")
                    result = recover_article(
                        sender,
                        title=args.title.strip(),
                        output_dir=output_dir,
                        max_scrolls=args.max_scrolls,
                    )
                else:
                    if not terms:
                        raise NativeRecoveryError(
                            "at least one exact card identity term is required",
                            code="missing_identity_terms",
                        )
                    object_id = args.object_id.strip() or native_object_id(args.source_id)
                    result = recover_shipinhao(
                        sender,
                        object_id=object_id,
                        source_id=args.source_id,
                        title=args.title.strip(),
                        author=args.author.strip(),
                        identity_terms=terms,
                        output_dir=output_dir,
                        cache_root=args.cache_root.expanduser().resolve(),
                        max_scrolls=args.max_scrolls,
                        max_seconds=args.max_seconds,
                        expected_duration_seconds=args.expected_duration_seconds,
                    )
            finally:
                try:
                    sender.restore_wecom()
                except Exception:
                    pass
    except Exception as exc:
        result = {
            "ok": False,
            "status": "failed",
            "error_code": exc.code if isinstance(exc, NativeRecoveryError) else "native_recovery_failed",
            "error": f"{type(exc).__name__}: {str(exc)[:700]}",
            "read_only": True,
            "public_actions": False,
        }
    manifest = output_dir / "native-source-recovery.json"
    safe_result = dict(result)
    manifest.write_text(
        json.dumps(safe_result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    result["manifest_path"] = str(manifest)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.json else result.get("status", "failed"))
    return 0 if result.get("ok") else 2


def recover_shipinhao(
    sender: AndroidWechatSender,
    *,
    object_id: str,
    source_id: str,
    title: str,
    author: str,
    identity_terms: list[str],
    output_dir: Path,
    cache_root: Path,
    max_scrolls: int,
    max_seconds: float,
    expected_duration_seconds: float,
) -> dict[str, Any]:
    prewarm_sndcpy(sender)
    # Starting sndcpy briefly foregrounds its helper activity. Re-enter and
    # verify the exact chat only after that transition so card scanning cannot
    # silently begin from WeChat's conversation list.
    sender.ensure_exact_chat()
    player = open_exact_card(
        sender,
        identity_terms=identity_terms,
        max_scrolls=max_scrolls,
        require_article=False,
    )
    cache_dir = cache_root / safe_component(object_id)
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    capture = capture_player(
        sender,
        cache_dir=cache_dir,
        identity_terms=identity_terms,
        max_seconds=max_seconds,
        expected_duration_seconds=expected_duration_seconds,
    )
    manifest = {
        "status": "verified",
        "read_only": True,
        "public_actions": False,
        "source_kind": "android_native_finder_capture",
        "source_chat": sender.chat,
        "source_message_id": source_id,
        "object_id": object_id,
        "title": title,
        "author": author,
        "identity_terms": identity_terms,
        "visual_identity_verified": True,
        "identity_screenshot": str(player),
        "audio_path": capture["audio_path"],
        "audio_sha256": capture["audio_sha256"],
        "video_path": capture["video_path"],
        "video_sha256": capture["video_sha256"],
        "raw_audio_path": capture.get("raw_audio_path", ""),
        "raw_audio_sha256": capture.get("raw_audio_sha256", ""),
        "raw_video_path": capture.get("raw_video_path", ""),
        "raw_video_sha256": capture.get("raw_video_sha256", ""),
        "raw_duration_seconds": capture.get("raw_duration_seconds", 0.0),
        "duration_seconds": capture["duration_seconds"],
        "loop_trim_verified": bool(capture.get("loop_trim_verified")),
        "loop_period_seconds": capture.get("loop_period_seconds", 0.0),
        "captured_at": utc_now(),
    }
    verified_manifest = cache_dir / "verified-capture.json"
    verified_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verified_manifest.chmod(0o600)
    return {
        "ok": True,
        "status": "verified",
        "visual_identity_verified": True,
        "object_id": object_id,
        "title": title,
        "author": author,
        "capture_manifest": str(verified_manifest),
        "duration_seconds": capture["duration_seconds"],
        "read_only": True,
        "public_actions": False,
    }


def recover_article(
    sender: AndroidWechatSender,
    *,
    title: str,
    output_dir: Path,
    max_scrolls: int,
) -> dict[str, Any]:
    open_exact_card(
        sender,
        identity_terms=[title],
        max_scrolls=max_scrolls,
        require_article=True,
    )
    url = copy_article_link(sender)
    article = recover_mp_weixin_article(
        url,
        output_dir / "article",
        card_profile={"title": title},
    )
    if not article_titles_match(title, str(article.get("title") or "")):
        raise NativeRecoveryError(
            "copied article title does not match the exact source card",
            code="article_identity_mismatch",
        )
    return {
        "ok": True,
        "status": str(article.get("status") or "unknown"),
        "transport": "wechat_android",
        "source_quality": str(article.get("source_quality") or "unknown"),
        "title": str(article.get("title") or title),
        "author": str(article.get("author") or ""),
        "article_chars": int(article.get("article_chars") or 0),
        "markdown_path": str(article.get("markdown_path") or ""),
        "url": url,
        "identity_verified": True,
        "read_only": True,
        "public_actions": False,
    }


def article_titles_match(expected: str, actual: str) -> bool:
    """Allow a publisher suffix without weakening exact-card identity."""

    expected_key = normalize_text(expected)
    actual_key = normalize_text(actual)
    if not expected_key or not actual_key:
        return False
    if expected_key == actual_key:
        return True
    shorter, longer = sorted((expected_key, actual_key), key=len)
    return bool(
        len(shorter) >= 8
        and len(shorter) / len(longer) >= 0.65
        and shorter in longer
    )


def open_exact_card(
    sender: AndroidWechatSender,
    *,
    identity_terms: list[str],
    max_scrolls: int,
    require_article: bool,
) -> Path:
    terms = [normalize_text(term) for term in identity_terms if normalize_text(term)]
    for page in range(max(0, min(12, max_scrolls)) + 1):
        shot = sender.screenshot(f"source-card-page-{page}")
        candidates = identity_candidates(ocr_lines(shot), terms)
        for index, candidate in enumerate(candidates):
            sender.tap(candidate.center_x, candidate.center_y)
            time.sleep(2.0)
            opened = sender.screenshot(f"source-card-open-{page}-{index}")
            opened_text = normalize_text(" ".join(line.text for line in ocr_lines(opened)))
            still_chat = sender.current_chat_matches(opened)
            identity_seen = any(term in opened_text for term in terms)
            package = sender.current_package()
            if package == WECHAT_PACKAGE and not still_chat and (identity_seen or require_article):
                return opened
            if package == WECHAT_PACKAGE and not still_chat:
                sender.keyevent(4, check=False)
                time.sleep(0.8)
        if page < max_scrolls:
            sender.swipe(540, 650, 540, 1500, 450, check=False)
            time.sleep(0.8)
    raise NativeRecoveryError(
        "exact same-chat source card was not found in the bounded scan",
        code="source_card_not_found",
    )


def identity_candidates(lines: list[OcrLine], normalized_terms: list[str]) -> list[OcrLine]:
    candidates = []
    for line in lines:
        text = normalize_text(line.text)
        if not text or line.top < 170 or line.bottom > 1980:
            continue
        if any(term in text or text in term for term in normalized_terms if len(term) >= 2):
            candidates.append(line)
    # Try the newest visible source first. Text replies containing the same
    # term are harmless because the post-click player identity gate rejects
    # them and continues with the next candidate.
    candidates.sort(key=lambda item: item.center_y, reverse=True)
    return candidates


def prewarm_sndcpy(sender: AndroidWechatSender) -> None:
    package = sender.shell(["pm", "path", SNDCPY_PACKAGE], check=False)
    if not str(package.stdout or "").strip():
        raise NativeRecoveryError(
            "the source-audited sndcpy helper is not installed",
            code="sndcpy_not_installed",
        )
    sender.shell(["am", "force-stop", SNDCPY_PACKAGE], check=False)
    sender.shell(["am", "start", "-n", SNDCPY_ACTIVITY], check=False)
    time.sleep(1.5)
    sender.wake_and_launch()


def capture_player(
    sender: AndroidWechatSender,
    *,
    cache_dir: Path,
    identity_terms: list[str],
    max_seconds: float,
    expected_duration_seconds: float,
) -> dict[str, Any]:
    require_tools("ffmpeg", "ffprobe")
    limit = capture_limit(max_seconds, expected_duration_seconds)
    sender.shell(["media", "volume", "--stream", "3", "--set", "0"], check=False)
    forward = sender.adb_run(
        ["forward", "tcp:0", "localabstract:sndcpy"],
        timeout=15,
    )
    port = int(str(forward.stdout or "").strip())
    remote = f"/sdcard/Download/labcanvas-{safe_component(sender.task_id)}.mp4"
    video_path = cache_dir / "native-player-capture.mp4"
    audio_path = cache_dir / "native-player-audio.wav"
    audio_process = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-i",
            f"tcp://127.0.0.1:{port}",
            "-t",
            f"{limit:.3f}",
            str(audio_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    video_process = subprocess.Popen(
        [
            sender.adb,
            "-s",
            sender.serial,
            "shell",
            "screenrecord",
            "--bit-rate",
            "12000000",
            "--time-limit",
            str(int(round(limit))),
            remote,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    lost_identity = 0
    normalized_terms = [normalize_text(term) for term in identity_terms if normalize_text(term)]
    try:
        while time.monotonic() - started < limit + 3.0 and video_process.poll() is None:
            time.sleep(min(5.0, max(0.5, limit / 8.0)))
            shot = sender.screenshot("source-capture-identity")
            visible = normalize_text(" ".join(line.text for line in ocr_lines(shot)))
            if any(term in visible for term in normalized_terms):
                lost_identity = 0
            else:
                lost_identity += 1
                if lost_identity >= 3 and time.monotonic() - started >= 8.0:
                    break
    finally:
        if video_process.poll() is None:
            sender.shell(["pkill", "-2", "screenrecord"], check=False)
            time.sleep(0.8)
        stop_process(video_process, sig=signal.SIGINT)
        stop_process(audio_process, sig=signal.SIGINT)
        sender.shell(["am", "force-stop", SNDCPY_PACKAGE], check=False)
        sender.adb_run(["forward", "--remove", f"tcp:{port}"], timeout=10, check=False)
    sender.adb_run(["pull", remote, str(video_path)], timeout=180)
    sender.shell(["rm", "-f", remote], check=False)
    video_probe = probe_media(video_path)
    audio_probe = probe_media(audio_path)
    if not any(stream.get("codec_type") == "video" for stream in video_probe.get("streams") or []):
        raise NativeRecoveryError("native capture contains no readable video stream", code="capture_video_invalid")
    if not any(stream.get("codec_type") == "audio" for stream in audio_probe.get("streams") or []):
        raise NativeRecoveryError("native capture contains no readable audio stream", code="capture_audio_invalid")
    raw_duration = min(
        positive_float(video_probe.get("format", {}).get("duration")),
        positive_float(audio_probe.get("format", {}).get("duration")),
    )
    loop_period = verified_loop_period(
        audio_path,
        video_path,
        duration_seconds=raw_duration,
    )
    duration = loop_period or raw_duration
    recovered_audio = cache_dir / "recovered-source-audio.wav"
    recovered_video = cache_dir / "recovered-source-video.mp4"
    trim_audio_capture(audio_path, recovered_audio, duration)
    mux_player_capture(video_path, recovered_audio, recovered_video, duration)
    return {
        "video_path": str(recovered_video.resolve()),
        "video_sha256": sha256_file(recovered_video),
        "audio_path": str(recovered_audio.resolve()),
        "audio_sha256": sha256_file(recovered_audio),
        "raw_video_path": str(video_path.resolve()),
        "raw_video_sha256": sha256_file(video_path),
        "raw_audio_path": str(audio_path.resolve()),
        "raw_audio_sha256": sha256_file(audio_path),
        "raw_duration_seconds": raw_duration,
        "duration_seconds": duration,
        "loop_trim_verified": bool(loop_period),
        "loop_period_seconds": loop_period,
    }


def verified_loop_period(
    audio_path: Path,
    video_path: Path,
    *,
    duration_seconds: float,
) -> float:
    """Return one repeated playback period only with audio and visual proof."""

    candidate, correlation = audio_loop_candidate(audio_path)
    if not candidate or correlation < 0.92:
        return 0.0
    if candidate >= duration_seconds - 10.0:
        return 0.0
    visual_score = visual_loop_difference(
        video_path,
        period_seconds=candidate,
        duration_seconds=duration_seconds,
    )
    if visual_score < 0 or visual_score > 0.05:
        return 0.0
    return round(candidate, 3)


def audio_loop_candidate(audio_path: Path) -> tuple[float, float]:
    """Find a repeated tail in PCM audio using a 20 ms RMS envelope."""

    try:
        with wave.open(str(audio_path), "rb") as source:
            channels = int(source.getnchannels())
            rate = int(source.getframerate())
            width = int(source.getsampwidth())
            frames = int(source.getnframes())
            payload = source.readframes(frames)
    except (OSError, wave.Error):
        return 0.0, 0.0
    if channels <= 0 or rate <= 0 or width != 2 or not payload:
        return 0.0, 0.0
    samples = np.frombuffer(payload, dtype="<i2")
    usable = samples.size - (samples.size % channels)
    if usable <= 0:
        return 0.0, 0.0
    mono = samples[:usable].reshape(-1, channels).astype(np.float64).mean(axis=1)
    hop = max(1, int(round(rate * 0.02)))
    buckets = mono.size // hop
    if buckets < 1000:
        return 0.0, 0.0
    envelope = np.sqrt(
        np.mean(mono[: buckets * hop].reshape(buckets, hop) ** 2, axis=1)
    )
    envelope -= float(envelope.mean())
    spread = float(envelope.std())
    if spread < 1e-6:
        return 0.0, 0.0
    envelope /= spread
    seconds_per_bucket = hop / rate
    minimum_lag = max(1, int(round(8.0 / seconds_per_bucket)))
    minimum_overlap = max(1, int(round(12.0 / seconds_per_bucket)))
    maximum_lag = envelope.size - minimum_overlap
    best_correlation = -1.0
    best_lag = 0
    for lag in range(minimum_lag, maximum_lag + 1):
        first = envelope[:-lag]
        second = envelope[lag:]
        denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
        if denominator <= 1e-9:
            continue
        correlation = float(np.dot(first, second) / denominator)
        if correlation > best_correlation:
            best_correlation = correlation
            best_lag = lag
    if best_lag <= 0:
        return 0.0, 0.0
    return best_lag * seconds_per_bucket, best_correlation


def visual_loop_difference(
    video_path: Path,
    *,
    period_seconds: float,
    duration_seconds: float,
) -> float:
    overlap = duration_seconds - period_seconds
    if overlap < 10.0:
        return -1.0
    sample_times = unique_numbers(
        [1.0, overlap * 0.25, overlap * 0.5, overlap * 0.75]
    )
    differences: list[float] = []
    for timestamp in sample_times:
        if timestamp + period_seconds >= duration_seconds - 0.2:
            continue
        first = extract_gray_frame(video_path, timestamp)
        second = extract_gray_frame(video_path, timestamp + period_seconds)
        if first is None or second is None or first.shape != second.shape:
            return -1.0
        differences.append(float(np.mean(np.abs(first - second)) / 255.0))
    if len(differences) < 3:
        return -1.0
    return float(np.median(np.asarray(differences)))


def extract_gray_frame(video_path: Path, timestamp: float) -> np.ndarray | None:
    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "crop=iw:ih*0.76:0:ih*0.08,scale=128:192,format=gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=20,
        check=False,
    )
    expected = 128 * 192
    if process.returncode != 0 or len(process.stdout) != expected:
        return None
    return np.frombuffer(process.stdout, dtype=np.uint8).reshape(192, 128).astype(np.float64)


def trim_audio_capture(source: Path, target: Path, duration_seconds: float) -> None:
    run_checked(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-t",
            f"{duration_seconds:.3f}",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        timeout=180,
    )


def mux_player_capture(
    video_path: Path,
    audio_path: Path,
    target: Path,
    duration_seconds: float,
) -> None:
    run_checked(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-t",
            f"{duration_seconds:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(target),
        ],
        timeout=300,
    )


def unique_numbers(values: list[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        number = round(max(0.0, float(value)), 3)
        if number not in result:
            result.append(number)
    return result


def copy_article_link(sender: AndroidWechatSender) -> str:
    require_tools("xclip")
    sentinel = f"__LABCANVAS_ARTICLE_{os.getpid()}_{time.time_ns()}__"
    with serialized_android_clipboard(
        lock_path=DEFAULT_CLIPBOARD_LOCK,
        timeout_seconds=15.0,
    ):
        set_host_clipboard(sender.display, sentinel)
        sender.tap(960, 132, check=False)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            menu = sender.screenshot("article-menu")
            choices = [
                line
                for line in ocr_lines(menu)
                if normalize_text(line.text) == normalize_text("复制链接")
            ]
            if choices:
                sender.tap(choices[0].center_x, choices[0].center_y)
                break
            time.sleep(0.4)
        else:
            raise NativeRecoveryError(
                "native article menu did not expose Copy Link",
                code="article_copy_link_missing",
            )
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            value = get_host_clipboard(sender.display)
            if value != sentinel:
                try:
                    normalized = normalize_wechat_article_url(value)
                except ValueError:
                    normalized = ""
                if normalized and urlparse.urlsplit(normalized).hostname == "mp.weixin.qq.com":
                    return normalized
            time.sleep(0.25)
    raise NativeRecoveryError(
        "native article URL did not reach the synchronized clipboard",
        code="article_clipboard_missing",
    )


def set_host_clipboard(display: str, value: str) -> None:
    subprocess.run(
        ["xclip", "-selection", "clipboard", "-i"],
        input=value,
        text=True,
        env={**os.environ, "DISPLAY": display},
        timeout=5,
        check=True,
    )


def get_host_clipboard(display: str) -> str:
    process = subprocess.run(
        ["xclip", "-selection", "clipboard", "-o"],
        capture_output=True,
        text=True,
        env={**os.environ, "DISPLAY": display},
        timeout=5,
        check=False,
    )
    return str(process.stdout or "").strip()


def stop_process(process: subprocess.Popen[str], *, sig: signal.Signals) -> None:
    if process.poll() is not None:
        return
    process.send_signal(sig)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def probe_media(path: Path) -> dict[str, Any]:
    process = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise NativeRecoveryError("ffprobe returned invalid media metadata", code="capture_probe_failed") from exc
    if process.returncode != 0 or not isinstance(payload, dict):
        raise NativeRecoveryError("captured media is unreadable", code="capture_probe_failed")
    return payload


def capture_limit(max_seconds: float, expected_duration_seconds: float) -> float:
    maximum = min(180.0, max(8.0, float(max_seconds or 120.0)))
    expected = max(0.0, float(expected_duration_seconds or 0.0))
    return min(maximum, max(8.0, expected + 8.0)) if expected else maximum


def native_object_id(source_id: str) -> str:
    digest = hashlib.sha256(str(source_id).encode("utf-8")).hexdigest()[:24]
    return f"android-{digest}"


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "")).strip("-._")
    return cleaned[:120] or "source"


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = " ".join(str(value or "").split())
        key = normalize_text(item)
        if item and key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def positive_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, number)


def require_tools(*names: str) -> None:
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise NativeRecoveryError(
            f"missing required tools: {', '.join(missing)}",
            code="missing_tools",
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
