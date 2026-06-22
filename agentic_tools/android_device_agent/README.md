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

## Dedicated noVNC Desktop

Start a persistent phone-control desktop:

```bash
agentic_tools/android_device_agent/scripts/android_device_desktop.sh start --serial <MIX2S_SERIAL>
```

Open the printed noVNC URL. The desktop runs `scrcpy` for direct mouse/keyboard
control and keeps the phone awake while connected.

Defaults:

- X display: `:99`
- VNC: `127.0.0.1:5929`
- noVNC: `http://127.0.0.1:6129/...`
- tmux session: `labcanvas-android-mix2s`

Stop only the Android desktop session:

```bash
agentic_tools/android_device_agent/scripts/android_device_desktop.sh stop
```

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

## Safety

- Do not commit screenshots, app data, ADB backups, or private logs.
- Keep noVNC bound to `127.0.0.1`; use SSH tunneling for remote viewing.
- Prefer `android_control.py status` and screenshots before tapping.
- Use exact `--serial` when more than one Android target is connected.
