# LabCanvas Studio Browser Control

LabCanvas has a dedicated visible browser desktop for testing the real web UI without disturbing WeChat, Xiaoyunque, JLC, or other browser profiles.

## Start and View

```bash
scripts/launch_labcanvas_studio_novnc.sh start
```

Default endpoints:

- Studio: `http://127.0.0.1:19474`
- noVNC: `http://127.0.0.1:6114/vnc_lite.html?host=127.0.0.1&port=6114&autoconnect=1&resize=remote`
- Chrome CDP: `http://127.0.0.1:9444`
- X display: `:94`

All remote-control ports bind to localhost. Use an SSH tunnel when viewing from another machine.

## Visible Chat Control

The controller fills the visible composer, selects the visible model/effort/mode controls, clicks Send once, captures the returned task ID, and monitors that exact task.

```bash
scripts/labcanvas_studio_browser.py status
scripts/labcanvas_studio_browser.py chat \
  --message-file /tmp/labcanvas-task.md \
  --model gpt-5.6-sol \
  --effort ultra \
  --mode execute \
  --wait-seconds 10800
scripts/labcanvas_studio_browser.py monitor --task-id TASK_ID
```

Evidence screenshots are written under ignored `output/webapp/browser-evidence/`. The controller may read task status through the page when reconnecting, but it never mutates the application through a private API or bypasses the visible chat submission.

## Acceptance Contract

A Studio CAD task is complete only when the exact task reaches a terminal state and its claimed files pass independent checks. Validate run-folder placement, source scripts, STEP validity and solid count, STL watertightness and components, 3MF structure, full-view render, manifest dimensions, and Nutstore handoff. A chat reply alone is not proof of completion.
