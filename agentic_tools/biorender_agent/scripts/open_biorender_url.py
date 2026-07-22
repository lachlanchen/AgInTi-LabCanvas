#!/usr/bin/env python3
"""Open one URL in the dedicated BioRender Chrome session over local CDP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib import parse, request


def get_json(url: str, *, method: str = "GET") -> object:
    with request.urlopen(request.Request(url, method=method), timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def is_oauth_callback_url(value: str) -> bool:
    parsed = parse.urlsplit(str(value or ""))
    return (
        parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.port == 1455
        and parsed.path == "/callback"
    )


def close_page(base: str, page_id: str) -> None:
    with request.urlopen(f"{base}/json/close/{parse.quote(page_id, safe='')}", timeout=10):
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--cdp-port", type=int, default=9389)
    parser.add_argument("--launcher", default="")
    parser.add_argument("--close-callbacks", action="store_true")
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.cdp_port}"
    try:
        pages = get_json(f"{base}/json/list")
    except Exception:
        launcher = args.launcher or str(Path(__file__).with_name("start_biorender_browser.sh"))
        subprocess.run([launcher], check=True, timeout=30)
        deadline = time.monotonic() + 20
        while True:
            try:
                pages = get_json(f"{base}/json/list")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise SystemExit("BioRender Chrome CDP did not start")
                time.sleep(0.5)
    if args.close_callbacks and isinstance(pages, list):
        for page_item in pages:
            if not isinstance(page_item, dict) or not is_oauth_callback_url(str(page_item.get("url") or "")):
                continue
            page_id = str(page_item.get("id") or "")
            if page_id:
                close_page(base, page_id)
    encoded = parse.quote(args.url, safe="")
    page = get_json(f"{base}/json/new?{encoded}", method="PUT")
    print(json.dumps({"ok": True, "id": page.get("id"), "url": page.get("url")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
