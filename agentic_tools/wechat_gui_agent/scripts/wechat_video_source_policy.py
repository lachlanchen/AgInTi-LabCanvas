#!/usr/bin/env python3
"""Fail-closed provenance checks for WeChat video processing and publication."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


NATIVE_MANIFEST = "native-video-export.json"
ACCEPTED_NATIVE_KINDS = {
    "wechat_android_native_album_export",
    "wechat_desktop_native_cache",
    "wechat_exact_cdn_payload",
}
CAPTURE_MARKERS = (
    "screenrecord",
    "screen_record",
    "screen-record",
    "screen capture",
    "screen_capture",
    "scrcpy capture",
    "scrcpy_capture",
    "native_player_capture",
    "player_capture",
    "cropped capture",
    "capture_after_original_control_failed",
)
SUSPICIOUS_NAME_MARKERS = (
    "screen_raw",
    "screen-record",
    "screen_record",
    "screenrecord",
    "scrcpy-capture",
    "scrcpy_capture",
)


class UnpublishableVideoSource(RuntimeError):
    """Raised when a local file is not a verified source video."""


@dataclass(frozen=True)
class VideoSourceDecision:
    accepted: bool
    status: str
    reason: str
    manifest_path: str = ""
    source_kind: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "reason": self.reason,
            "manifest_path": self.manifest_path,
            "source_kind": self.source_kind,
        }


def evaluate_publishable_video_source(path: Path) -> VideoSourceDecision:
    """Evaluate one source without confusing native screen-recorded content with fallback capture.

    A user may intentionally send a screen recording. That is still accepted when WeChat
    exports the exact native attachment. What is forbidden is an automation-created
    recording of the WeChat player, desktop, or scrcpy window used as a substitute.
    """
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return VideoSourceDecision(False, "missing", f"source video does not exist: {resolved}")

    native_manifest = resolved.parent / NATIVE_MANIFEST
    if native_manifest.is_file():
        payload = read_manifest(native_manifest)
        source_kind = str(payload.get("source_kind") or "")
        manifest_host = Path(str(payload.get("host_path") or "")).expanduser()
        manifest_sha = str(payload.get("sha256") or "").lower()
        if str(payload.get("status") or "") != "verified":
            return VideoSourceDecision(
                False,
                "native-export-unverified",
                "native export manifest is not verified",
                str(native_manifest),
                source_kind,
            )
        if source_kind not in ACCEPTED_NATIVE_KINDS:
            return VideoSourceDecision(
                False,
                "native-export-kind-rejected",
                f"unsupported native source kind: {source_kind or '<missing>'}",
                str(native_manifest),
                source_kind,
            )
        try:
            host_matches = manifest_host.resolve() == resolved
        except OSError:
            host_matches = False
        if not host_matches:
            return VideoSourceDecision(
                False,
                "native-export-path-mismatch",
                "native export manifest does not identify this exact host file",
                str(native_manifest),
                source_kind,
            )
        if not manifest_sha or sha256_file(resolved) != manifest_sha:
            return VideoSourceDecision(
                False,
                "native-export-checksum-mismatch",
                "native export checksum does not match this exact host file",
                str(native_manifest),
                source_kind,
            )
        if bool(payload.get("automation_screen_capture")):
            return VideoSourceDecision(
                False,
                "automation-capture-rejected",
                "native export manifest identifies an automation screen capture",
                str(native_manifest),
                source_kind,
            )
        if (
            source_kind == "wechat_android_native_album_export"
            and payload.get("device_copy_removed") is not True
        ):
            return VideoSourceDecision(
                False,
                "phone-export-cleanup-required",
                "native host copy is not complete until the temporary phone export is removed",
                str(native_manifest),
                source_kind,
            )
        return VideoSourceDecision(
            True,
            "verified-native-source",
            "exact native WeChat media export verified by path and checksum",
            str(native_manifest),
            source_kind,
        )

    filename = resolved.name.lower()
    if any(marker in filename for marker in SUSPICIOUS_NAME_MARKERS):
        return VideoSourceDecision(
            False,
            "automation-capture-rejected",
            "automation-created screen/scrcpy capture filenames cannot be used as source video",
        )

    nearby = nearest_provenance_manifest(resolved)
    if nearby is not None:
        payload = read_manifest(nearby)
        flattened = json.dumps(payload, ensure_ascii=False).lower()
        if any(marker in flattened for marker in CAPTURE_MARKERS):
            return VideoSourceDecision(
                False,
                "automation-capture-rejected",
                "nearby provenance identifies a player/screen capture fallback",
                str(nearby),
                str(payload.get("source_kind") or ""),
            )

    if is_android_intake_path(resolved):
        return VideoSourceDecision(
            False,
            "native-export-proof-required",
            "Android WeChat intake requires a verified native album/CDN export manifest",
            str(nearby or ""),
        )

    return VideoSourceDecision(
        True,
        "non-android-source",
        "source is outside Android WeChat intake and has no capture-fallback provenance",
        str(nearby or ""),
    )


def require_publishable_video_source(path: Path) -> VideoSourceDecision:
    decision = evaluate_publishable_video_source(path)
    if not decision.accepted:
        raise UnpublishableVideoSource(
            f"WECHAT_NATIVE_SOURCE_REQUIRED: {decision.reason}; "
            "obtain the exact native attachment or stop without publishing"
        )
    return decision


def nearest_provenance_manifest(path: Path) -> Path | None:
    names = (
        "verified-intake.json",
        "verified-capture.json",
        "source-manifest.json",
        "native-source-recovery.json",
    )
    current = path.parent
    for _ in range(3):
        for name in names:
            candidate = current / name
            if candidate.is_file():
                return candidate
        current = current.parent
    return None


def is_android_intake_path(path: Path) -> bool:
    parts = tuple(part.lower() for part in path.parts)
    return "wechat_android_intake" in parts


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
