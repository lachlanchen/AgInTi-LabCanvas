# LabVIEW Linux Setup

Date checked: 2026-06-14.

## Current Workstation

```text
Ubuntu 24.04.4 LTS x86_64
Kernel 6.8.0-107-generic
```

Installed support packages:

- `xvfb`
- `libopenal1`
- `libncurses6`

No NI/LabVIEW packages are currently installed.

## NI Download Boundary

NI’s LabVIEW download page lists Linux as a supported OS and shows current versions through 2026 Q1, but the actual download action is behind NI login and may require a trial, license, subscription, or service entitlement. Because of that, this repo does not vendor LabVIEW installers and does not store NI credentials.

Download source:

- <https://www.ni.com/en/support/downloads/software-products/download.labview.html>

Suggested selection for this server:

- OS: Linux
- Bitness: 64-bit
- Edition: Community for non-commercial evaluation, or Professional if licensed
- Version: newest available that supports your desired MCP toolkit; 2026 Q1/26.1 is useful because one MCP candidate documents native HTTP/JSON support for 26.1.

## Install Flow

1. Download the Linux installer from NI into `~/Downloads`.
2. Keep the original `.zip` or `.deb`; do not commit it.
3. Run:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh
```

The script searches for LabVIEW installer archives in `~/Downloads`, extracts a zip when needed, installs NI feed `.deb` packages, runs `apt update`, and then tries the likely LabVIEW package names for the discovered version/edition.

## Expected Package Pattern

Recent Linux installers commonly install a feed package first, then use apt for the IDE package. Example pattern:

```bash
sudo dpkg -i ni-labview-*-ubuntu*.deb
sudo apt update
sudo apt install ni-labview-*-pro
```

Exact package names vary by NI release and edition. The script intentionally prints candidate packages before installing.

## Activation

LabVIEW may require NI License Manager activation after installation. For remote GUI activation, use a forwarded X11 session or start the IDE through the `launch_labview.sh` helper. Do not put NI credentials or serial numbers in git.

## Verification

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
labview --version  # if the NI launcher provides this
```

If `labview` is not in `PATH`, check likely install directories:

```bash
find /usr/local /opt -iname 'labview*' -maxdepth 5 2>/dev/null
```
