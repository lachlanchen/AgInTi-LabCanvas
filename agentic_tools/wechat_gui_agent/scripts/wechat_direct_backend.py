#!/usr/bin/env python3
"""Private wrapper for direct WeChat local-store monitoring/decryption backends."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
EXTERNAL = PRIVATE / "external" / "wechat-decrypt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", default="wechat-chat")
    parser.add_argument("--external", type=Path, default=EXTERNAL)
    parser.add_argument("--db-dir", type=Path, default=None, help="Path to xwechat_files/<WXID>/db_storage. Auto-discovers when omitted.")
    parser.add_argument("--mirror-db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-config")
    sub.add_parser("status")
    sub.add_parser("find-keys")
    sub.add_parser("monitor")
    sub.add_parser("mcp-server")
    args = parser.parse_args()
    db_dir = args.db_dir or discover_xwechat_db()

    if args.command == "init-config":
        config_path = write_external_config(args.external, db_dir)
        print(config_path)
        record_event(
            chat_name=args.chat,
            action="direct_backend",
            status="config-written",
            db_path=args.mirror_db,
            metadata={"config_path": str(config_path), "db_dir": str(db_dir)},
        )
        return 0
    if args.command == "status":
        print(json.dumps(status(args.external, db_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "find-keys":
        config_path = write_external_config(args.external, db_dir)
        return run_external(args.external, [str(venv_python()), "find_all_keys_linux.py"], config_path)
    if args.command == "monitor":
        config_path = write_external_config(args.external, db_dir)
        return run_external(args.external, [str(venv_python()), "monitor.py"], config_path)
    if args.command == "mcp-server":
        config_path = write_external_config(args.external, db_dir)
        return run_external(args.external, [str(venv_python()), "mcp_server.py"], config_path)
    return 0


def discover_xwechat_db() -> Path:
    root = Path.home() / "Documents" / "xwechat_files"
    candidates = [path for path in root.glob("*/db_storage") if path.is_dir()]
    if not candidates:
        raise SystemExit(f"No local WeChat db_storage found under {root}; pass --db-dir explicitly.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def write_external_config(external: Path, db_dir: Path) -> Path:
    if not external.exists():
        raise SystemExit(f"Missing private external decryptor: {external}")
    config = {
        "db_dir": str(db_dir),
        "keys_file": str((PRIVATE / "wechat_decrypt" / "all_keys.json").resolve()),
        "decrypted_dir": str((PRIVATE / "wechat_decrypt" / "decrypted").resolve()),
        "decoded_image_dir": str((PRIVATE / "wechat_decrypt" / "decoded_images").resolve()),
        "wechat_process": "wechat",
        "wxwork_db_dir": "",
        "wxwork_keys_file": str((PRIVATE / "wechat_decrypt" / "wxwork_keys.json").resolve()),
        "wxwork_decrypted_dir": str((PRIVATE / "wechat_decrypt" / "wxwork_decrypted").resolve()),
        "wxwork_export_dir": str((PRIVATE / "wechat_decrypt" / "wxwork_export").resolve()),
        "wxwork_process": "WXWork.exe",
        "transcription_backend": "local",
        "local_whisper_model": "base",
        "openai_api_key": "",
    }
    (PRIVATE / "wechat_decrypt").mkdir(parents=True, exist_ok=True)
    config_path = external / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config_path.chmod(0o600)
    return config_path


def status(external: Path, db_dir: Path) -> dict:
    keys_file = PRIVATE / "wechat_decrypt" / "all_keys.json"
    return {
        "external_exists": external.exists(),
        "db_dir": str(db_dir),
        "db_dir_exists": db_dir.exists(),
        "message_db": str(db_dir / "message" / "message_0.db"),
        "keys_file": str(keys_file),
        "keys_file_exists": keys_file.exists(),
        "decrypted_dir": str(PRIVATE / "wechat_decrypt" / "decrypted"),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def run_external(external: Path, command: list[str], config_path: Path) -> int:
    env = os.environ.copy()
    env["WECHAT_DECRYPT_APP_DIR"] = str(external)
    proc = subprocess.run(command, cwd=external, env=env, check=False)
    if proc.returncode != 0:
        print(f"{command} failed with code {proc.returncode}; config={config_path}", file=sys.stderr)
    return proc.returncode


def venv_python() -> Path:
    candidate = PRIVATE / "wechat_decrypt" / ".venv" / "bin" / "python"
    if candidate.exists():
        return candidate
    return Path(sys.executable)


if __name__ == "__main__":
    raise SystemExit(main())
