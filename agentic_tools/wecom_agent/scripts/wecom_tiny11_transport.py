#!/usr/bin/env python3
"""Manage the localhost-only Tiny11 WeCom helper and verified SFTP staging."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_CONFIG = PRIVATE / "wecom_gui_bridge.local.json"
GUEST_HELPER = TOOL_ROOT / "windows" / "WeComBridge.ps1"
DEFAULT_VM_COMMAND = Path(
    "/home/lachlan/UbuntuSDA/VirtualMachines/Windows-Tiny11/tools/windows-tiny11-kvm"
)


class Tiny11TransportError(RuntimeError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Tiny11TransportError(f"Tiny11 transport config is unavailable: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise Tiny11TransportError("Tiny11 transport config must be a JSON object")
    return payload


class Tiny11Transport:
    def __init__(self, config: dict[str, Any]) -> None:
        nested = config.get("tiny11")
        self.config = nested if isinstance(nested, dict) else {}
        self.host = str(self.config.get("ssh_host") or "127.0.0.1")
        self.ssh_port = bounded_int(self.config.get("ssh_port"), 2290, 1, 65535)
        self.user = str(self.config.get("ssh_user") or "lachlan")
        self.helper_port = bounded_int(self.config.get("helper_port"), 19582, 1024, 65535)
        self.local_port = bounded_int(self.config.get("local_port"), self.helper_port, 1024, 65535)
        self.token = str(
            self.config.get("helper_token") or config.get("local_api_token") or ""
        ).strip()
        self.vm_command = Path(str(self.config.get("vm_command") or DEFAULT_VM_COMMAND)).expanduser()
        self.start_vm = bool(self.config.get("start_vm", True))
        self.remote_root = str(self.config.get("remote_root") or r"C:\LabCanvas\WeComBridge")
        self.task_name = str(self.config.get("task_name") or "LabCanvas-WeCom-Bridge")
        self.timeout = float(self.config.get("timeout_seconds") or 12.0)
        if not self.token:
            raise Tiny11TransportError("Tiny11 helper token is missing")
        if self.host not in {"127.0.0.1", "localhost"}:
            raise Tiny11TransportError("Tiny11 SSH must remain localhost-only")

    @property
    def helper_url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"

    def ssh_base(self) -> list[str]:
        return [
            "ssh",
            "-p",
            str(self.ssh_port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            f"{self.user}@{self.host}",
        ]

    def ensure_vm(self) -> None:
        if self.ssh_ready():
            return
        if not self.start_vm:
            raise Tiny11TransportError("Tiny11 SSH is unavailable and start_vm is disabled")
        if not self.vm_command.is_file():
            raise Tiny11TransportError(f"Tiny11 launcher is missing: {self.vm_command}")
        subprocess.run([str(self.vm_command), "start"], cwd=ROOT, check=False, timeout=30)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.ssh_ready():
                return
            time.sleep(2)
        raise Tiny11TransportError("Tiny11 SSH did not become ready")

    def ssh_ready(self) -> bool:
        proc = subprocess.run(
            [*self.ssh_base(), "cmd.exe", "/d", "/s", "/c", "exit 0"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0

    def powershell(self, script: str, *, timeout: float = 45.0) -> str:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        proc = subprocess.run(
            [
                *self.ssh_base(),
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise Tiny11TransportError(f"Tiny11 PowerShell failed: {clean_powershell_error(proc.stderr)}")
        return proc.stdout.strip()

    def scp_to_guest(self, source: Path, remote_path: str) -> None:
        proc = subprocess.run(
            [
                "scp",
                "-C",
                "-P",
                str(self.ssh_port),
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                str(source),
                f"{self.user}@{self.host}:{remote_path.replace(chr(92), '/')}",
            ],
            capture_output=True,
            text=True,
            timeout=max(60.0, self.timeout),
            check=False,
        )
        if proc.returncode != 0:
            raise Tiny11TransportError(f"SFTP staging failed: {proc.stderr.strip()[:500]}")

    def install(self) -> dict[str, Any]:
        self.ensure_vm()
        helper_hash = sha256_file(GUEST_HELPER)
        token_file = PRIVATE / "tiny11-helper-token.txt"
        token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        token_file.write_text(self.token + "\n", encoding="utf-8")
        token_file.chmod(0o600)
        remote_helper = self.remote_root + r"\WeComBridge.ps1"
        remote_token = self.remote_root + r"\token.txt"
        self.powershell(
            "$ErrorActionPreference='Stop'; "
            f"New-Item -ItemType Directory -Force -Path {ps_quote(self.remote_root)} | Out-Null"
        )
        self.scp_to_guest(GUEST_HELPER, remote_helper)
        self.scp_to_guest(token_file, remote_token)
        script = f"""$ErrorActionPreference='Stop'
$taskName={ps_quote(self.task_name)}
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent()
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {ps_quote(f'-NoLogo -NoProfile -NonInteractive -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "{remote_helper}" -Port {self.helper_port} -TokenPath "{remote_token}"')}
$principal=New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {{
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}}
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output 'installed'
"""
        self.powershell(script)
        return {
            "ok": True,
            "task_name": self.task_name,
            "helper_sha256": helper_hash,
            "remote_root": self.remote_root,
        }

    def tunnel_command(self) -> list[str]:
        return [
            *self.ssh_base(),
            "-N",
            "-L",
            f"127.0.0.1:{self.local_port}:127.0.0.1:{self.helper_port}",
            "-o",
            "ExitOnForwardFailure=yes",
        ]

    def invoke(self, action: dict[str, Any]) -> Any:
        body = json.dumps(action, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.helper_url + "/action",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        payload = self._json_request(req)
        if not payload.get("ok"):
            raise Tiny11TransportError(str(payload.get("error") or "Tiny11 action failed"))
        return payload.get("result")

    def health(self) -> dict[str, Any]:
        req = request.Request(
            self.helper_url + "/health",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            return self._json_request(req)
        except Tiny11TransportError as exc:
            return {"ok": False, "error": str(exc)}

    def screenshot(self) -> bytes:
        req = request.Request(
            self.helper_url + "/screenshot",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = response.read(20 * 1024 * 1024)
        except (OSError, error.URLError, TimeoutError) as exc:
            raise Tiny11TransportError(f"Tiny11 screenshot failed: {type(exc).__name__}") from exc
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise Tiny11TransportError("Tiny11 screenshot was not a PNG")
        return data

    def stage_file(self, source: Path, delivery_key: str) -> str:
        source = source.resolve()
        safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", delivery_key)[:80]
        safe_name = re.sub(r"[<>:\"/\\|?*]", "_", source.name).strip(" .")
        if not safe_name:
            safe_name = "artifact" + source.suffix
        remote_directory = self.remote_root + rf"\inbox\{safe_key}"
        remote_path = remote_directory + "\\" + safe_name
        self.powershell(
            "$ErrorActionPreference='Stop'; "
            f"New-Item -ItemType Directory -Force -Path {ps_quote(remote_directory)} | Out-Null"
        )
        self.scp_to_guest(source, remote_path)
        expected_hash = sha256_file(source)
        expected_size = source.stat().st_size
        verification = self.powershell(
            "$ErrorActionPreference='Stop'; "
            f"$p={ps_quote(remote_path)}; "
            "$i=Get-Item -LiteralPath $p; $h=(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant(); "
            "[ordered]@{size=$i.Length;sha256=$h}|ConvertTo-Json -Compress"
        )
        try:
            observed = json.loads(first_json_line(verification))
        except json.JSONDecodeError as exc:
            raise Tiny11TransportError("Tiny11 staged-file verification was invalid") from exc
        if int(observed.get("size") or -1) != expected_size or observed.get("sha256") != expected_hash:
            raise Tiny11TransportError("Tiny11 staged file did not match source identity")
        return remote_path

    def remove_staged_file(self, remote_path: str) -> None:
        inbox = (self.remote_root + "\\inbox\\").casefold()
        normalized = str(remote_path or "").replace("/", "\\")
        if not normalized.casefold().startswith(inbox):
            raise Tiny11TransportError("refusing to remove a path outside the Tiny11 inbox")
        remote_directory = normalized.rsplit("\\", 1)[0]
        self.powershell(
            "$ErrorActionPreference='Stop'; "
            f"Remove-Item -LiteralPath {ps_quote(remote_directory)} -Recurse -Force -ErrorAction SilentlyContinue"
        )

    def start_helper_if_needed(self) -> None:
        if self.health().get("ok"):
            return
        self.powershell(f"Start-ScheduledTask -TaskName {ps_quote(self.task_name)}")

    def supervise(self) -> int:
        self.ensure_vm()
        self.install()
        backoff = 2.0
        while True:
            tunnel = subprocess.Popen(self.tunnel_command())
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and tunnel.poll() is None:
                    if self.health().get("ok"):
                        backoff = 2.0
                        break
                    try:
                        self.start_helper_if_needed()
                    except Tiny11TransportError:
                        pass
                    time.sleep(1)
                while tunnel.poll() is None:
                    if not self.health().get("ok"):
                        try:
                            self.start_helper_if_needed()
                        except Tiny11TransportError:
                            pass
                    time.sleep(10)
            finally:
                if tunnel.poll() is None:
                    tunnel.terminate()
                    try:
                        tunnel.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        tunnel.kill()
                time.sleep(backoff)
                backoff = min(60.0, backoff * 2)

    def _json_request(self, req: request.Request) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise Tiny11TransportError(f"Tiny11 helper unavailable: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise Tiny11TransportError("Tiny11 helper returned an invalid response")
        return payload


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_json_line(value: str) -> str:
    for line in value.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if stripped.startswith("{"):
            return stripped
    return value.strip().lstrip("\ufeff")


def clean_powershell_error(value: str) -> str:
    cleaned = re.sub(r"#< CLIXML.*", "", value, flags=re.DOTALL).strip()
    return cleaned[:500] or "remote command failed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=["install", "status", "supervise", "tunnel", "screenshot"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    transport = Tiny11Transport(load_config(args.config))
    if args.command == "install":
        payload = transport.install()
    elif args.command == "status":
        payload = transport.health()
    elif args.command == "tunnel":
        os.execvp(transport.tunnel_command()[0], transport.tunnel_command())
    elif args.command == "supervise":
        return transport.supervise()
    else:
        if args.output is None:
            parser.error("screenshot requires --output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(transport.screenshot())
        payload = {"ok": True, "output": str(args.output)}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if args.json else payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
