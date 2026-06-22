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
agentic_tools/android_device_agent/scripts/android_control.py --serial <ADB_SERIAL> status
adb -s <ADB_SERIAL> shell dumpsys window | rg 'mCurrentFocus|isStatusBarKeyguard'
```

For the local MIX 2S, the useful state was:

- model: `MIX 2S`
- Android: `10`
- screen: `1080x2160`
- keyguard: `isStatusBarKeyguard=false`

## Start the Phone Mirror

Start or restart the dedicated tmux-held virtual desktop and open mobile
WeChat:

```bash
agentic_tools/android_device_agent/scripts/android_device_desktop.sh restart \
  --serial <ADB_SERIAL> \
  --open-wechat
```

Default endpoints:

- X display: `:99`
- VNC: `127.0.0.1:5929`
- noVNC: `http://127.0.0.1:6129/vnc_lite.html?host=127.0.0.1&port=6129&autoconnect=1&resize=remote`
- tmux session: `labcanvas-android-mix2s`

The launcher runs:

```bash
adb -s <ADB_SERIAL> shell input keyevent 224
adb -s <ADB_SERIAL> shell wm dismiss-keyguard
adb -s <ADB_SERIAL> shell svc power stayon true
scrcpy --serial <ADB_SERIAL> --stay-awake --disable-screensaver
adb -s <ADB_SERIAL> shell monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1
```

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

- If no device is found, reconnect USB and re-run `adb devices -l`.
- If multiple devices are connected, always pass `--serial`.
