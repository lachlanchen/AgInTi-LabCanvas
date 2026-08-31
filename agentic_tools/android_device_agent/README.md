# Android Device Agent

Reusable Android control layer for the connected Xiaomi Mi MIX 2S and matching
test emulators.

## Current Device

- Serial: use `adb devices -l` locally, then pass `--serial <MIX2S_SERIAL>`
- Model: `MIX 2S`
- Codename: `polaris`
- Screen: `1080x2160`
- Density: `440`

The real device is the default target because it keeps the user's actual app
state, logins, files, and notifications. The AVD profile is only for app testing
or dry automation that does not need the real phone state.

When the health guard reports `wechat_login_required`, the bounded repair is to
restart the exact `labcanvas-android-mix2s` tmux window via
`android_device_desktop.sh restart --serial <MIX2S_SERIAL> --open-wechat` and
then verify with `android_control.py status --serial <MIX2S_SERIAL>` plus a
screenshot under `output/android_device_agent/`. Do not bypass QR/CAPTCHA or
change credentials; the account owner must complete any login prompt manually.
If the restart succeeds but the login prompt is still pending, leave the phone
on the WeChat login screen and report the `wechat_login_required` code as
awaiting manual account-owner action rather than retrying repeatedly. When the
health guard reports a repeated `wechat_login_required` that survives the
restart, first confirm the exact `labcanvas-android-mix2s` tmux window is the
only Android transport target, then verify the device is still reachable via
`adb devices -l` before concluding the login is genuinely pending; a stale or
orphaned scrcpy process can mask a healthy device and should be cleared only
after proving it is orphaned.

## Dedicated noVNC Desktop

Use the short on/off routine for a persistent phone-control desktop:

```bash
scripts/mix2s on --serial <MIX2S_SERIAL>
scripts/mix2s status --serial <MIX2S_SERIAL>
scripts/mix2s off --serial <MIX2S_SERIAL>
```

Use `scripts/mix2s dual --serial <MIX2S_SERIAL>` to keep personal WeChat on
the physical display and WeCom on a dedicated virtual display in the same
noVNC desktop. `dual` is persisted as the desired layout: Android senders may
temporarily take the physical display, then restore both panes. If WeCom's
single-task activity leaves the virtual surface stale, the relay verifies the
surface and recreates only the `wecom-virtual` pane; it does not restart
personal WeChat, noVNC, or the complete relay stack.

Open the printed noVNC URL. The desktop runs `scrcpy` for direct mouse/keyboard
control and keeps the phone awake while connected. Its tmux pane also retries
the exact device after a transient USB/ADB disconnect, so a live noVNC transport
does not remain permanently blank after `scrcpy` exits.

After ADB becomes `unauthorized` or the device disconnects, the primary
physical-WeChat supervisor and the virtual-WeCom supervisor stay durable and
idle (no CPU churn) instead of spinning. Once the same device is authorized
again, both supervisors resume automatically. If an existing
`labcanvas-android-mix2s` tmux session is missing only the primary window, the
relay repairs that single window in place without duplicating mirrors or
restarting unrelated project runtimes.

To start the mirror and bring mobile WeChat to the foreground:

```bash
agentic_tools/android_device_agent/scripts/android_device_desktop.sh restart \
  --serial <MIX2S_SERIAL> \
  --open-wechat
```

Defaults:

- X display: `:99`
- VNC: `127.0.0.1:5929`
- noVNC: `http://127.0.0.1:6129/...`
- tmux session: `labcanvas-android-mix2s`

Detailed MIX 2S and mobile-WeChat desktop-unlock steps are in
`docs/MIX2S_ADB_SCRCPY_RUNBOOK.md`.

`off` stops the Android tmux retry loop, scrcpy, display `:99`, VNC/noVNC
listeners, and the display keep-awake process. It then disables Android's USB
stay-awake setting and sends `KEYCODE_SLEEP`, leaving WeChat and WeCom desktop
services untouched.

The long command remains available and accepts the same `on`, `off`, and
`status` actions:

```bash
agentic_tools/android_device_agent/scripts/android_device_desktop.sh off
```

See `../../references/mix2s-mirror-power-routine.md` for the ownership boundaries,
verification checks, and heat-reduction behavior.

## Direct ADB Control

Use the CLI wrapper for scripted actions:

```bash
agentic_tools/android_device_agent/scripts/android_control.py status --serial <MIX2S_SERIAL>
agentic_tools/android_device_agent/scripts/android_control.py screenshot --serial <MIX2S_SERIAL>
agentic_tools/android_device_agent/scripts/android_control.py tap --serial <MIX2S_SERIAL> 540 1800
agentic_tools/android_device_agent/scripts/android_control.py swipe --serial <MIX2S_SERIAL> 540 1800 540 400 --duration 400
agentic_tools/android_device_agent/scripts/android_control.py text --serial <MIX2S_SERIAL> "hello from LabCanvas"
agentic_tools/android_device_agent/scripts/android_control.py key --serial <MIX2S_SERIAL> HOME
agentic_tools/android_device_agent/scripts/android_control.py url --serial <MIX2S_SERIAL> https://lazying.art
```

Screenshots are saved under `output/android_device_agent/`.

## MIX 2S-Shaped Emulator

Create an optional local AVD matching the phone's screen envelope:

```bash
agentic_tools/android_device_agent/scripts/create_mix2s_avd.sh
```

Launch it:

```bash
emulator -avd LabCanvas_MIX2S_API34 -no-snapshot-load
```

The emulator is useful for app installation tests. Do not use it for WeChat or
other account-bound workflows unless the account owner logs in there manually.

## Transport Repair Notes

When the deterministic health guard reports a repeated WeChat/WeCom runtime
fault that survives normal scripted recovery, treat this agent as the bounded
transport repair layer. Allowed recovery actions are local and reversible:
inspect status/logs, restart an exact dead or stalled tmux window, resume a
durable task, clear an orphaned process only after proving it is orphaned, and
run focused tests. Never send chat messages, publish, place orders, change
credentials/accounts, bypass QR/CAPTCHA, delete user data, rewrite unrelated
code, or restart a healthy logged-in GUI. If the fault is genuinely too complex
for medium reasoning and still unresolved, emit the exact marker `ESCALATE_HIGH`
once and stop.

## Safety

- Do not commit screenshots, app data, ADB backups, or private logs.
- Keep noVNC bound to `127.0.0.1`; use SSH tunneling for remote viewing.
- Prefer `android_control.py status` and screenshots before tapping.
- Use exact `--serial` when more than one Android target is connected.
