#!/usr/bin/env python3
"""Keep startup/recovery gated when durable chat storage is unavailable.

Install this file and its state on a different filesystem from the repository.
It does not repair disks, send messages, or create replacement queues.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


DEFAULT_CONFIG = Path.home() / ".config/labcanvas/storage-guard.json"


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".guard-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def mount_for(path: str, content: str) -> dict:
    candidates = []
    path = os.path.abspath(path)
    for line in content.splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])
        if path == mount or path.startswith(mount.rstrip("/") + "/"):
            candidates.append({"path": mount, "device": fields[2],
                               "options": fields[5].split(","), "fstype": right.split()[0]})
    if not candidates:
        raise OSError("No mount entry for required path")
    return max(candidates, key=lambda item: len(item["path"]))


def controller_states(device: str, sys_block: Path = Path("/sys/dev/block")) -> dict:
    pending = [sys_block / device]
    seen = set()
    states = {}
    while pending:
        entry = pending.pop().resolve(strict=True)
        if entry in seen:
            continue
        seen.add(entry)
        for parent in (entry, *entry.parents):
            if re.fullmatch(r"nvme\d+", parent.name):
                states[parent.name] = (parent / "state").read_text().strip()
                break
        slaves = entry / "slaves"
        if slaves.is_dir():
            pending.extend(slaves.iterdir())
    return states


def probe(config: dict) -> dict:
    """Kernel state is checked before touching an unavailable project volume."""
    mounts = Path("/proc/self/mountinfo").read_text()
    mount = mount_for(config["root"], mounts)
    if mount["path"] != config["mountpoint"]:
        return {"ok": False, "reason": "required_mount_missing", "latch": False}
    state_mount = mount_for(config["state_dir"], mounts)
    if state_mount["device"] == mount["device"]:
        return {"ok": False, "reason": "guard_state_on_project_volume", "latch": True}
    states = controller_states(mount["device"])
    if any(value != "live" for value in states.values()):
        return {"ok": False, "reason": "backing_controller_unavailable", "latch": True,
                "controllers": states}
    if "ro" in mount["options"]:
        return {"ok": False, "reason": "project_filesystem_read_only", "latch": True}
    device_name = (Path("/sys/dev/block") / mount["device"]).resolve().name
    last_error = Path("/sys/fs/ext4") / device_name / "last_error_time"
    if last_error.exists():
        boot_time = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                         if line.startswith("btime "))
        if int(last_error.read_text()) >= boot_time:
            return {"ok": False, "reason": "filesystem_error_this_boot", "latch": True}
    root = Path(config["root"])
    for relative in config["required_files"]:
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts:
            raise ValueError("required_files must be relative to the project")
        with (root / item).open("rb") as stream:
            if not stream.read(1):
                return {"ok": False, "reason": "required_file_empty", "latch": True}
    # Prove durable writes in the existing artifact directory, never create it.
    fd, filename = tempfile.mkstemp(prefix=".storage-probe-", dir=root / "output")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"labcanvas-storage-probe\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.unlink(filename)
    directory = os.open(root / "output", os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {"ok": True, "reason": "storage_ready", "controllers": states}


def pid_identity(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""


def bounded_probe(config_path: Path, state: dict, timeout: float) -> dict:
    old_pid = int(state.get("probe_pid") or 0)
    old_identity = state.get("probe_identity")
    if old_pid and old_identity and pid_identity(old_pid) == old_identity:
        return {"ok": False, "reason": "previous_probe_still_running", "latch": True,
                "probe_pid": old_pid, "probe_identity": old_identity}
    child = subprocess.Popen(
        [sys.executable, "-I", str(Path(__file__).resolve()), "--config", str(config_path), "_probe"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    identity = pid_identity(child.pid)
    try:
        stdout, _ = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        try:
            child.communicate(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
        return {"ok": False, "reason": "storage_probe_timeout", "latch": True,
                "probe_pid": child.pid, "probe_identity": identity}
    try:
        result = json.loads(stdout)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ValueError("Invalid probe result")
        return result
    except (ValueError, TypeError):
        return {"ok": False, "reason": "storage_probe_failed", "latch": True}


def evaluate(previous: dict, result: dict, acknowledge: bool = False) -> dict:
    latched = bool(previous.get("recovery_review_required")) or bool(result.get("latch"))
    if acknowledge and result["ok"]:
        latched = False
    return {**result, "ok": bool(result["ok"] and not latched),
            "recovery_review_required": latched,
            "reason": "recovery_review_required" if result["ok"] and latched else result["reason"]}


def check(config: dict, config_path: Path, acknowledge: bool = False) -> dict:
    directory = Path(config["state_dir"])
    mounts = Path("/proc/self/mountinfo").read_text()
    project_mount = mount_for(config["root"], mounts)
    if (project_mount["path"] == config["mountpoint"]
            and mount_for(str(directory), mounts)["device"] == project_mount["device"]):
        raise ValueError("Guard state must not be written on the project filesystem")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "guard.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "status.json"
        previous = json.loads(path.read_text()) if path.exists() else {}
        result = bounded_probe(config_path, previous, float(config.get("probe_timeout", 8)))
        current = evaluate(previous, result, acknowledge)
        current["checked_at"] = time.time()
        transition = (previous.get("ok"), previous.get("reason")) != (current["ok"], current["reason"])
        atomic_json(path, current)
        if transition:
            print(f"LabCanvas storage: {current['reason']}", file=sys.stderr, flush=True)
        return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", help="Skip this installation's gate for unrelated workspaces")
    parser.add_argument("--ledgers-verified", action="store_true")
    parser.add_argument("action", choices=("check", "wait", "acknowledge", "_probe"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        config = json.loads(args.config.read_text())
        if args.root and os.path.abspath(args.root) != os.path.abspath(config["root"]):
            return 0
        if args.action == "_probe":
            try:
                result = probe(config)
            except (OSError, ValueError, StopIteration) as exc:
                result = {"ok": False, "reason": "storage_io_failure", "latch": True,
                          "error_type": type(exc).__name__, "errno": getattr(exc, "errno", None)}
            print(json.dumps(result))
            return 0
        if args.action == "acknowledge" and not args.ledgers_verified:
            parser.error("acknowledge requires --ledgers-verified after offline repair and ledger checks")
        while True:
            result = check(config, args.config, args.action == "acknowledge")
            if args.action != "wait":
                print(json.dumps(result, sort_keys=True))
                return 0 if result["ok"] else 75
            if result["ok"]:
                command = args.command[1:] if args.command[:1] == ["--"] else args.command
                if command:
                    os.execvp(command[0], command)
                return 0
            time.sleep(max(10, float(config.get("interval", 60))))
    except (OSError, ValueError, KeyError, TypeError):
        print("LabCanvas storage guard failed closed; inspect its host-side configuration/state.", file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
