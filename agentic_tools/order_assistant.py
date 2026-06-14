#!/usr/bin/env python3
"""Unified guarded order assistant for JLCPCB and Wenext.

The script delegates provider-specific work to the maintained order agents, then
normalizes status and writes a private assistance packet when a website blocks
automation. It is intentionally conservative: "place" can submit to review,
cashier, or payment pages only when --allow-submit is passed, and it never
clicks payment/recharge controls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "agentic_tools"
DEFAULT_PACKET_DIR = Path("~/.config/manufacturing-order-assistant/packets").expanduser()


def redact(text: str) -> str:
    text = re.sub(r"1\d{10}", lambda m: f"{m.group(0)[:3]}****{m.group(0)[-4:]}", text)
    text = re.sub(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+)", r"\1@***", text)
    text = re.sub(r"(?i)(password|token|secret|key|验证码|code)[=:]\s*\S+", r"\1=***", text)
    return text


def rel_cmd(parts: list[str]) -> list[str]:
    return [str((ROOT / part).resolve()) if part.startswith("agentic_tools/") else part for part in parts]


def run_command(parts: list[str], *, env: dict[str, str] | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        parts,
        cwd=ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def parse_last_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    for start in [idx for idx, char in enumerate(text) if char in "[{"][-20:]:
        try:
            value = json.loads(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return {"targets": value}
        if isinstance(value, dict):
            return value
    return None


def diagnose(provider: str, site: str, text: str, parsed: dict[str, Any] | None) -> dict[str, Any]:
    body = text
    state = (parsed or {}).get("state", {}) if isinstance(parsed, dict) else {}
    url = state.get("url") or (parsed or {}).get("url") if isinstance(parsed, dict) else ""
    payment_page = bool(state.get("payment_page")) or any(marker in body for marker in ["收银台支付", "Payment Link", "PayPal"])
    blockers: list[str] = []
    next_steps: list[str] = []

    if provider == "wenext":
        if any(marker in body for marker in ["您好，请登录", "密码登录", "验证码登录", "账号绑定", "微信未绑定"]):
            blockers.append("wenext-login-or-binding")
            next_steps.append("Finish Wenext login or WeChat/phone binding in the same Chrome profile, then rerun.")
        if "解析文件报价中" in body:
            blockers.append("wenext-parser-busy")
            next_steps.append("Wait or retry upload one file at a time; record a snapshot before refreshing.")
        if "暂无产品" in body or "已选产品 0" in body:
            blockers.append("wenext-empty-product-table")
            next_steps.append("Wait for cart/checkout rows to populate before clicking checkout or submit.")
        if "发票信息中缺少邮箱地址" in body:
            blockers.append("wenext-invoice-email-missing")
            next_steps.append("Choose 数电普票, create/select a personal invoice title, fill 收票人邮箱, then submit again.")
        if payment_page:
            return {
                "status": "payment_waiting",
                "blockers": [],
                "next_steps": ["Pay manually from the Wenext payment/cashier page if the order is correct."],
                "url": url,
            }

    if provider == "jlc":
        if any(marker in body for marker in ["检测到您的订单还有", "去填写", "系统未检测到"]):
            blockers.append("jlc-missing-required-fields")
            next_steps.append("Open the JLC order-check drawer and fill every field marked missing.")
        if "品质赔付费" in body:
            blockers.append("jlc-paid-quality-compensation")
            next_steps.append("Switch quality compensation to 按标准合同常规处理 for bare PCB orders.")
        if any(marker in body for marker in ["OSP", "尺寸过小", "不能支持"]):
            blockers.append("jlc-osp-or-finish-warning")
            next_steps.append("Choose a supported finish, such as lead-free HASL, or use a larger board for OSP.")
        if any(marker in body for marker in ["余额不足", "充值"]):
            blockers.append("jlc-payment-or-wallet-boundary")
            next_steps.append("Stop at the review/payment boundary; do not automate recharge or wallet payment.")
        if any(marker in body for marker in ["下单成功", "pcbPlaceSuccess", "Review Before Payment"]):
            return {
                "status": "submitted_or_review_waiting",
                "blockers": [],
                "next_steps": ["Wait for JLC review or pay manually after checking the order."],
                "url": url,
            }
        if "file_inputs=" in body and any(marker in body for marker in ["jlc.com", "cart.jlcpcb.com", "嘉立创"]):
            match = re.search(r"url=(\S+)", body)
            return {
                "status": "browser_ready",
                "blockers": [],
                "next_steps": ["Use place with a Gerber ZIP when ready to prepare or submit an order."],
                "url": match.group(1) if match else url,
            }

    if blockers:
        return {"status": "needs_agent_assistance", "blockers": blockers, "next_steps": next_steps, "url": url}
    if parsed:
        return {"status": "ok", "blockers": [], "next_steps": [], "url": url}
    return {"status": "unknown", "blockers": [], "next_steps": ["Inspect stdout/stderr and provider snapshot."], "url": url}


def write_packet(
    args: argparse.Namespace,
    command: list[str],
    result: subprocess.CompletedProcess[str],
    parsed: dict[str, Any] | None,
    diagnosis: dict[str, Any],
    snapshot_result: subprocess.CompletedProcess[str] | None = None,
) -> Path:
    args.packet_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = args.packet_dir / f"{args.provider}-{args.site}-{stamp}.json"
    packet = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "provider": args.provider,
        "site": args.site,
        "action": args.action,
        "allow_submit": bool(args.allow_submit),
        "command": [shlex.quote(part) for part in command],
        "returncode": result.returncode,
        "diagnosis": diagnosis,
        "parsed_stdout": parsed,
        "stdout_tail": redact(result.stdout[-6000:]),
        "stderr_tail": redact(result.stderr[-6000:]),
        "snapshot_stdout_tail": redact((snapshot_result.stdout if snapshot_result else "")[-6000:]),
        "snapshot_stderr_tail": redact((snapshot_result.stderr if snapshot_result else "")[-6000:]),
        "agent_prompt": (
            "Resume this manufacturing order. Read the provider docs under agentic_tools, "
            "inspect the current browser/CDP state, resolve the listed blockers, and stop at "
            "review/payment/cashier boundary without clicking payment."
        ),
    }
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def provider_command(args: argparse.Namespace) -> tuple[list[str], dict[str, str]]:
    env: dict[str, str] = {}
    files = list(args.files or [])
    if args.provider == "wenext":
        script = TOOLS_ROOT / "wenext_3d_order_agent" / "scripts" / ("quick_order_china.sh" if args.site == "china" else "quick_order_global.sh")
        if args.action == "status":
            return [str(script), "snapshot", "--status", "order_assistant_status", "--note", "Unified order assistant status check."], env
        flow = "china-flow" if args.site == "china" else "global-flow"
        command = [str(script), flow]
        if args.upload:
            command.append("--upload")
        if args.allow_submit:
            command.append("--allow-submit")
        if args.site == "china" and args.invoice:
            command.extend(["--invoice", args.invoice])
        if files:
            command.append("--files")
            command.extend(files)
        return command, env

    script = TOOLS_ROOT / "jlcpcb_order_agent" / "scripts" / ("quick_order_china.sh" if args.site == "china" else "quick_order_global.sh")
    if args.action == "status":
        launcher = TOOLS_ROOT / "jlcpcb_order_agent" / "scripts" / "launch_shared_chrome.sh"
        agent = TOOLS_ROOT / "jlcpcb_order_agent" / "scripts" / "jlc_order_cdp.py"
        return ["bash", "-lc", f"{shlex.quote(str(launcher))} && {shlex.quote(sys.executable)} {shlex.quote(str(agent))} status"], env
    if args.allow_submit:
        env["JLCPCB_ALLOW_SUBMIT"] = "1"
    if args.surface_finish:
        env["JLCPCB_SURFACE_FINISH"] = args.surface_finish
    if args.order_channel:
        env["JLCPCB_ORDER_CHANNEL"] = args.order_channel
    if args.shipping_mode:
        env["JLCPCB_SHIPPING_MODE"] = args.shipping_mode
    command = [str(script)]
    if files:
        if len(files) > 1:
            raise SystemExit("JLC accepts one Gerber ZIP path for this wrapper")
        command.append(files[0])
    return command, env


def snapshot_command(args: argparse.Namespace) -> tuple[list[str], dict[str, str]] | None:
    if args.provider == "wenext":
        script = TOOLS_ROOT / "wenext_3d_order_agent" / "scripts" / ("quick_order_china.sh" if args.site == "china" else "quick_order_global.sh")
        return [str(script), "snapshot", "--status", "order_assistant_blocker", "--note", "Snapshot after order assistant blocker."], {}
    if args.provider == "jlc":
        launcher = TOOLS_ROOT / "jlcpcb_order_agent" / "scripts" / "launch_shared_chrome.sh"
        agent = TOOLS_ROOT / "jlcpcb_order_agent" / "scripts" / "jlc_order_cdp.py"
        return ["bash", "-lc", f"{shlex.quote(str(launcher))} && {shlex.quote(sys.executable)} {shlex.quote(str(agent))} status"], {}
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["wenext", "jlc"], required=True)
    parser.add_argument("--site", choices=["china", "global"], default="china")
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--allow-submit", action="store_true", help="Submit only to review/payment boundary; never pays.")
    parser.add_argument("--upload", action="store_true", help="Upload configured/provided files before placing the order.")
    parser.add_argument("--invoice", choices=["auto", "skip"], default="auto")
    parser.add_argument("--surface-finish", help="JLC surface finish, e.g. OSP or 无铅喷锡.")
    parser.add_argument("--order-channel", choices=["web", "assistant"])
    parser.add_argument("--shipping-mode", choices=["separate", "combined"])
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("action", choices=["status", "place"])
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    command, env = provider_command(args)
    if args.dry_run:
        print(json.dumps({"command": command, "env": env}, ensure_ascii=False, indent=2))
        return

    result = run_command(command, env=env, timeout=args.timeout)
    combined = "\n".join([result.stdout, result.stderr])
    parsed = parse_last_json(result.stdout)
    diagnosis = diagnose(args.provider, args.site, combined, parsed)
    needs_packet = result.returncode != 0 or diagnosis["status"] == "needs_agent_assistance"
    snapshot_result = None
    if needs_packet:
        snap = snapshot_command(args)
        if snap:
            snap_cmd, snap_env = snap
            snapshot_result = run_command(snap_cmd, env=snap_env, timeout=120)
        packet = write_packet(args, command, result, parsed, diagnosis, snapshot_result)
        print(json.dumps({"ok": False, "diagnosis": diagnosis, "assistance_packet": str(packet)}, ensure_ascii=False, indent=2))
        raise SystemExit(result.returncode or 2)

    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    print(json.dumps({"ok": True, "diagnosis": diagnosis}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
