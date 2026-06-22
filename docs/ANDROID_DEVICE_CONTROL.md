# Android Device Control

LabCanvas can control a connected Android phone through ADB and a dedicated
noVNC desktop. The current target class is the Xiaomi Mi MIX 2S (`polaris`).
Find the local serial with `adb devices -l`.

## Real Device Path

Use the real device when the task depends on installed apps, logins, WeChat,
photos, files, notifications, or account state.

```bash
agentic_tools/android_device_agent/scripts/android_device_desktop.sh start --serial <MIX2S_SERIAL>
agentic_tools/android_device_agent/scripts/android_control.py status --serial <MIX2S_SERIAL>
```

The desktop runs separately from the WeChat desktop:

```text
http://127.0.0.1:6129/vnc_lite.html?host=127.0.0.1&port=6129&autoconnect=1&resize=remote
```

## Scripted Actions

```bash
agentic_tools/android_device_agent/scripts/android_control.py screenshot --serial <MIX2S_SERIAL>
agentic_tools/android_device_agent/scripts/android_control.py tap --serial <MIX2S_SERIAL> 540 1800
agentic_tools/android_device_agent/scripts/android_control.py swipe --serial <MIX2S_SERIAL> 540 1800 540 400 --duration 400
agentic_tools/android_device_agent/scripts/android_control.py text --serial <MIX2S_SERIAL> "hello from LabCanvas"
agentic_tools/android_device_agent/scripts/android_control.py key --serial <MIX2S_SERIAL> BACK
```

Use screenshots and status checks before tapping. Coordinates are physical
screen pixels unless Android display scaling is changed.

## Emulator Path

For app testing without touching the phone:

```bash
agentic_tools/android_device_agent/scripts/create_mix2s_avd.sh
emulator -avd LabCanvas_MIX2S_API34 -no-snapshot-load
```

This AVD matches the MIX 2S screen (`1080x2160`, density `440`) but does not
share the real phone's app data or login state.

## Safety Notes

- Keep noVNC bound to localhost and access it through SSH tunneling when remote.
- Do not commit screenshots or ADB output containing private app data.
- Use `--serial` for every automated command when more than one device or
  emulator is attached.
