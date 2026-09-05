#!/usr/bin/env python3
"""Capture one exact WeChat Channels player's audio with visual identity gates."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
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
import sys
import time
from typing import Any, Iterator

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None

IDENTITY_T2S = OpenCC("t2s") if OpenCC is not None else None


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_CACHE_ROOT = PRIVATE / "shipinhao_media_transcripts"
GUI_LOCK = PRIVATE / "wechat_gui_send.lock"
DEFAULT_TARGETS = PRIVATE / "wechat_send_targets.local.json"


class CaptureFailure(RuntimeError):
    """Source-scoped capture failure with a stable machine-readable reason."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        failure_stage: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.failure_stage = failure_stage
        self.evidence = evidence or {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument(
        "--cover-image",
        type=Path,
        help="Exact card cover cached from the same Finder object; used only as a visual identity anchor.",
    )
    parser.add_argument("--identity-term", action="append", default=[])
    parser.add_argument("--min-term-matches", type=int, default=1)
    parser.add_argument("--display", default=":97")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--chat", default="", help="Open the exact recent card from this guarded chat before capture.")
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--max-scrolls", type=int, default=12)
    parser.add_argument("--scroll-clicks", type=int, default=5)
    parser.add_argument("--player-open-timeout", type=float, default=8.0)
    parser.add_argument("--audio-stream-timeout", type=float, default=12.0)
    parser.add_argument("--expected-duration-seconds", type=float, default=0.0)
    parser.add_argument(
        "--recover-share-link-first",
        action="store_true",
        help="Try the exact native player's read-only Copy Link action before audio capture.",
    )
    parser.add_argument("--lock-timeout", type=float, default=0.0)
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
        capture_args = {
            "object_id": args.object_id,
            "title": args.title,
            "author": args.author,
            "identity_terms": terms,
            "min_term_matches": max(1, args.min_term_matches),
            "display": args.display,
            "output_dir": output_dir,
            "interval": max(0.5, args.interval),
            "loss_polls": max(2, args.loss_polls),
            "max_seconds": max(5.0, args.max_seconds),
            "audio_stream_timeout": max(2.0, args.audio_stream_timeout),
            "expected_duration_seconds": max(0.0, args.expected_duration_seconds),
            "recover_share_link_first": bool(args.recover_share_link_first),
        }
        if args.chat.strip():
            cover_image = args.cover_image
            if cover_image is None:
                candidate = DEFAULT_CACHE_ROOT / safe_component(args.object_id) / "card-cover.jpg"
                cover_image = candidate if candidate.is_file() else None
            result = capture_exact_card_from_chat(
                chat=args.chat.strip(),
                targets_file=args.targets_file,
                max_scrolls=max(1, args.max_scrolls),
                scroll_clicks=max(1, args.scroll_clicks),
                player_open_timeout=max(2.0, args.player_open_timeout),
                lock_timeout=max(0.0, args.lock_timeout),
                cover_image=cover_image,
                **capture_args,
            )
        else:
            result = capture_exact_player(lock_timeout=max(0.0, args.lock_timeout), **capture_args)
    except Exception as exc:
        result = {
            "status": "failed",
            "read_only": True,
            "visual_identity_verified": False,
            "error": f"{type(exc).__name__}: {str(exc)[:700]}",
        }
        if isinstance(exc, CaptureFailure):
            result.update(
                error_code=exc.error_code,
                failure_stage=exc.failure_stage,
                source_card_found=bool(exc.evidence.get("source_card_found")),
                card_open=exc.evidence,
            )
        if args.chat.strip():
            result["source_chat"] = args.chat.strip()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) if args.json else result.get("manifest_path", result["status"]))
    return 0 if result.get("status") in {"verified", "share_link_recovered"} else 2


def capture_exact_card_from_chat(
    *,
    chat: str,
    targets_file: Path,
    max_scrolls: int,
    scroll_clicks: int,
    player_open_timeout: float,
    lock_timeout: float,
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
    audio_stream_timeout: float,
    expected_duration_seconds: float,
    recover_share_link_first: bool = False,
    cover_image: Path | None = None,
) -> dict[str, Any]:
    """Open one source-bound card from its chat, then capture its exact player."""
    require_tools("xdotool", "import", "convert", "tesseract")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    gui = load_wechat_gui_module()
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    targets, _ = gui.load_targets([chat], targets_file.expanduser().resolve(), "")
    if len(targets) != 1:
        raise RuntimeError(f"no unique guarded WeChat target is configured for {chat}")
    target = targets[0]

    with exclusive_gui_lock(GUI_LOCK, timeout_seconds=lock_timeout):
        main_window = gui.find_wechat_window(env)
        if not main_window:
            raise RuntimeError(f"no visible native WeChat chat window was found on {display}")
        main_window_ids = {str(main_window.wid)}
        close_channels_players(env, excluded_window_ids=main_window_ids)
        gui.focus(env, main_window)
        guard = gui.open_target(
            env,
            main_window,
            target,
            0.5,
            output_dir,
            "source-chat",
            False,
            True,
            False,
            relaxed_visible_fallback_allowed=False,
        )
        if not guard.get("ok"):
            raise RuntimeError(f"exact source chat title guard failed for {chat}")

        player, open_evidence = open_exact_card_from_visible_history(
            env=env,
            gui=gui,
            main_window=main_window,
            output_dir=output_dir,
            identity_terms=identity_terms,
            min_term_matches=min_term_matches,
            max_scrolls=max_scrolls,
            scroll_clicks=scroll_clicks,
            player_open_timeout=player_open_timeout,
            cover_image=cover_image,
            excluded_window_ids=main_window_ids,
        )
        if not player:
            if open_evidence.get("source_card_found"):
                raise CaptureFailure(
                    "the exact Finder card was found, but this WeChat client did not open its player",
                    error_code="finder_player_unavailable",
                    failure_stage="player_open",
                    evidence=open_evidence,
                )
            raise CaptureFailure(
                "the exact Finder card was not found in the bounded recent chat history",
                error_code="finder_card_not_found",
                failure_stage="card_scan",
                evidence=open_evidence,
            )
        try:
            share_link_result: dict[str, Any] = {}
            if recover_share_link_first:
                share_link_result = recover_share_link_from_player(
                    player=player,
                    env=env,
                    output_dir=output_dir,
                    identity_terms=identity_terms,
                    min_term_matches=min_term_matches,
                )
                if share_link_result.get("status") == "verified":
                    return {
                        "status": "share_link_recovered",
                        "read_only": True,
                        "public_actions": False,
                        "visual_identity_verified": True,
                        "source_chat": chat,
                        "object_id": object_id,
                        "title": title,
                        "author": author,
                        "share_url": share_link_result["share_url"],
                        "share_url_sha256": share_link_result["share_url_sha256"],
                        "card_open": open_evidence,
                    }
            result = capture_exact_player(
                object_id=object_id,
                title=title,
                author=author,
                identity_terms=identity_terms,
                min_term_matches=min_term_matches,
                display=display,
                output_dir=output_dir,
                interval=interval,
                loss_polls=loss_polls,
                max_seconds=max_seconds,
                audio_stream_timeout=audio_stream_timeout,
                expected_duration_seconds=expected_duration_seconds,
                gui_lock_held=True,
                player_window_id=str(player["id"]),
            )
            if share_link_result:
                result["share_link_recovery"] = {
                    key: share_link_result.get(key)
                    for key in ("status", "error_code", "menu_detected")
                    if share_link_result.get(key) not in {None, ""}
                }
            result["source_chat"] = chat
            result["card_open"] = open_evidence
            manifest_path = Path(str(result.get("manifest_path") or ""))
            if manifest_path.is_file():
                persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
                persisted["source_chat"] = chat
                persisted["card_open"] = open_evidence
                manifest_path.write_text(
                    json.dumps(persisted, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                manifest_path.chmod(0o600)
            return result
        finally:
            close_channels_players(env, excluded_window_ids=main_window_ids)
            gui.focus(env, main_window)


def recover_share_link_from_player(
    *,
    player: dict[str, Any],
    env: dict[str, str],
    output_dir: Path,
    identity_terms: list[str],
    min_term_matches: int,
) -> dict[str, Any]:
    """Copy one exact player's public share link through its native context menu."""

    if not shutil.which("xclip"):
        return {"status": "unavailable", "error_code": "clipboard_tool_missing"}
    evidence = capture_identity_evidence(
        player,
        output_dir / "share-link-identity",
        env,
        identity_terms,
        min_term_matches,
    )
    if not evidence.get("matched"):
        return {"status": "failed", "error_code": "player_identity_mismatch"}

    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        env=env,
        input="",
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    center_x = int(player.get("x") or 0) + int(player.get("width") or 0) // 2
    center_y = int(player.get("y") or 0) + int(player.get("height") or 0) // 2
    run(
        ["xdotool", "windowfocus", str(player["id"]), "mousemove", str(center_x), str(center_y), "click", "3"],
        env=env,
        check=False,
    )
    time.sleep(0.7)
    menu_image = output_dir / "share-link-menu.png"
    run(["import", "-window", "root", str(menu_image)], env=env, check=False)
    ocr = run(
        [
            "tesseract",
            str(menu_image),
            "stdout",
            "-l",
            "chi_sim+chi_tra+eng",
            "--psm",
            "11",
            "tsv",
        ],
        env=env,
        check=False,
    )
    candidates = copy_link_menu_candidates(ocr.stdout if ocr.returncode == 0 else "")
    if not candidates:
        run(["xdotool", "key", "Escape"], env=env, check=False)
        return {
            "status": "unavailable",
            "error_code": "native_copy_link_action_missing",
            "menu_detected": False,
        }

    candidate = candidates[0]
    run(
        [
            "xdotool",
            "mousemove",
            str(int(candidate["center_x"])),
            str(int(candidate["center_y"])),
            "click",
            "1",
        ],
        env=env,
        check=False,
    )
    time.sleep(0.5)
    clipboard = run(
        ["xclip", "-selection", "clipboard", "-o"],
        env=env,
        check=False,
    ).stdout
    try:
        from shipinhao_share_link_resolver import extract_share_urls
    except ImportError:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from shipinhao_share_link_resolver import extract_share_urls

    urls = extract_share_urls(clipboard)
    if len(urls) != 1:
        return {
            "status": "failed",
            "error_code": "native_copy_link_invalid_clipboard",
            "menu_detected": True,
        }
    share_url = urls[0]
    return {
        "status": "verified",
        "menu_detected": True,
        "share_url": share_url,
        "share_url_sha256": hashlib.sha256(share_url.encode("utf-8")).hexdigest(),
    }


def copy_link_menu_candidates(tsv_text: str) -> list[dict[str, Any]]:
    """Locate explicit Copy Link menu rows; never infer a click from position alone."""

    rows: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in parse_tesseract_tsv_words(tsv_text):
        key = (str(item["block_num"]), str(item["par_num"]), str(item["line_num"]))
        rows.setdefault(key, []).append(item)
    candidates: list[dict[str, Any]] = []
    accepted = {"复制链接", "複製連結", "複製鏈接", "copylink"}
    for words in rows.values():
        words.sort(key=lambda item: int(item["left"]))
        label = "".join(str(item["text"]) for item in words)
        normalized = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", label.casefold())
        if not any(value in normalized for value in accepted):
            continue
        left = min(int(item["left"]) for item in words)
        top = min(int(item["top"]) for item in words)
        right = max(int(item["left"]) + int(item["width"]) for item in words)
        bottom = max(int(item["top"]) + int(item["height"]) for item in words)
        candidates.append(
            {
                "label": label,
                "center_x": (left + right) / 2.0,
                "center_y": (top + bottom) / 2.0,
            }
        )
    return candidates


def open_exact_card_from_visible_history(
    *,
    env: dict[str, str],
    gui: Any,
    main_window: Any,
    output_dir: Path,
    identity_terms: list[str],
    min_term_matches: int,
    max_scrolls: int,
    scroll_clicks: int,
    player_open_timeout: float,
    cover_image: Path | None = None,
    excluded_window_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Scan recent visible messages and open only a card whose player identity matches."""
    region = message_pane_region(main_window)
    gui.focus(env, main_window)
    jump_to_latest_message(env=env, gui=gui, main_window=main_window, region=region, output_dir=output_dir)
    attempts: list[dict[str, Any]] = []
    for scan_index in range(max_scrolls):
        screenshot_path = output_dir / f"card-scan-{scan_index:02d}.png"
        crop_path = output_dir / f"card-scan-{scan_index:02d}-messages.png"
        tsv = capture_message_pane_tsv(
            env=env,
            gui=gui,
            main_window=main_window,
            region=region,
            screenshot_path=screenshot_path,
            crop_path=crop_path,
        )
        line_candidates = ocr_line_candidates(tsv, identity_terms)
        exact_cover = exact_cover_candidates(
            screenshot_path,
            cover_image,
            region=region,
        )
        play_candidates = play_button_candidates(crop_path, source_side_ratio=0.56)
        identity_bound = associate_play_candidates_with_identity(
            tsv,
            play_candidates,
            identity_terms,
            min_term_matches,
            source_side_width=float(region["width"]) * 0.56,
        )
        candidates = [*exact_cover, *identity_bound]
        if not candidates:
            # A card can omit or obscure its play icon. Only use OCR fallback
            # on the received/source side of the message pane; this excludes
            # our own right-aligned summaries that may repeat the same title.
            candidates.extend(
                candidate
                for candidate in line_candidates
                if float(candidate["center_x"]) < float(region["width"]) * 0.56
                and float(candidate["center_y"]) < float(region["height"]) - 55
            )
        candidates = deduplicate_click_candidates(candidates)
        for candidate_index, candidate in enumerate(candidates[:8]):
            click_x = region["left"] + int(candidate["center_x"])
            click_y = region["top"] + int(candidate["center_y"])
            gui.focus(env, main_window)
            gui.click(env, main_window.x + click_x, main_window.y + click_y)
            kind = str(candidate.get("kind") or "ocr_identity")
            open_timeout = player_open_timeout if kind in {"exact_cover", "play_control"} else min(3.0, player_open_timeout)
            player = wait_for_channels_window(
                env,
                timeout=open_timeout,
                excluded_window_ids=excluded_window_ids,
            )
            attempt = {
                "scan": scan_index,
                "candidate": candidate_index,
                "candidate_kind": kind,
                "matched_terms": candidate["matched_terms"],
                "text_preview": compact_text(candidate["text"], 120),
            }
            if candidate.get("match_confidence") is not None:
                attempt["match_confidence"] = round(float(candidate["match_confidence"]), 4)
            if not player:
                attempt["result"] = "no_player"
                attempts.append(attempt)
                continue
            evidence = wait_for_player_identity(
                player=player,
                stem=output_dir / f"card-open-{scan_index:02d}-{candidate_index:02d}",
                env=env,
                identity_terms=identity_terms,
                min_term_matches=min_term_matches,
                timeout=max(8.0, player_open_timeout),
            )
            attempt["result"] = "identity_match" if evidence["matched"] else "identity_mismatch"
            attempt["player_matched_terms"] = evidence["matched_terms"]
            attempts.append(attempt)
            if evidence["matched"]:
                return player, {
                    "status": "identity_verified",
                    "scan": scan_index,
                    "matched_terms": evidence["matched_terms"],
                    "attempt_count": len(attempts),
                }
            close_channels_players(env, excluded_window_ids=excluded_window_ids)
            gui.focus(env, main_window)

        gui.focus(env, main_window)
        gui.run(
            [
                "xdotool",
                "mousemove",
                "--window",
                main_window.wid,
                str(region["left"] + region["width"] // 2),
                str(region["top"] + region["height"] // 2),
                "click",
                "--repeat",
                str(scroll_clicks),
                "--delay",
                "70",
                "4",
            ],
            env=env,
            check=False,
        )
        time.sleep(0.8)
    matched_terms = unique_strings(
        [term for attempt in attempts for term in attempt.get("matched_terms", [])]
    )
    source_card_found = bool(attempts)
    return None, {
        "status": "source_card_found_player_unavailable" if source_card_found else "not_found",
        "source_card_found": source_card_found,
        "matched_terms": matched_terms,
        "attempt_count": len(attempts),
        "scans": max_scrolls,
    }


def jump_to_latest_message(
    *,
    env: dict[str, str],
    gui: Any,
    main_window: Any,
    region: dict[str, int],
    output_dir: Path,
) -> bool:
    screenshot_path = output_dir / "latest-jump.png"
    crop_path = output_dir / "latest-jump-messages.png"
    tsv = capture_message_pane_tsv(
        env=env,
        gui=gui,
        main_window=main_window,
        region=region,
        screenshot_path=screenshot_path,
        crop_path=crop_path,
    )
    visual_candidate = latest_message_button_candidate(screenshot_path, region=region)
    candidates = ocr_line_candidates(tsv, ["Go to the latest message", "最新消息"])
    clicked_button = False
    if visual_candidate:
        click_x = int(visual_candidate["center_x"])
        click_y = int(visual_candidate["center_y"])
    elif candidates:
        candidate = candidates[0]
        click_x = region["left"] + int(candidate["center_x"])
        click_y = region["top"] + int(candidate["center_y"])
    else:
        button_crop = output_dir / "latest-jump-button.png"
        button_x = max(0, main_window.width - 255)
        button_y = max(0, main_window.height - 230)
        gui.run(
            [
                "convert",
                str(screenshot_path),
                "-crop",
                f"250x90+{button_x}+{button_y}",
                "-resize",
                "400%",
                "-colorspace",
                "Gray",
                "-contrast-stretch",
                "2%x2%",
                str(button_crop),
            ],
            env=env,
        )
        proc = gui.run(
            ["tesseract", str(button_crop), "stdout", "-l", "eng", "--psm", "7"],
            env=env,
            check=False,
        )
        normalized = normalize_identity(proc.stdout)
        if "gotothelatestmessage" in normalized:
            click_x = main_window.width - 125
            click_y = main_window.height - 183
        else:
            click_x = click_y = 0
    if click_x and click_y:
        gui.click(env, main_window.x + click_x, main_window.y + click_y)
        clicked_button = True
        time.sleep(1.0)

    # Compact/icon-only clients often render the jump control without OCR-able
    # text. Wheel-down events are delivered to the pane under the pointer and
    # do not activate cards, links, or the composer, so this is a safe bounded
    # fallback and also normalizes partially completed button jumps.
    fallback = gui.run(
        [
            "xdotool",
            "mousemove",
            "--window",
            main_window.wid,
            str(region["left"] + region["width"] // 2),
            str(region["top"] + region["height"] // 2),
            "click",
            "--repeat",
            "120",
            "--delay",
            "12",
            "5",
        ],
        env=env,
        check=False,
    )
    time.sleep(1.0)
    return clicked_button or fallback.returncode == 0


def latest_message_button_candidate(
    screenshot_path: Path,
    *,
    region: dict[str, int],
) -> dict[str, float] | None:
    """Find WeChat's green-on-white latest-message control without OCR."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    image = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    blue, green, red = cv2.split(image)
    channel_max = np.maximum.reduce([blue, green, red])
    channel_min = np.minimum.reduce([blue, green, red])
    white = (
        (blue > 225)
        & (green > 225)
        & (red > 225)
        & ((channel_max.astype(np.int16) - channel_min.astype(np.int16)) < 18)
    )
    green_ink = (
        (green.astype(np.int16) > red.astype(np.int16) + 22)
        & (green.astype(np.int16) > blue.astype(np.int16) + 12)
        & (green > 100)
    )
    local_white = cv2.boxFilter(white.astype(np.float32), -1, (15, 15), normalize=True)
    mask = (green_ink & (local_white > 0.45)).astype(np.uint8) * 255

    left = max(0, int(region["left"] + float(region["width"]) * 0.52))
    right = min(image.shape[1], int(region["left"] + region["width"]))
    top = max(0, int(region["top"] + region["height"] - 90))
    bottom = min(image.shape[0], int(region["top"] + region["height"]) + 8)
    bounded = np.zeros_like(mask)
    bounded[top:bottom, left:right] = mask[top:bottom, left:right]
    bounded = cv2.morphologyEx(
        bounded,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7)),
    )
    count, _, stats, centers = cv2.connectedComponentsWithStats(bounded)
    candidates: list[dict[str, float]] = []
    for index in range(1, count):
        x, y, width, height, area = [int(value) for value in stats[index]]
        if width < 80 or width > 280 or height < 5 or height > 42 or area < 100:
            continue
        candidates.append(
            {
                "center_x": float(centers[index][0]),
                "center_y": float(centers[index][1]),
                "score": float(width * 10 + area - abs(bottom - (y + height)) * 2),
            }
        )
    return max(candidates, key=lambda item: item["score"], default=None)


def message_pane_region(window: Any) -> dict[str, int]:
    left = int(window.width * 0.36)
    top = 68
    width = max(320, window.width - left - 8)
    height = max(240, window.height - top - 160)
    return {"left": left, "top": top, "width": width, "height": height}


def capture_message_pane_tsv(
    *,
    env: dict[str, str],
    gui: Any,
    main_window: Any,
    region: dict[str, int],
    screenshot_path: Path,
    crop_path: Path,
) -> str:
    gui.run(["import", "-window", main_window.wid, str(screenshot_path)], env=env)
    gui.run(
        [
            "convert",
            str(screenshot_path),
            "-crop",
            f"{region['width']}x{region['height']}+{region['left']}+{region['top']}",
            "-colorspace",
            "Gray",
            "-resize",
            "160%",
            str(crop_path),
        ],
        env=env,
    )
    proc = gui.run(
        ["tesseract", str(crop_path), "stdout", "-l", "chi_sim+chi_tra+eng", "--psm", "11", "tsv"],
        env=env,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def parse_tesseract_tsv_words(tsv_text: str) -> list[dict[str, Any]]:
    """Parse Tesseract TSV without CSV quote semantics.

    OCR text may itself be a single or double quote. ``csv.DictReader`` treats
    those as quoting delimiters and can merge subsequent TSV records, which in
    turn associates text from a later chat bubble with the wrong video card.
    Tesseract has eleven fixed metadata columns, so split each row at most
    eleven times and preserve the final field literally.
    """
    words: list[dict[str, Any]] = []
    for line in str(tsv_text or "").splitlines():
        parts = line.split("\t", 11)
        if len(parts) != 12 or parts[0] == "level":
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            words.append(
                {
                    "text": text,
                    "block_num": parts[2],
                    "par_num": parts[3],
                    "line_num": parts[4],
                    "left": int(float(parts[6])),
                    "top": int(float(parts[7])),
                    "width": int(float(parts[8])),
                    "height": int(float(parts[9])),
                }
            )
        except ValueError:
            continue
    return words


def ocr_line_candidates(tsv_text: str, identity_terms: list[str]) -> list[dict[str, Any]]:
    """Return OCR lines matching source identity, with coordinates restored from 160% scale."""
    rows: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in parse_tesseract_tsv_words(tsv_text):
        key = (str(item["block_num"]), str(item["par_num"]), str(item["line_num"]))
        rows.setdefault(key, []).append(item)
    candidates: list[dict[str, Any]] = []
    for words in rows.values():
        words.sort(key=lambda item: (item["left"], item["top"]))
        text = "".join(str(item["text"]) for item in words)
        matched, match_score = match_identity_terms(text, identity_terms)
        if not matched:
            continue
        left = min(int(item["left"]) for item in words)
        top = min(int(item["top"]) for item in words)
        right = max(int(item["left"]) + int(item["width"]) for item in words)
        bottom = max(int(item["top"]) + int(item["height"]) for item in words)
        candidates.append(
            {
                "text": text,
                "matched_terms": matched,
                "center_x": (left + right) / 3.2,
                "center_y": (top + bottom) / 3.2,
                "score": match_score,
                "kind": "ocr_identity",
            }
        )
    candidates.sort(key=lambda item: (-int(item["score"]), -float(item["center_y"])))
    return candidates


def associate_play_candidates_with_identity(
    tsv_text: str,
    play_candidates: list[dict[str, Any]],
    identity_terms: list[str],
    min_term_matches: int,
    source_side_width: float | None = None,
) -> list[dict[str, Any]]:
    """Bind play controls to OCR evidence inside the same visible card.

    The bounded neighborhood covers a normal portrait/landscape Finder card,
    while excluding a later right-aligned summary or the next feed card. This
    prevents a correct title elsewhere in the chat from authorizing a click on
    an unrelated play button.
    """
    words = parse_tesseract_tsv_words(tsv_text)
    result: list[dict[str, Any]] = []
    for play in play_candidates:
        play_x = float(play.get("center_x") or 0)
        play_y = float(play.get("center_y") or 0)
        if source_side_width is not None and play_x >= source_side_width:
            continue
        nearby = []
        for word in words:
            word_x = (float(word["left"]) + float(word["width"]) / 2.0) / 1.6
            word_y = (float(word["top"]) + float(word["height"]) / 2.0) / 1.6
            if abs(word_x - play_x) <= 185 and play_y - 185 <= word_y <= play_y + 185:
                nearby.append(str(word["text"]))
        # Tesseract TSV rows are already emitted in reading order. Sorting
        # individual words by their slightly different baselines can scramble
        # Chinese text from one line (for example, 昨天的自己), causing the
        # exact card's visible play control to be rejected.
        evidence_text = " ".join(nearby)
        matched, match_score = match_identity_terms(evidence_text, identity_terms)
        if len(matched) < max(1, min_term_matches):
            continue
        result.append(
            {
                **play,
                "text": f"identity-bound video card: {compact_text(evidence_text, 180)}",
                "kind": str(play.get("kind") or "play_control"),
                "matched_terms": matched,
                "score": 1000 + match_score + int(play.get("score") or 0),
            }
        )
    result.sort(key=lambda item: (-int(item["score"]), -float(item["center_y"])))
    return result


def match_identity_terms(text: str, identity_terms: list[str]) -> tuple[list[str], int]:
    normalized = normalize_identity(text)
    matched: list[str] = []
    score = 0
    for term in identity_terms:
        variants = identity_term_variants(term)
        strengths = [len(variant) for variant in variants if variant and variant in normalized]
        if not strengths:
            continue
        matched.append(term)
        score += max(strengths)
    return unique_strings(matched), score


def identity_term_variants(term: str) -> list[str]:
    normalized = normalize_identity(term)
    if not normalized:
        return []
    variants = [normalized]
    pieces = [normalize_identity(piece) for piece in re.split(r"[#|｜:：\-—–_/]+", str(term or ""))]
    for piece in [normalized, *pieces]:
        if len(piece) >= 7:
            variants.extend((piece[:6], piece[-6:]))
        elif len(piece) >= 4:
            variants.append(piece)
    return unique_strings(variants)


def play_button_candidates(
    image_path: Path,
    *,
    source_side_ratio: float | None = None,
) -> list[dict[str, Any]]:
    """Detect visible circular play controls without making OpenCV mandatory."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []
    blurred = cv2.GaussianBlur(image, (5, 5), 1.2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=55,
        param1=100,
        param2=40,
        minRadius=24,
        maxRadius=42,
    )
    if circles is None:
        return []
    height, width = image.shape[:2]
    candidates: list[dict[str, Any]] = []
    for x, y, radius in np.round(circles[0]).astype(int):
        original_x = float(x) / 1.6
        original_y = float(y) / 1.6
        if original_y < 35 or original_y > height / 1.6 - 55:
            continue
        if original_x < 30 or original_x > width / 1.6 - 30:
            continue
        if source_side_ratio is not None and original_x >= (width / 1.6) * source_side_ratio:
            continue
        candidates.append(
            {
                "text": "visible video play control",
                "kind": "play_control",
                "matched_terms": [],
                "center_x": original_x,
                "center_y": original_y,
                "score": max(1, 80 - abs(int(radius) - 48)),
            }
        )
    candidates.sort(key=lambda item: (-float(item["center_y"]), -int(item["score"])))
    return candidates[:6]


def exact_cover_candidates(
    screenshot_path: Path,
    cover_image: Path | None,
    *,
    region: dict[str, int],
    min_confidence: float = 0.70,
) -> list[dict[str, Any]]:
    """Locate the exact same-object cover in the received side of the chat.

    Finder media URLs can expire while the cover remains cacheable. Matching the
    cached cover gives the GUI fallback a stronger click target than OCR alone
    and prevents a repeated title in our own right-aligned reply from winning.
    """
    if cover_image is None or not cover_image.is_file():
        return []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_GRAYSCALE)
    cover = cv2.imread(str(cover_image), cv2.IMREAD_GRAYSCALE)
    if screenshot is None or cover is None:
        return []
    left = max(0, int(region["left"]))
    top = max(0, int(region["top"]))
    right = min(screenshot.shape[1], left + int(float(region["width"]) * 0.60))
    bottom = min(screenshot.shape[0], top + int(region["height"]))
    search = screenshot[top:bottom, left:right]
    if search.size == 0:
        return []
    best: dict[str, Any] = {}
    for scale in np.linspace(0.20, 0.90, 36):
        width = max(24, int(round(cover.shape[1] * float(scale))))
        height = max(24, int(round(cover.shape[0] * float(scale))))
        if width >= search.shape[1] or height >= search.shape[0]:
            continue
        resized = cv2.resize(cover, (width, height), interpolation=cv2.INTER_AREA)
        match = cv2.matchTemplate(search, resized, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, location = cv2.minMaxLoc(match)
        if float(confidence) > float(best.get("match_confidence") or -1):
            best = {
                "text": "exact same-object Finder card cover",
                "kind": "exact_cover",
                "matched_terms": [],
                "center_x": float(location[0] + width / 2.0),
                "center_y": float(location[1] + height / 2.0),
                "width": width,
                "height": height,
                "match_confidence": float(confidence),
                "score": 5000 + int(float(confidence) * 1000),
            }
    return [best] if float(best.get("match_confidence") or 0.0) >= min_confidence else []


def deduplicate_click_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        x = float(candidate.get("center_x") or 0)
        y = float(candidate.get("center_y") or 0)
        if any(abs(x - float(item["center_x"])) < 28 and abs(y - float(item["center_y"])) < 28 for item in result):
            continue
        result.append(candidate)
    return result


def wait_for_channels_window(
    env: dict[str, str],
    *,
    timeout: float,
    excluded_window_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window = find_channels_window(env, excluded_window_ids=excluded_window_ids)
        if window:
            return window
        time.sleep(0.25)
    return None


def wait_for_player_identity(
    *,
    player: dict[str, Any],
    stem: Path,
    env: dict[str, str],
    identity_terms: list[str],
    min_term_matches: int,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {
        "matched": False,
        "matched_terms": [],
        "identity_terms": identity_terms,
        "ocr_preview": "",
        "screenshot": "",
    }
    poll = 0
    while time.monotonic() < deadline:
        last = capture_identity_evidence(
            player,
            stem.with_name(f"{stem.name}-loading-{poll:02d}"),
            env,
            identity_terms,
            min_term_matches,
            retain_image=False,
        )
        if last["matched"]:
            return capture_identity_evidence(player, stem, env, identity_terms, min_term_matches)
        poll += 1
        time.sleep(0.8)
    return last


def close_channels_players(env: dict[str, str], *, excluded_window_ids: set[str] | None = None) -> None:
    while True:
        window = find_channels_window(env, excluded_window_ids=excluded_window_ids)
        if not window:
            return
        run(["xdotool", "windowfocus", str(window["id"]), "key", "Escape"], env=env, check=False)
        time.sleep(0.5)
        if find_channels_window(env, excluded_window_ids=excluded_window_ids):
            run(["xdotool", "windowclose", str(window["id"])], env=env, check=False)
            time.sleep(0.5)
        else:
            return


def load_wechat_gui_module() -> Any:
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import wechat_gui_send

    return wechat_gui_send


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
    audio_stream_timeout: float = 12.0,
    expected_duration_seconds: float = 0.0,
    lock_timeout: float = 0.0,
    gui_lock_held: bool = False,
    player_window_id: str = "",
) -> dict[str, Any]:
    require_tools("xdotool", "import", "convert", "tesseract", "pw-dump", "pw-record", "ffmpeg", "ffprobe")
    if not identity_terms:
        raise RuntimeError("no distinctive visual identity terms were supplied or derived")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    env = os.environ.copy()
    env["DISPLAY"] = display
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    lock_context = nullcontext() if gui_lock_held else exclusive_gui_lock(GUI_LOCK, timeout_seconds=lock_timeout)
    with lock_context:
        window = window_geometry(player_window_id, env) if player_window_id else find_channels_window(env)
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
        stream = wait_for_wechat_audio_stream(
            display=display,
            window=window,
            env=env,
            timeout=audio_stream_timeout,
        )
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
                if expected_duration_seconds > 0 and elapsed >= min(
                    max_seconds,
                    expected_duration_seconds + max(1.5, interval),
                ):
                    stop_reason = "expected_duration_elapsed"
                    break
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
        valid_duration_stop = stop_reason == "expected_duration_elapsed" and expected_duration_seconds > 0
        if not valid_duration_stop and (stop_reason != "visual_identity_lost" or first_loss is None):
            raise RuntimeError(f"capture ended without a verified player identity transition ({stop_reason or 'unknown'})")
        raw_probe = probe_audio(raw_audio)
        raw_duration = float(raw_probe["duration_seconds"])
        # Map the first visual identity loss into the recorded stream clock. This
        # remains correct even when a virtual audio clock differs slightly from wall time.
        if valid_duration_stop:
            visual_cutoff = min(wall_duration, expected_duration_seconds)
            audio_cutoff = min(raw_duration, max(0.5, expected_duration_seconds))
        else:
            visual_cutoff = max(last_match, float(first_loss) - interval * 0.25)
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
        "expected_duration_seconds": round(expected_duration_seconds, 3),
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
    matched_terms, match_score = match_identity_terms(combined, terms)
    result = {
        "matched": len(matched_terms) >= min_matches,
        "matched_terms": matched_terms,
        "match_score": match_score,
        "identity_terms": terms,
        "ocr_preview": compact_text(combined, 500),
        "screenshot": str(screenshot) if retain_image else "",
        "screenshot_sha256": sha256_file(screenshot),
    }
    if not retain_image:
        screenshot.unlink(missing_ok=True)
    return result


def find_channels_window(
    env: dict[str, str],
    *,
    excluded_window_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    # Some Linux builds title the main client "Weixin" and the player
    # "WeChat"; others title both alike. The source-bound path excludes the
    # already-known main window before accepting either title.
    pattern = "^(WeChat|Weixin)$" if excluded_window_ids else "^WeChat$"
    proc = run(["xdotool", "search", "--onlyvisible", "--name", pattern], env=env, check=False)
    candidates = [window_geometry(wid, env) for wid in proc.stdout.split()]
    excluded = {str(value) for value in (excluded_window_ids or set())}
    candidates = [
        item
        for item in candidates
        if item
        and str(item["id"]) not in excluded
        and item["width"] >= 600
        and item["height"] >= 600
    ]
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


def wait_for_wechat_audio_stream(
    *,
    display: str,
    window: dict[str, Any],
    env: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    """Wait for playback audio, starting the identity-verified player once if needed."""
    deadline = time.monotonic() + max(2.0, timeout)
    activated = False
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return find_wechat_audio_stream(display)
        except RuntimeError as exc:
            last_error = str(exc)
        if not activated and time.monotonic() + 1.0 < deadline:
            center_x = int(window.get("x") or 0) + int(window.get("width") or 0) // 2
            center_y = int(window.get("y") or 0) + int(window.get("height") or 0) // 2
            run(
                ["xdotool", "mousemove", str(center_x), str(center_y), "click", "1"],
                env=env,
                check=False,
            )
            activated = True
        time.sleep(0.4)
    raise CaptureFailure(
        last_error or "no active WeChat player audio stream appeared",
        error_code="finder_audio_stream_unavailable",
        failure_stage="audio_stream_start",
        evidence={"source_card_found": True},
    )


def derive_identity_terms(title: str, author: str) -> list[str]:
    terms = re.findall(r"[《【]([^》】]{2,20})[》】]", title)
    terms.extend(part.strip() for part in re.split(r"[#|｜]", title) if 2 <= len(part.strip()) <= 20)
    for phrase in re.findall(r"[0-9A-Za-z㐀-鿿]{4,}", title):
        if len(phrase) <= 16:
            terms.append(phrase)
        else:
            terms.extend((phrase[:10], phrase[-10:]))
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
def exclusive_gui_lock(path: Path, *, timeout_seconds: float = 0.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise CaptureFailure(
                        "WECHAT_SEND_BUSY: GUI lane is active; retry capture later",
                        error_code="wechat_gui_busy",
                        failure_stage="gui_lock",
                    ) from exc
                time.sleep(0.25)
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
    text = str(value or "").casefold()
    if IDENTITY_T2S is not None:
        text = IDENTITY_T2S.convert(text)
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


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
