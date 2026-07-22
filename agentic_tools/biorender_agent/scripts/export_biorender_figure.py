#!/usr/bin/env python3
"""Export one editable BioRender figure as a validated 300-DPI PNG over CDP."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
from urllib.parse import urlsplit


def allowed_editor_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "app.biorender.com"
        and parsed.path.startswith("/illustrations/")
    )


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return 0, 0
    return struct.unpack(">II", data[16:24])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_figure(
    editor_url: str,
    output: Path,
    *,
    cdp_url: str,
    timeout_seconds: float,
    screenshot_dir: Path | None = None,
) -> dict[str, object]:
    if not allowed_editor_url(editor_url):
        raise ValueError("editor URL must be an app.biorender.com illustration")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Python Playwright is required for BioRender print export") from exc

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if screenshot_dir:
        screenshot_dir = screenshot_dir.expanduser().resolve()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
    timeout_ms = max(30_000, int(timeout_seconds * 1000))
    started = time.monotonic()
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(cdp_url)
    try:
        pages = [page for context in browser.contexts for page in context.pages]
        page = next((candidate for candidate in pages if candidate.url.split("?", 1)[0] == editor_url.split("?", 1)[0]), None)
        if page is None:
            context = browser.contexts[0]
            page = context.new_page()
            page.goto(editor_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.bring_to_front()
        page.wait_for_timeout(8000)
        if screenshot_dir:
            page.screenshot(path=str(screenshot_dir / "editor-before-export.png"))

        modal_title = page.get_by_text("Export your illustration", exact=True)
        if not modal_title.is_visible():
            page.get_by_text("Export", exact=True).first.click(timeout=timeout_ms)
            modal_title.wait_for(state="visible", timeout=timeout_ms)
        body_text = page.locator("body").inner_text()
        if "300 DPI" not in body_text or "High Resolution for Print" not in body_text:
            raise RuntimeError("BioRender export dialog is not set to the expected 300-DPI print mode")
        if screenshot_dir:
            page.screenshot(path=str(screenshot_dir / "export-dialog-300dpi.png"))

        with page.expect_download(timeout=timeout_ms) as download_info:
            page.get_by_role("button", name="Export", exact=True).last.click(timeout=timeout_ms)
        download = download_info.value
        download.save_as(str(output))
    finally:
        browser.close()
        playwright.stop()

    width, height = png_dimensions(output)
    if width < 2400 or height < 1400:
        raise RuntimeError(f"BioRender print export is too small: {width}x{height}")
    return {
        "ok": True,
        "output": str(output),
        "width": width,
        "height": height,
        "size_bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "editor_url": editor_url,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9389")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--screenshot-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = export_figure(
            args.editor_url,
            args.output,
            cdp_url=args.cdp_url,
            timeout_seconds=args.timeout,
            screenshot_dir=args.screenshot_dir,
        )
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:700]}"}
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
