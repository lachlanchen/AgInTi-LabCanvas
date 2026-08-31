# MIX 2S Mirror and Power Routine

This is the canonical on/off workflow for the connected Xiaomi MIX 2S. Use it
only when direct mobile control is needed; ordinary LabCanvas WeChat and WeCom
automation runs on separate computer desktops and does not require this mirror.

## Commands

```bash
cd /home/lachlan/ProjectsLFS/AgenticApp
scripts/mix2s on
scripts/mix2s dual
scripts/mix2s single
scripts/mix2s status
scripts/mix2s off
```

Pass `--serial SERIAL` when multiple Android targets are attached. A successful
`on` saves the selected serial under ignored `output/android_device_agent/`, so
later `status` and `off` calls continue to target the same phone.

To open mobile WeChat after starting the mirror:

```bash
scripts/mix2s on --open-wechat
```

To show both logged-in clients without creating another noVNC stack:

```bash
scripts/mix2s dual
```

This keeps WeChat on the physical phone display and starts WeCom on one Android
virtual display. Both scrcpy windows are tiled side by side inside the same
display `:99` and the same noVNC URL. The selected layout is persisted under
ignored `output/android_device_agent/`, so a later `on` or `restart` restores
the dual view. Use `scripts/mix2s single` to remove the virtual display and
return to one centered physical-phone mirror.

## What On Owns

The routine starts only these dedicated resources:

- tmux session `labcanvas-android-mix2s`;
- scrcpy for the exact saved Android serial;
- in `dual` mode, one additional scrcpy window and one Android virtual display
  for WeCom;
- X display `:99` at `1440x2400x24`;
- localhost VNC `5929` and noVNC `6129`;
- the X11 keep-awake loop for display `:99`.

The full-client URL is:

```text
http://127.0.0.1:6129/vnc.html?host=127.0.0.1&port=6129&autoconnect=1&resize=scale&reconnect=1&reconnect_delay=1000
```

`on` wakes the display, dismisses only a non-secure keyguard, and enables
stay-awake while connected. It does not bypass a PIN, password, pattern, or app
login. The retry supervisor restores scrcpy after a transient ADB disconnect.

## What Off Does

`off` is safe to repeat. It terminates the exact tmux session, scrcpy process,
noVNC/websockify relay, x11vnc relay, X11 keep-awake loop, and Xvfb display.
Process matching is constrained by serial, display, and ports. It does not
touch the WeChat desktop, WeCom desktop, or their noVNC ports.

After transport cleanup, it disables Android USB stay-awake and sends
`KEYCODE_SLEEP`:

```text
svc power stayon false
input keyevent 223
```

This leaves ADB authorization intact but removes screen, encoding, and mirror
load. USB charging can still produce heat; unplug the cable when ADB access is
not needed and charging heat remains a concern.

## Verification

```bash
scripts/mix2s status
```

Expected off state:

```text
status: stopped
mirror: off
transport: off
phone: Asleep
USB stay-awake: 0
```

Expected on state reports a running tmux session, connected mirror, online
transport, current `single` or `dual` layout, and the noVNC URL. If the phone is
disconnected, `off` still cleans the computer-side stack and reports that it
could not change phone power.
If the browser view turns white while `scripts/mix2s status` still reports a
connected mirror, repair only the viewer transport:

```bash
scripts/mix2s transport-restart
```

Reload the URL above if the old tab did not include `reconnect=1`. This does
not restart scrcpy, Xvfb, WeChat, WeCom, or the phone.

In dual mode, a low-frequency guard also checks the actual Android activities,
not only whether two scrcpy windows exist. If an interrupted WeCom action moves
WeCom to the physical display and leaves the virtual display on Android Home,
the guard publishes a cooperative fairness request, waits for the current exact
chat action, restores WeChat on the left, and recreates only the virtual WeCom
mirror. Passive pollers yield to this request; explicit sends still win. Run
`scripts/mix2s dual-heal` for the same bounded repair on demand. A brief blank
right pane is expected while UIAutomator temporarily uses WeCom on display 0;
remaining blank after the action and guard cycle is not expected.
