# MIX 2S ADB and Scrcpy Runbook

This runbook documents the safe workflow used to mirror and control the Xiaomi
MIX 2S from LabCanvas. It assumes the phone has already authorized this
computer in Android's ADB prompt.

## Safety Boundary

- Do not bypass a secure phone lock screen, PIN, password, pattern, or app
  credential prompt.
- `wm dismiss-keyguard` only dismisses a non-secure keyguard. If Android asks
  for credentials, unlock manually on the phone.
- Keep noVNC bound to `127.0.0.1` and use SSH tunneling for remote access.

## Check the Device

```bash
adb devices -l
scripts/mix2s key-status --serial <ADB_SERIAL>
agentic_tools/android_device_agent/scripts/android_control.py --serial <ADB_SERIAL> status
adb -s <ADB_SERIAL> shell dumpsys window | rg 'mCurrentFocus|isStatusBarKeyguard'
```

`scripts/mix2s key-status` is the only supported identity diagnostic. It
validates and fingerprints the existing private key without changing it. Never
run `adb keygen ~/.android/adbkey` as a fingerprint or health probe: that command
replaces the key and forces a new device authorization.

For the local MIX 2S, the useful state was:

- model: `MIX 2S`
- Android: `10`
- screen: `1080x2160`
- keyguard: `isStatusBarKeyguard=false`

## Start the Phone Mirror

Turn on the dedicated tmux-held virtual desktop and optionally open mobile
WeChat:

```bash
scripts/mix2s on \
  --serial <ADB_SERIAL> \
  --open-wechat
```

Default endpoints:

- X display: `:99`
- VNC: `127.0.0.1:5929`
- noVNC: `http://127.0.0.1:6129/vnc.html?host=127.0.0.1&port=6129&autoconnect=1&resize=scale&reconnect=1&reconnect_delay=1000`

If the browser canvas turns white but the Android mirror is still healthy,
run `scripts/mix2s transport-restart`. It replaces only websockify and keeps
Xvfb, scrcpy, phone state, WeChat, and WeCom intact. A viewer opened with the
URL above reconnects automatically.

If the phone occupies only a small upper-left area, repair the **host window**:

```bash
scripts/mix2s fit
```

This reads the live X desktop size and fits the existing single scrcpy window
at `(0, 0)`. It does not call ADB, send phone input, switch apps, poll the phone,
restart services, or change login state. It refuses to cover a visible dual
mirror. Supply `--serial <ADB_SERIAL>` only if the saved mirror identity is absent.

On 2026-09-05, the root canvas was 1440x2400 but scrcpy occupied only 672x1344
at `(180, 120)`. The browser's `resize=scale` correctly scaled the entire canvas,
including its empty area. Fitting the window to 1440x2400 fixed the view; scrcpy
keeps the phone aspect ratio with narrow centered side margins. The launcher
now uses desktop-sized windows instead of the old 540x1080 defaults and fits
single mode when starting/reusing it. A running legacy supervisor is not
restarted just for sizing; `fit` repairs its current window in place.

Dual mode includes a lock-aware activity guard. It repairs immediately when the
shared phone lane is free. It publishes a cooperative fairness request only
after the layout has remained wrong continuously beyond the stale grace period,
so normal WeCom polling is not interrupted and explicit message/artifact sends
still take priority. If WeCom was left on the physical display or the virtual
display fell back to Android Home, it restores WeChat-left and recreates only
the virtual WeCom mirror. The same repair is available as
`scripts/mix2s dual-heal`.
The virtual pane may be briefly blank while WeCom is deliberately using display
0 for UIAutomator; a persistent blank pane after the action is a fault.

- tmux session: `labcanvas-android-mix2s`

The launcher runs:

```bash
adb -s <ADB_SERIAL> shell input keyevent 224
adb -s <ADB_SERIAL> shell wm dismiss-keyguard
adb -s <ADB_SERIAL> shell svc power stayon true
scrcpy --serial <ADB_SERIAL> --stay-awake --disable-screensaver
adb -s <ADB_SERIAL> shell monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1
```

The tmux pane is a lightweight retry supervisor. If USB/ADB disconnects,
`scrcpy` may exit but Xvfb, x11vnc, and noVNC remain available. The pane checks
the exact serial every 10 seconds and restores only the missing mirror after the
device reconnects. Override the interval with `ANDROID_DEVICE_RETRY_SECONDS`.
`android_device_desktop.sh status --serial <ADB_SERIAL>` distinguishes a live
mirror from a transport-only desktop waiting for retry.

The supervisor is also authorization-aware. While `adb devices` reports
`unauthorized`, both physical-WeChat and virtual-WeCom panes block in
`adb wait-for-device` instead of repeatedly launching scrcpy or app-control
commands. Once the existing computer key is accepted on the phone, both panes
resume automatically. If scrcpy previously removed the primary tmux window but
the dual-layout windows kept the session alive, `scripts/mix2s on` recreates the
missing `wechat-physical` supervisor without restarting the surviving display,
VNC, noVNC, WeChat, or WeCom resources.

## Turn the Mirror and Phone Screen Off

When mobile control is not needed, use the complete off routine rather than
leaving a blank noVNC desktop running:

```bash
scripts/mix2s off --serial <ADB_SERIAL>
scripts/mix2s status --serial <ADB_SERIAL>
```

`off` is idempotent. It stops only the MIX 2S resources identified by tmux
session, serial, X display `:99`, VNC `5929`, and noVNC `6129`. It also runs:

```bash
adb -s <ADB_SERIAL> shell svc power stayon false
adb -s <ADB_SERIAL> shell input keyevent 223
```

Expected status is `mirror: off`, `transport: off`, `phone: Asleep`, and
`USB stay-awake: 0`. This reduces display and mirroring load while preserving
ADB authorization and does not stop the separate computer WeChat or WeCom
desktops. `on` wakes the phone but never bypasses a secure lock.

## Unlock Desktop WeChat from Mobile WeChat

Use this only when the account owner requests unlocking the logged-in desktop
session. On a MIX 2S at `1080x2160`:

Run the guarded LabCanvas watchdog once:

```bash
PYTHONPATH=src python -m agenticapp wechat unlock-watchdog once \
  --serial <ADB_SERIAL> \
  --flush-deferred
```

The watchdog first checks that the Linux WeChat window is actually locked. If it
is not locked, it only refreshes keep-awake settings.

Manual equivalent:

1. Open mobile WeChat. If the chat list shows `桌面微信已锁定`, tap the banner:

   ```bash
   adb -s <ADB_SERIAL> shell input tap 505 282
   ```

2. On `已登录设备`, tap the center lock control:

   ```bash
   adb -s <ADB_SERIAL> shell input tap 540 690
   ```

3. Verify the card shows `未锁定`:

   ```bash
   adb -s <ADB_SERIAL> exec-out screencap -p > output/android_device_agent/$(date +%F)/mix2s-wechat-unlocked.png
   ```

If the coordinates drift after a WeChat or MIUI layout change, use the noVNC
mirror and click the same visible controls manually.

## Troubleshooting

- If `scrcpy` is running but no window appears, inspect:

  ```bash
  tmux capture-pane -pt labcanvas-android-mix2s -S -120
  DISPLAY=:99 XAUTHORITY= xwininfo -root -tree
  ```

- If noVNC is black while its HTTP page and VNC port are healthy, inspect
  `android-mix2s_app.log`. `Device disconnected` means the old mirror exited;
  the retry supervisor should relaunch it when the exact device returns.

- If no device is found, reconnect USB and re-run `adb devices -l`.
- If the exact device is listed as `unauthorized`, accept the existing computer
  key on the phone once. Do not delete or regenerate `~/.android/adbkey`; the
  waiting supervisors will resume with the same key after authorization.
- If multiple devices are connected, always pass `--serial`.
