#!/usr/bin/env python3
"""Extract, decode, and transcribe WeChat voice messages from decrypted media DBs."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DECRYPTED = PRIVATE / "wechat_decrypt" / "decrypted"
VENV_PYTHON = PRIVATE / "wechat_decrypt" / ".venv" / "bin" / "python"
DEFAULT_CACHE = PRIVATE / "voice_transcriptions.json"
DEFAULT_OUTPUT = PRIVATE / "voice_transcripts"
DEFAULT_MODEL = os.environ.get("WECHAT_VOICE_WHISPER_MODEL", "base")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Direct chatops config JSON; used for chatroom_id/chat_name defaults.")
    parser.add_argument("--chatroom-id", default="", help="WeChat username/chatroom id, e.g. 12345@chatroom.")
    parser.add_argument("--chat-name", default="", help="Display name used only for output folder names.")
    parser.add_argument("--local-id", type=int, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--backend",
        choices=["auto", "faster-whisper", "whisper"],
        default=os.environ.get("WECHAT_VOICE_WHISPER_BACKEND", "auto"),
        help="ASR backend. auto prefers faster-whisper when installed, then OpenAI whisper.",
    )
    parser.add_argument("--device", default=os.environ.get("WECHAT_VOICE_WHISPER_DEVICE", "cpu"))
    parser.add_argument("--compute-type", default=os.environ.get("WECHAT_VOICE_WHISPER_COMPUTE_TYPE", "int8"))
    parser.add_argument("--language", default=os.environ.get("WECHAT_VOICE_LANGUAGE", ""))
    parser.add_argument(
        "--vad-filter",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("WECHAT_VOICE_VAD", "").strip().lower() in {"1", "true", "yes", "on"},
        help="Enable faster-whisper VAD. Disabled by default because onnxruntime may be unavailable or ABI-incompatible.",
    )
    parser.add_argument("--media-db", type=Path, default=DECRYPTED / "message" / "media_0.db")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", action="store_true", help="Ignore cached transcript and rerun decode/transcription.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config) if args.config else {}
    chatroom_id = args.chatroom_id or str(config.get("chatroom_id") or "")
    chat_name = args.chat_name or str(config.get("chat_name") or chatroom_id or "wechat")
    if not chatroom_id:
        return emit({"ok": False, "status": "missing-chatroom-id", "error": "chatroom id is required"}, args.json, 2)

    key = cache_key(chatroom_id, args.local_id)
    cache = load_cache(args.cache)
    cached = cache.get(key)
    if isinstance(cached, dict) and not args.refresh and cached.get("text") and cached.get("model") == args.model:
        payload = {"ok": True, "status": "cached", **public_cache_entry(cached)}
        return emit(payload, args.json, 0)

    try:
        voice_row = fetch_voice_row(args.media_db, chatroom_id, args.local_id)
        if voice_row is None:
            return emit(
                {
                    "ok": False,
                    "status": "voice-not-found",
                    "error": f"no VoiceInfo row for {chatroom_id} local_id={args.local_id}",
                },
                args.json,
                3,
            )
        voice_data, create_time = voice_row
        args.output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = decode_voice_to_wav(voice_data, chatroom_id, chat_name, args.local_id, create_time, args.output_dir)
        transcript = transcribe_wav(
            wav_path,
            model=args.model,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
            vad_filter=bool(args.vad_filter),
            backend=args.backend,
        )
    except Exception as exc:
        return emit({"ok": False, "status": "error", "error": str(exc)[:1000]}, args.json, 1)

    entry = {
        "text": transcript["text"],
        "model": args.model,
        "backend": transcript.get("backend") or args.backend,
        "language": transcript.get("language") or "",
        "language_probability": transcript.get("language_probability"),
        "duration": transcript.get("duration"),
        "segments": transcript.get("segments", []),
        "wav_path": str(wav_path),
        "source_bytes": len(voice_data),
        "chatroom_id": chatroom_id,
        "chat_name": chat_name,
        "local_id": args.local_id,
        "create_time": create_time,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    cache[key] = entry
    save_cache(args.cache, cache)
    payload = {"ok": True, "status": "transcribed", **public_cache_entry(entry)}
    return emit(payload, args.json, 0)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cache_key(chatroom_id: str, local_id: int) -> str:
    return json.dumps([chatroom_id, int(local_id)], ensure_ascii=False)


def load_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    path.chmod(0o600)


def public_cache_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": str(entry.get("text") or ""),
        "language": entry.get("language") or "",
        "language_probability": entry.get("language_probability"),
        "duration": entry.get("duration"),
        "wav_path": entry.get("wav_path") or "",
        "source_bytes": entry.get("source_bytes") or 0,
        "local_id": entry.get("local_id"),
        "create_time": entry.get("create_time"),
        "model": entry.get("model") or "",
        "backend": entry.get("backend") or "",
    }


def fetch_voice_row(media_db: Path, chatroom_id: str, local_id: int) -> tuple[bytes, int] | None:
    if not media_db.exists():
        raise FileNotFoundError(f"missing decrypted media DB: {media_db}")
    with sqlite3.connect(media_db) as conn:
        row = conn.execute("SELECT rowid FROM Name2Id WHERE user_name = ?", (chatroom_id,)).fetchone()
        if row is None:
            return None
        chat_name_id = int(row[0])
        voice = conn.execute(
            "SELECT voice_data, create_time FROM VoiceInfo WHERE chat_name_id = ? AND local_id = ? ORDER BY data_index LIMIT 1",
            (chat_name_id, int(local_id)),
        ).fetchone()
    if voice is None:
        return None
    return bytes(voice[0]), int(voice[1])


def decode_voice_to_wav(
    voice_data: bytes,
    chatroom_id: str,
    chat_name: str,
    local_id: int,
    create_time: int,
    output_dir: Path,
) -> Path:
    if not VENV_PYTHON.exists():
        raise FileNotFoundError(f"missing WeChat decrypt venv python: {VENV_PYTHON}")
    safe_chat = safe_component(chat_name or chatroom_id)
    target_dir = output_dir / safe_chat
    target_dir.mkdir(parents=True, exist_ok=True)
    time_part = datetime.fromtimestamp(create_time).strftime("%Y%m%d_%H%M%S")
    wav_path = target_dir / f"voice_{time_part}_{int(local_id)}.wav"
    if wav_path.exists() and wav_path.stat().st_size > 44:
        return wav_path
    with tempfile.TemporaryDirectory(prefix="wechat-voice-", dir=str(PRIVATE)) as tmp:
        tmp_dir = Path(tmp)
        blob_path = tmp_dir / "voice.blob"
        blob_path.write_bytes(voice_data)
        helper = r'''
from pathlib import Path
import sys
import wave
import pilk

blob = Path(sys.argv[1])
wav = Path(sys.argv[2])
work = blob.parent
silk = work / "voice.silk"
pcm = work / "voice.pcm"
data = blob.read_bytes()
if data[:1] == b"\x02":
    data = data[1:]
if not data.startswith(b"#!SILK_V3"):
    raise SystemExit("voice blob is not SILK_V3")
if not data.endswith(b"\xff\xff"):
    data += b"\xff\xff"
silk.write_bytes(data)
pilk.decode(str(silk), str(pcm))
pcm_data = pcm.read_bytes()
wav.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(wav), "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(24000)
    wf.writeframes(pcm_data)
'''
        proc = subprocess.run(
            [str(VENV_PYTHON), "-c", helper, str(blob_path), str(wav_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "SILK decode failed").strip()[:1000])
    return wav_path


def transcribe_wav(
    wav_path: Path,
    *,
    model: str,
    device: str,
    compute_type: str,
    language: str = "",
    vad_filter: bool = False,
    backend: str = "auto",
) -> dict[str, Any]:
    backend = (backend or "auto").strip().lower()
    if backend in {"auto", "faster-whisper", "faster_whisper"}:
        try:
            return transcribe_wav_faster_whisper(
                wav_path,
                model=model,
                device=device,
                compute_type=compute_type,
                language=language,
                vad_filter=vad_filter,
            )
        except Exception as exc:
            if backend in {"faster-whisper", "faster_whisper"}:
                raise RuntimeError(f"faster_whisper failed in the selected Python environment: {exc}") from exc
    if backend in {"auto", "whisper", "openai-whisper", "openai_whisper"}:
        try:
            return transcribe_wav_openai_whisper(wav_path, model=model, device=device, language=language)
        except Exception as exc:
            if backend == "auto":
                raise RuntimeError(
                    "missing usable Whisper backend in the selected Python environment "
                    "(tried faster_whisper and whisper)"
                ) from exc
            raise
    raise RuntimeError(f"unsupported Whisper backend: {backend}")


def transcribe_wav_faster_whisper(
    wav_path: Path,
    *,
    model: str,
    device: str,
    compute_type: str,
    language: str = "",
    vad_filter: bool = False,
) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError as exc:
        raise exc

    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    kwargs: dict[str, Any] = {"beam_size": 5}
    if language:
        kwargs["language"] = language
    if vad_filter:
        try:
            segments_iter, info = whisper.transcribe(str(wav_path), vad_filter=True, **kwargs)
        except Exception as exc:
            if not optional_vad_failure(exc):
                raise
            segments_iter, info = whisper.transcribe(str(wav_path), vad_filter=False, **kwargs)
    else:
        segments_iter, info = whisper.transcribe(str(wav_path), vad_filter=False, **kwargs)
    segments = []
    parts = []
    for segment in segments_iter:
        text = str(segment.text or "").strip()
        if not text:
            continue
        parts.append(text)
        segments.append({"start": round(float(segment.start), 2), "end": round(float(segment.end), 2), "text": text})
    return {
        "backend": "faster-whisper",
        "text": " ".join(parts).strip(),
        "language": getattr(info, "language", ""),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "segments": segments,
    }


def transcribe_wav_openai_whisper(
    wav_path: Path,
    *,
    model: str,
    device: str,
    language: str = "",
) -> dict[str, Any]:
    try:
        import whisper
    except Exception as exc:
        raise RuntimeError(f"missing usable whisper package in the selected Python environment: {exc}") from exc

    whisper_model = whisper.load_model(model, device=device)
    kwargs: dict[str, Any] = {"fp16": device not in {"cpu", ""}}
    if language:
        kwargs["language"] = language
    result = whisper_model.transcribe(str(wav_path), **kwargs)
    raw_segments = result.get("segments") or []
    segments = []
    parts = []
    for segment in raw_segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        parts.append(text)
        segments.append(
            {
                "start": round(float(segment.get("start") or 0), 2),
                "end": round(float(segment.get("end") or 0), 2),
                "text": text,
            }
        )
    duration = max((float(segment.get("end") or 0) for segment in raw_segments), default=None)
    return {
        "backend": "whisper",
        "text": " ".join(parts).strip(),
        "language": result.get("language") or "",
        "language_probability": None,
        "duration": duration,
        "segments": segments,
    }


def optional_vad_failure(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    markers = ("onnxruntime", "VAD filter", "_ARRAY_API", "NumPy 1.x", "numpy 1.x")
    return any(marker.lower() in text.lower() for marker in markers)


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "-", value.strip())
    return cleaned.strip("-") or "wechat"


def emit(payload: dict[str, Any], as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if payload.get("ok"):
            print(payload.get("text") or payload.get("status") or "ok")
        else:
            print(payload.get("error") or payload.get("status") or "error", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
