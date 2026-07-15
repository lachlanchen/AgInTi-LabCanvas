#!/usr/bin/env python3
"""Capture one exact WeChat Channels player's audio with visual identity gates."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_CACHE_ROOT = PRIVATE / "shipinhao_media_transcripts"
GUI_LOCK = PRIVATE / "wechat_gui_send.lock"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--identity-term", action="append", default=[])
    parser.add_argument("--min-term-matches", type=int, default=1)
    parser.add_argument("--display", default=":97")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument("--loss-polls", type=int, default=3)
    parser.add_argument("--max-seconds", type=float, default=1800)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    terms = unique_strings(args.identity_term or derive_identity_terms(args.title, args.author))
    output_dir = (args.output_dir or DEFAULT_CACHE_ROOT / safe_component(args.object_id)).expanduser().resolve()
    try:
        result = capture_exact_player(
            object_id=args.object_id,
            title=args.title,
            author=args.author,
            identity_terms=terms,
            min_term_matches=max(1, args.min_term_matches),
            display=args.display,
            output_dir=output_dir,
            interval=max(0.5, args.interval),
            loss_polls=max(2, args.loss_polls),
            max_seconds=max(5.0, args.max_seconds),
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "read_only": True,
            "visual_identity_verified": False,
            "error": f"{type(exc).__name__}: {str(exc)[:700]}",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) if args.json else result.get("manifest_path", result["status"]))
    return 0 if result.get("status") == "verified" else 2


def capture_exact_player(
    *,
    object_id: str,
    title: str,
    author: str,
    identity_terms: list[str],
    min_term_matches: int,
    display: str,
    output_dir: Path,
    interval: float,
    loss_polls: int,
    max_seconds: float,
) -> dict[str, Any]:
    require_tools("xdotool", "import", "convert", "tesseract", "pw-dump", "pw-record", "ffmpeg", "ffprobe")
    if not identity_terms:
        raise RuntimeError("no distinctive visual identity terms were supplied or derived")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    env = os.environ.copy()
    env["DISPLAY"] = display
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    with exclusive_gui_lock(GUI_LOCK):
        window = find_channels_window(env)
        if not window:
            raise RuntimeError("the native WeChat Channels player is not visible")
        start_evidence = capture_identity_evidence(
            window,
            output_dir / f"identity-start-{stamp}",
            env,
            identity_terms,
            min_term_matches,
        )
        if not start_evidence["matched"]:
            raise RuntimeError("visible Channels player does not match the expected source identity")
        stream = find_wechat_audio_stream(display)
        raw_audio = output_dir / f"capture-raw-{stamp}.wav"
        recorder = subprocess.Popen(
            ["pw-record", f"--target={stream['serial']}", str(raw_audio)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        started = time.monotonic()
        last_match = 0.0
        first_loss: float | None = None
        consecutive_losses = 0
        polls: list[dict[str, Any]] = []
        stop_reason = ""
        try:
            while True:
                elapsed = time.monotonic() - started
                if recorder.poll() is not None:
                    raise RuntimeError(f"pw-record stopped before identity loss: {(recorder.stderr.read() if recorder.stderr else '')[:400]}")
                if elapsed >= max_seconds:
                    stop_reason = "max_duration"
                    break
                time.sleep(interval)
                evidence = capture_identity_evidence(
                    window,
                    output_dir / f"identity-poll-{stamp}-{len(polls):04d}",
                    env,
                    identity_terms,
                    min_term_matches,
                    retain_image=False,
                )
                elapsed = time.monotonic() - started
                polls.append(
                    {
                        "elapsed_seconds": round(elapsed, 3),
                        "matched": evidence["matched"],
                        "matched_terms": evidence["matched_terms"],
                        "ocr_preview": evidence["ocr_preview"],
                    }
                )
                if evidence["matched"]:
                    last_match = elapsed
                    first_loss = None
                    consecutive_losses = 0
                else:
                    if first_loss is None:
                        first_loss = elapsed
                    consecutive_losses += 1
                    if consecutive_losses >= loss_polls:
                        stop_reason = "visual_identity_lost"
                        break
        finally:
            stop_process(recorder)

        wall_duration = max(0.001, time.monotonic() - started)
        if stop_reason != "visual_identity_lost" or first_loss is None:
            raise RuntimeError(f"capture ended without a verified player identity transition ({stop_reason or 'unknown'})")
        raw_probe = probe_audio(raw_audio)
        raw_duration = float(raw_probe["duration_seconds"])
        # Map the first visual identity loss into the recorded stream clock. This
        # remains correct even when a virtual audio clock differs slightly from wall time.
        visual_cutoff = max(last_match, first_loss - interval * 0.25)
        audio_cutoff = min(raw_duration, max(0.5, visual_cutoff * raw_duration / wall_duration))
        source_audio = output_dir / f"captured-source-{stamp}.wav"
        trim_audio(raw_audio, source_audio, audio_cutoff)
        source_probe = probe_audio(source_audio)
        end_evidence = capture_identity_evidence(
            window,
            output_dir / f"identity-end-{stamp}",
            env,
            identity_terms,
            min_term_matches,
        )

    manifest = {
        "schema_version": 1,
        "status": "verified",
        "read_only": True,
        "public_actions": False,
        "visual_identity_verified": True,
        "source_scope": "one exact WeChat Finder card",
        "object_id": str(object_id),
        "title": str(title),
        "author": str(author),
        "identity_terms": identity_terms,
        "min_term_matches": min_term_matches,
        "stop_reason": stop_reason,
        "audio_path": str(source_audio),
        "audio_sha256": sha256_file(source_audio),
        "audio_duration_seconds": source_probe["duration_seconds"],
        "raw_capture_path": str(raw_audio),
        "raw_capture_sha256": sha256_file(raw_audio),
        "raw_duration_seconds": raw_duration,
        "wall_duration_seconds": round(wall_duration, 3),
        "visual_cutoff_seconds": round(visual_cutoff, 3),
        "audio_cutoff_seconds": round(audio_cutoff, 3),
        "pipewire_stream": stream,
        "start_evidence": start_evidence,
        "end_evidence": end_evidence,
        "polls": polls,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    timestamped = output_dir / f"verified-capture-{stamp}.json"
    latest = output_dir / "verified-capture.json"
    for path in (timestamped, latest):
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        path.chmod(0o600)
    manifest["manifest_path"] = str(latest)
    return manifest


def capture_identity_evidence(
    window: dict[str, Any],
    stem: Path,
    env: dict[str, str],
    terms: list[str],
    min_matches: int,
    *,
    retain_image: bool = True,
) -> dict[str, Any]:
    screenshot = stem.with_suffix(".png")
    run(["import", "-window", str(window["id"]), str(screenshot)], env=env)
    width = int(window["width"])
    height = int(window["height"])
    crops = [
        ("title", int(width * 0.08), int(height * 0.04), int(width * 0.84), int(height * 0.28)),
        ("footer", 0, int(height * 0.68), width, int(height * 0.32)),
    ]
    texts: list[str] = []
    for label, x, y, crop_width, crop_height in crops:
        crop = stem.with_name(stem.name + f"-{label}").with_suffix(".png")
        run(["convert", str(screenshot), "-crop", f"{crop_width}x{crop_height}+{x}+{y}", str(crop)])
        for psm in (6, 11):
            proc = run(["tesseract", str(crop), "stdout", "-l", "chi_sim+chi_tra+eng", "--psm", str(psm)], check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                texts.append(proc.stdout.strip())
        crop.unlink(missing_ok=True)
    combined = "\n".join(texts)
    normalized = normalize_identity(combined)
    matched_terms = [term for term in terms if normalize_identity(term) in normalized]
    result = {
        "matched": len(matched_terms) >= min_matches,
        "matched_terms": matched_terms,
        "identity_terms": terms,
        "ocr_preview": compact_text(combined, 500),
        "screenshot": str(screenshot) if retain_image else "",
        "screenshot_sha256": sha256_file(screenshot),
    }
    if not retain_image:
        screenshot.unlink(missing_ok=True)
    return result


def find_channels_window(env: dict[str, str]) -> dict[str, Any] | None:
    proc = run(["xdotool", "search", "--onlyvisible", "--name", "^WeChat$"], env=env, check=False)
    candidates = [window_geometry(wid, env) for wid in proc.stdout.split()]
    candidates = [item for item in candidates if item and item["width"] >= 600 and item["height"] >= 600]
    return max(candidates, key=lambda item: item["width"] * item["height"]) if candidates else None


def window_geometry(wid: str, env: dict[str, str]) -> dict[str, Any] | None:
    proc = run(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False)
    values: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        try:
            values[key.lower()] = int(raw)
        except ValueError:
            pass
    return {"id": wid, **values} if values.get("width") and values.get("height") else None


def find_wechat_audio_stream(display: str) -> dict[str, Any]:
    proc = run(["pw-dump"])
    payload = json.loads(proc.stdout)
    candidates: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        info = item.get("info") if isinstance(item, dict) and isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        if props.get("media.class") != "Stream/Output/Audio":
            continue
        if props.get("application.process.binary") != "WeChatAppEx":
            continue
        if props.get("window.x11.display") not in {None, "", display}:
            continue
        serial = props.get("object.serial")
        if serial is not None:
            candidates.append({"node_id": item.get("id"), "serial": int(serial), "process_id": props.get("application.process.id")})
    if not candidates:
        raise RuntimeError("no active WeChatAppEx PipeWire output stream was found")
    return candidates[-1]


def derive_identity_terms(title: str, author: str) -> list[str]:
    terms = re.findall(r"[《【]([^》】]{2,20})[》】]", title)
    terms.extend(part.strip() for part in re.split(r"[#|｜]", title) if 2 <= len(part.strip()) <= 20)
    if author.strip():
        terms.append(author.strip().rstrip("."))
    return unique_strings(terms)


def probe_audio(path: Path) -> dict[str, Any]:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(path)
    ])
    payload = json.loads(proc.stdout)
    info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("captured audio has no readable duration")
    return {"duration_seconds": duration, "size_bytes": int(info.get("size") or path.stat().st_size)}


def trim_audio(source: Path, target: Path, seconds: float) -> None:
    run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", str(target),
    ])
    if not target.is_file() or target.stat().st_size <= 44:
        raise RuntimeError("ffmpeg did not produce the source-scoped audio file")


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


@contextmanager
def exclusive_gui_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("WECHAT_SEND_BUSY: GUI lane is active; retry capture later") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def require_tools(*names: str) -> None:
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise RuntimeError("missing required tools: " + ", ".join(missing))


def run(command: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, capture_output=True, text=True, check=check)


def normalize_identity(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", str(value or "").casefold())


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "").strip()).strip("-._")
    return cleaned[:100] or "shipinhao"


def compact_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "..."


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
