# LCEDA Pro Local Setup

## Installed Version

The downloaded official Linux archive was verified with `unzip -tq` and
installed locally instead of through the system `/opt` installer:

```text
archive: ~/Downloads/lceda-pro-linux-x64-3.2.149.zip
size: 358079031 bytes
install root: ~/.local/opt/lceda-pro-3.2.149/lceda-pro
wrapper: ~/.local/bin/lceda-pro
app version observed: 3.2.149.88089769
electron observed: 36.3.1
chrome observed: 136.0.7103.113
```

The first partial download was kept only as:

```text
~/Downloads/lceda-pro-linux-x64-3.2.149.zip.truncated-20260614
```

## Activation

Activation was performed through the LCEDA activation UI using the local file:

```text
~/Downloads/lceda-pro-activation.txt
```

The content is private license data. Do not print it, commit it, copy it into
documentation, or place it under project folders. LCEDA also copied activation
state under `~/Documents/LCEDA-Pro`; keep that directory outside git.

## Launch Pattern

Use a deterministic CDP port so agents can inspect the Electron page:

```bash
LCEDA_PRO_EXTRA_ARGS='--disable-gpu --remote-debugging-port=51370 --remote-allow-origins=*' \
  nohup setsid ~/.local/bin/lceda-pro > ~/.cache/lceda-pro/lceda-pro.log 2>&1 &
```

Prefer the wrapper script:

```bash
agentic_tools/jlceda_mcp_agent/scripts/launch_lceda_pro.sh --restart --port 51370
python3 agentic_tools/jlceda_mcp_agent/scripts/lceda_cdp.py status --port 51370
```

`--remote-allow-origins=*` is needed with the bundled Chromium 136 CDP
WebSocket origin checks. The wrapper defaults to `--no-sandbox` because this
remote Ubuntu desktop did not provide a working Electron sandbox.

## Validation

Observed after activation:

```text
title: 嘉立创EDA(专业版) - V3.2.149.88089769
url: https://client/editor?cll=warn#
```

The post-activation screenshot was captured to `/tmp/lceda-pro-after-activation.png`
for local verification only.
