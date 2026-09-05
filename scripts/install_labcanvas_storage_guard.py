#!/usr/bin/env python3
"""Install a host-side startup gate without reading/writing private chat data."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from labcanvas_storage_guard import atomic_json, mount_for


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--mountpoint", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    home = Path.home()
    root = args.root.absolute()
    target = home / ".local/lib/labcanvas/storage_guard.py"
    config_path = home / ".config/labcanvas/storage-guard.json"
    state = home / ".local/state/labcanvas/storage-guard"
    mounts = Path("/proc/self/mountinfo").read_text()
    if mount_for(str(state), mounts)["device"] == mount_for(str(root), mounts)["device"]:
        parser.error("The guard and project must be on separate filesystems")
    config = {
        "root": str(root), "mountpoint": args.mountpoint, "state_dir": str(state),
        "interval": 60, "probe_timeout": 8,
        "required_files": [
            "src/agenticapp/cli.py",
            "agentic_tools/wechat_gui_agent/scripts/wechat_supervisor_tmux.sh",
            "agentic_tools/wecom_agent/scripts/wecom_autostart.sh",
        ],
    }
    if config_path.exists():
        existing = json.loads(config_path.read_text())
        if existing["root"] != str(root) or existing["mountpoint"] != args.mountpoint:
            parser.error("An existing installation has another root or mountpoint")
        config = existing
    dropin = home / ".config/systemd/user/labcanvas-wecom-autostart.service.d/20-storage-guard.conf"
    # Systemd specifiers and quoting must not reinterpret a local filename.
    def quote(value):
        return '"' + str(value).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"') + '"'
    command = " ".join(quote(value) for value in (
        "/usr/bin/python3", target, "--config", config_path, "wait", "--",
        "/bin/bash", root / "agentic_tools/wecom_agent/scripts/wecom_autostart.sh", "supervise",
    ))
    content = "[Service]\nWorkingDirectory=%h\nExecStart=\nExecStart=" + command + "\n"
    plan = {"guard": str(target), "config": str(config_path), "dropin": str(dropin),
            "runtime_restarted": False, "applied": args.apply}
    if args.apply:
        os.umask(0o077)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        shutil.copyfile(Path(__file__).with_name("labcanvas_storage_guard.py"), temporary)
        temporary.chmod(0o700)
        temporary.replace(target)
        gate = target.with_name("storage_gate.sh")
        temporary_gate = gate.with_suffix(".tmp")
        shutil.copyfile(Path(__file__).with_name("labcanvas_storage_gate.sh"), temporary_gate)
        temporary_gate.chmod(0o700)
        temporary_gate.replace(gate)
        atomic_json(config_path, config)
        dropin.parent.mkdir(parents=True, exist_ok=True)
        temp_dropin = dropin.with_suffix(".tmp")
        temp_dropin.write_text(content)
        temp_dropin.replace(dropin)
        env = dict(os.environ, XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}",
                   DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{os.getuid()}/bus")
        subprocess.run(["systemctl", "--user", "daemon-reload"], env=env, check=True)
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
