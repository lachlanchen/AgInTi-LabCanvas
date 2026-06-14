# LabVIEW Post-Install Report - 2026-06-14

This document records the completed LabVIEW Community install on the local Ubuntu workstation for AgInTi LabCanvas.

## Host

- OS: Ubuntu 24.04.4 LTS, x86_64
- Kernel: `6.8.0-107-generic`
- Install target: local workstation under `/home/lachlan/ProjectsLFS/AgenticApp`

## Download Artifact

Authenticated NI download succeeded through the logged-in browser session.

```text
/home/lachlan/Downloads/ni-labview-2026-community-26.1.2_linux.zip
```

Verified checksum:

```text
cc5afd57a3db083555c6d479d045c2b9642100da4b73891a7e758b1349057cf4
```

Archive contents include feed installers for openSUSE 15.5/15.6, RHEL 8/9, Ubuntu 22.04, and Ubuntu 24.04. The Ubuntu 24.04 feed was used:

```text
ni-labview-2026-community_26.1.2.49156-0+f4-ubuntu2404_all.deb
```

## Account Setup Notes

NI required account profile completion before the download. The account was configured as non-partner, with organization `The University of Hong Kong` and job title `Student`. No NI credentials, serial numbers, cookies, or tokens are committed to this repository.

If NI still shows a non-student account type in the web profile, update it manually from NI profile settings. The installed software package is still LabVIEW Community Edition.

## Apt Feed

The feed package installed this apt source:

```text
/etc/apt/sources.list.d/ni-labview-2026-noble-community.list
```

Feed URL:

```text
https://download.ni.com/ni-linux-desktop/LabVIEW/2026/Q1/f2/community/deb/ni-labview-2026/noble
```

Signing key:

```text
/usr/share/keyrings/ni-labview-2026-noble-community.asc
```

## Installed Packages

Primary packages:

- `ni-labview-2026-community` 26.1.2.49156-0+f4
- `ni-labview-2026-core` 26.1.2.49156-0+f4
- `labview-2026-community-exe` 26.1.2.49156-0+f4
- `labview-2026-rte` 26.1.2.49156-0+f4
- `ni-labview-command-line-interface` 26.1.0.49328-0+f176

Installed support includes desktop integration, examples, online help, application builder runtime support, compare/merge utilities, Python interface support, NI Wine, NI service locator, NI system configuration runtime, and EULA depot packages.

## File Layout

Main install trees:

```text
/usr/local/natinst/LabVIEW-2026-64
/usr/local/lib64/LabVIEW-2026-64
```

Observed sizes:

```text
1.3G  /usr/local/natinst/LabVIEW-2026-64
449M  /usr/local/lib64/LabVIEW-2026-64
```

Launchers:

```text
/usr/local/bin/labview64
/usr/local/natinst/LabVIEW-2026-64/labview
/usr/local/bin/LabVIEWCLI
```

Desktop entry:

```text
/usr/share/applications/labview64-2026.desktop
```

## Verification

Run the repository probe:

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
```

Expected launcher result:

```text
labview: not in PATH
labview64: /usr/local/bin/labview64
LabVIEWCLI: /usr/local/bin/LabVIEWCLI
```

CLI verification:

```bash
LabVIEWCLI -help
```

Confirmed output includes `RunVI`, `CloseLabVIEW`, `-Headless`, `-LabVIEWPath`, and `-PortNumber` options.

## Launch

GUI launch:

```bash
labview64
```

Repository helper:

```bash
agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
```

Headless/Xvfb launch helper:

```bash
LABVIEW_USE_XVFB=1 agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
```

First GUI launch may still require NI activation/sign-in. Complete that interactively before expecting MCP-controlled LabVIEW operations to work.

## MCP Integration Status

Recommended candidate remains:

```text
https://github.com/nineman-YU/Labview_mcp.git
```

Local clone path:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp
```

Next steps:

1. Activate LabVIEW on first GUI launch if prompted.
2. Open the candidate LabVIEW MCP project.
3. Run the LabVIEW HTTP/JSON-RPC server VI.
4. Connect through `agentic_tools/labview_mcp_agent/scripts/labview_http_mcp_bridge.py`.

Bridge test details:

```text
agentic_tools/labview_mcp_agent/docs/MCP_BRIDGE_TEST_REPORT_2026-06-14.md
```

## Maintenance Commands

Check package status:

```bash
dpkg -l | grep -Ei 'labview|ni-labview|ni-wine|ni-python-interface'
```

Refresh NI package metadata:

```bash
sudo apt update
apt-cache policy ni-labview-2026-community
```

Remove LabVIEW Community packages if needed:

```bash
sudo apt remove 'ni-labview-2026*' 'labview-2026*'
sudo apt autoremove
```

Do not commit NI installers, extracted package caches, account credentials, activation artifacts, or browser session data.
