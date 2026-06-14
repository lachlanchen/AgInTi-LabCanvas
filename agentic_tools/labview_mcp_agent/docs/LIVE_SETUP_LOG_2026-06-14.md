# Live Setup Log - 2026-06-14

## Host Check

Command:

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
```

Result:

- Ubuntu 24.04.4 LTS, x86_64.
- LabVIEW was initially absent.
- `xvfb`, `libopenal1`, and `libncurses6` are installed.

## Installer Check

Command:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --dry-run
```

Result:

- Authenticated NI download completed through the logged-in browser session.
- Downloaded file:

```text
/home/lachlan/Downloads/ni-labview-2026-community-26.1.2_linux.zip
```

- SHA256 verified:

```text
cc5afd57a3db083555c6d479d045c2b9642100da4b73891a7e758b1349057cf4
```

- The ZIP contains Ubuntu 22.04 and Ubuntu 24.04 feed packages. On this host the installer used the Ubuntu 24.04 feed:

```text
ni-labview-2026-community_26.1.2.49156-0+f4-ubuntu2404_all.deb
```

## LabVIEW Install

Commands:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --search-dir /home/lachlan/Downloads
sudo apt-get install -y ni-labview-2026-community
```

Result:

- Installed `ni-labview-2026-community` 26.1.2.49156-0+f4.
- Installed core, runtime, desktop support, examples, help, CLI, compare/merge utilities, and Python interface support.
- Launcher paths:

```text
/usr/local/bin/labview64
/usr/local/natinst/LabVIEW-2026-64/labview
/usr/local/bin/LabVIEWCLI
```

- First GUI launch may still require NI activation/sign-in.

Verification:

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
LabVIEWCLI -help
```

Result:

- `probe_labview.sh` detects `labview64` and `LabVIEWCLI`.
- `LabVIEWCLI -help` prints the expected operation syntax, including `RunVI`, `CloseLabVIEW`, and `-Headless`.
- Full post-install details are recorded in `POST_INSTALL_REPORT_2026-06-14.md`.

## MCP Candidate Install

Command:

```bash
agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman
```

Result:

- Cloned `https://github.com/nineman-YU/Labview_mcp.git`.
- Local path:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp
```

## Next Manual Boundary

1. Activate LabVIEW if prompted on first GUI launch.
2. Open the cloned `Labview_mcp` project and run its server VI.
3. Use `mcp.example.json` or `labview_http_mcp_bridge.py` to connect a normal MCP client.
