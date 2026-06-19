#!/usr/bin/env python3
"""Run ylytdeng/wechat-decrypt monitor_web on a localhost-only socket."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_EXTERNAL = PRIVATE / "external" / "wechat-decrypt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5678)
    args = parser.parse_args()

    external = args.external.resolve()
    if not (external / "monitor_web.py").exists():
        raise SystemExit(f"Missing monitor_web.py under {external}")
    sys.path.insert(0, str(external))
    os.chdir(external)

    monitor_web = importlib.import_module("monitor_web")
    if hasattr(monitor_web, "PORT"):
        monitor_web.PORT = args.port
    if hasattr(monitor_web, "_start_monitor_if_ready"):
        monitor_web._start_monitor_if_ready()
    server_cls = getattr(monitor_web, "ThreadedServer")
    handler_cls = getattr(monitor_web, "Handler")
    server = server_cls((args.host, args.port), handler_cls)
    print(f"WeChat decrypt monitor: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
