#!/usr/bin/env python3
"""Recover one exact WeCom article card through its native WeChat reader."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
WECOM_SCRIPTS = ROOT / "agentic_tools" / "wecom_agent" / "scripts"
WECHAT_SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
for directory in (WECOM_SCRIPTS, WECHAT_SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from wechat_source_recovery import normalize_wechat_article_url, recover_mp_weixin_article  # noqa: E402
from wecom_android_bridge import (  # noqa: E402
    ARTICLE_CARD_RESOURCE_SUFFIX,
    AndroidBridge,
    BridgeError,
    DEFAULT_CONFIG,
    chat_title_matches,
    find_nodes,
    load_config,
    node_text,
    normalize_visible_text,
    parse_bounds,
    visible_chat_title,
)


WECHAT_PACKAGE = "com.tencent.mm"


def find_article_title_node(root: ET.Element, title: str) -> ET.Element | None:
    expected = normalize_visible_text(title)
    for node in root.iter("node"):
        if not node.attrib.get("resource-id", "").endswith(ARTICLE_CARD_RESOURCE_SUFFIX):
            continue
        if normalize_visible_text(node_text(node)) != expected:
            continue
        try:
            _, top, _, bottom = parse_bounds(node.attrib.get("bounds", ""))
        except BridgeError:
            continue
        if bottom >= 180 and top <= 1800:
            return node
    return None


def scan_for_article(
    bridge: AndroidBridge,
    chat: str,
    title: str,
    *,
    max_pages: int,
) -> tuple[ET.Element, ET.Element, int]:
    root = bridge.open_chat(chat)
    for page in range(max(0, min(16, max_pages)) + 1):
        node = find_article_title_node(root, title)
        if node is not None:
            return root, node, page
        bridge.adb_shell("input", "swipe", "520", "650", "520", "1200", "400")
        time.sleep(0.55)
        root = bridge.dump_hierarchy(attempts=3)
        if not chat_title_matches(visible_chat_title(root), chat):
            break
    raise BridgeError("exact WeCom article card was not found in the bounded same-chat scan")


def wait_for_native_article(bridge: AndroidBridge, title: str, timeout: float = 45.0) -> ET.Element:
    expected = normalize_visible_text(title)
    deadline = time.monotonic() + max(4.0, timeout)
    while time.monotonic() < deadline:
        if bridge.current_package() not in {bridge.package, WECHAT_PACKAGE}:
            time.sleep(0.4)
            continue
        root = bridge.dump_hierarchy(attempts=2)
        if any(normalize_visible_text(node_text(node)) == expected for node in root.iter("node")):
            return root
        # WeCom's embedded native reader sometimes exposes the article body to
        # accessibility and sometimes only its fixed "在看" control. The copied
        # URL is still accepted only after HTTP title identity verification.
        if not visible_chat_title(root) and any(
            normalize_visible_text(node_text(node)) == "在看"
            for node in root.iter("node")
        ):
            return root
        time.sleep(0.5)
    raise BridgeError("native WeChat article did not expose the exact card title")


def screen_size(bridge: AndroidBridge) -> tuple[int, int]:
    output = bridge.adb_shell("wm", "size", check=False)
    matches = re.findall(r"(\d+)x(\d+)", output)
    if not matches:
        return 1080, 2160
    width, height = matches[-1]
    return int(width), int(height)


def host_clipboard(bridge: AndroidBridge) -> str:
    process = bridge.run(
        ["xclip", "-selection", "clipboard", "-o"],
        timeout=5,
        check=False,
        env={**os.environ, "DISPLAY": bridge.display},
    )
    return str(process.stdout or "").strip()


def copy_article_url(bridge: AndroidBridge) -> str:
    article_root = bridge.dump_hierarchy(attempts=3)
    menu_buttons = find_nodes(
        article_root,
        resource_id=f"{bridge.package}:id/n5v",
        package=bridge.package,
    )
    if menu_buttons:
        bridge.tap_node(article_root, menu_buttons[0])
    else:
        width, height = screen_size(bridge)
        bridge.adb_shell(
            "input",
            "tap",
            str(max(1, width - 120)),
            str(max(80, round(height * 0.063))),
        )
    deadline = time.monotonic() + 8.0
    copy_node: ET.Element | None = None
    while time.monotonic() < deadline:
        menu = bridge.dump_hierarchy(attempts=2)
        matches = find_nodes(menu, text="复制链接")
        if matches:
            copy_node = matches[0]
            bridge.tap_node(menu, copy_node)
            break
        time.sleep(0.3)
    if copy_node is None:
        raise BridgeError("native WeChat article menu did not expose Copy Link")

    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        value = host_clipboard(bridge)
        if value.startswith("https://mp.weixin.qq.com/"):
            return normalize_wechat_article_url(value)
        time.sleep(0.25)
    raise BridgeError("the native article link did not reach the synchronized clipboard")


def restore_wecom_chat_list(bridge: AndroidBridge) -> None:
    for _ in range(3):
        if bridge.current_package() == bridge.package:
            break
        bridge.press_back()
    bridge.launch_wecom()
    bridge.open_chat_list()


def recover_native_article(
    bridge: AndroidBridge,
    *,
    chat: str,
    title: str,
    output_dir: Path,
    max_pages: int = 3,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with bridge.serialized(timeout_seconds=90.0):
            root, title_node, scanned_pages = scan_for_article(
                bridge,
                chat,
                title,
                max_pages=max_pages,
            )
            bridge.tap_node(root, title_node)
            wait_for_native_article(bridge, title)
            url = copy_article_url(bridge)
            article = recover_mp_weixin_article(
                url,
                output_dir / "article",
                card_profile={"title": title},
            )
            recovered_title = normalize_visible_text(article.get("title"))
            if recovered_title != normalize_visible_text(title):
                raise BridgeError("copied article identity did not match the exact card title")
            result = {
                "ok": True,
                "status": str(article.get("status") or "unknown"),
                "source_quality": str(article.get("source_quality") or "unknown"),
                "title": str(article.get("title") or title),
                "author": str(article.get("author") or ""),
                "article_chars": int(article.get("article_chars") or 0),
                "markdown_path": str(article.get("markdown_path") or ""),
                "url": url,
                "scanned_pages": scanned_pages,
                "identity_verified": True,
            }
    finally:
        try:
            restore_wecom_chat_list(bridge)
        except Exception:
            pass
    manifest = output_dir / "native-article.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest, 0o600)
    result["manifest_path"] = str(manifest)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--chat", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        bridge = AndroidBridge(load_config(args.config), config_path=args.config)
        payload = recover_native_article(
            bridge,
            chat=args.chat,
            title=args.title,
            output_dir=args.output_dir,
            max_pages=args.max_pages,
        )
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:800]}"}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
