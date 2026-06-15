# Camera MCP Test Report - 2026-06-15

## Scope

The requested Raspberry Pi camera path was tested against the actual camera present on this workstation: a Logitech C922 USB webcam exposed through Linux V4L2. A simulator camera MCP endpoint was also added so LabCanvas can test camera-driven workflows without a live physical camera or a fully activated LabVIEW VI server.

## Hardware Camera Result

- Device: `/dev/video0`
- Name: `C922 Pro Stream Webcam`
- Working capture command:

```bash
ffmpeg -hide_banner -y \
  -f v4l2 -input_format mjpeg -video_size 1280x720 \
  -i /dev/video0 -frames:v 1 \
  output/labview_mcp_camera/2026-06-15/c922_capture_1280x720.jpg
```

The captured file is a valid 1280x720 JPEG. The frame is very dark, which indicates the camera is reachable but the scene/lens/exposure needs a visible target or lighting.

The Python V4L2 capture path also succeeded:

```text
output/labview_mcp_camera/2026-06-15/c922_capture_opencv.png
```

## Simulator MCP Result

New files:

- `scripts/camera_mcp_simulator.py`
- `scripts/test_camera_mcp_simulator.py`
- `tests/test_camera_mcp_simulator.py`

Generate one synthetic camera frame:

```bash
python agentic_tools/labview_mcp_agent/scripts/camera_mcp_simulator.py \
  capture-simulator \
  --output output/labview_mcp_camera/2026-06-15/simulator_capture.png \
  --width 1280 --height 720
```

Capture one frame from the Logitech camera:

```bash
python agentic_tools/labview_mcp_agent/scripts/camera_mcp_simulator.py \
  capture-v4l2 \
  --device /dev/video0 \
  --output output/labview_mcp_camera/2026-06-15/c922_capture_opencv.png \
  --width 1280 --height 720
```

Serve the camera tools as a JSON-RPC MCP HTTP endpoint:

```bash
python agentic_tools/labview_mcp_agent/scripts/camera_mcp_simulator.py serve \
  --host 127.0.0.1 --port 36988 \
  --device /dev/video0 \
  --output-dir output/labview_mcp_camera/2026-06-15
```

Forward stdio MCP frames to that endpoint with:

```bash
python agentic_tools/labview_mcp_agent/scripts/labview_http_mcp_bridge.py \
  --url http://127.0.0.1:36988/mcp/server
```

Smoke test:

```bash
python agentic_tools/labview_mcp_agent/scripts/test_camera_mcp_simulator.py
```

Live endpoint test on `127.0.0.1:36988` also succeeded:

- `tools/list` returned `camera.capture_simulator` and `camera.capture_v4l2`.
- `camera.capture_simulator` wrote `output/labview_mcp_camera/2026-06-15/simulator_capture_mcp.png`.
- `camera.capture_v4l2` wrote `output/labview_mcp_camera/2026-06-15/c922_capture_mcp.png`.

## LabVIEW VI Server Status

LabVIEW 2026 Q1 Community and `LabVIEWCLI` are installed, but the live LabVIEW VI server endpoint is not yet reachable headlessly.

Observed blockers:

- `LabVIEWCLI` reports it cannot establish a VI Server connection unless LabVIEW is running with VI Server enabled.
- LabVIEW reads preferences from `/home/lachlan/natinst/.config/LabVIEW-2026/labview.conf`.
- VI Server preference keys were written there, including `labview.server.tcp.enabled: True` and `labview.server.tcp.port: 3363`.
- Port `3363` and the candidate MCP port `36987` did not open.
- Direct LabVIEW GUI startup on the active remote display failed with an X `BadMatch` error.
- `Xvfb :99` did not resolve the LabVIEW display startup issue in this session; LabVIEW still reported `Unable to open X display`.

Next manual step: launch LabVIEW in a working desktop session, open `Tools > Options > VI Server`, enable TCP/IP, allow localhost access, then run the candidate VI `src/mcp_server_main.vi` from `nineman-YU/Labview_mcp`.
