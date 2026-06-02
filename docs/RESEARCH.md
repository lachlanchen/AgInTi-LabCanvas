# Research Brief: Agent Control for Creative Apps

Research date: 2026-06-02

This brief summarizes the current GitHub and vendor landscape for agent-controlled Blender, BioRender, Unity, and Unreal workflows. The goal is to justify AppAutoAction's registry-plus-adapter design instead of binding the project to one editor plugin.

## Executive Summary

MCP has become the common integration shape for AI agents that need external capabilities. Official MCP documentation describes servers as exposing tools, resources, and prompts; tools are schema-defined operations that models can call, while resources and prompts provide context and reusable workflows. That maps well to editor automation, where an agent needs both read access to scene/project state and explicit write tools.

The practical landscape is fragmented. Blender, Unity, and Unreal each have working community bridges, but they differ in ports, transports, installation flows, and safety assumptions. BioRender is different: its current public path is an official remote MCP connector that supports natural-language search of icons and templates through compatible AI assistants.

AppAutoAction should therefore remain a control hub rather than a monolithic replacement for those bridges.

## Findings by Target

| Target | Evidence | Implication for AppAutoAction |
| --- | --- | --- |
| MCP standard | MCP servers expose tools, resources, and prompts with schema-defined tool calls and user/application control boundaries. Source: https://modelcontextprotocol.io/docs/learn/server-concepts | Keep dispatch envelopes explicit and emit MCP config instead of inventing a competing protocol. |
| Blender | `sandraschi/blender-mcp` supports natural-language Blender automation, headless operation, live GUI bridge mode, exports, rendering, and asset workflows. Source: https://github.com/sandraschi/blender-mcp | Support both local HTTP and command dispatch; do not require the Blender UI for every workflow. |
| Blender + Unreal | `tahooki/unreal-blender-mcp` shows a unified server controlling Blender and Unreal through one AI-facing interface, with Blender and Unreal editor-side bridges. Source: https://github.com/tahooki/unreal-blender-mcp | A multi-target registry is useful; target routing should not be hard-coded into one editor. |
| Unity | `CoplayDev/unity-mcp` positions MCP as a bridge from Claude, Codex, VS Code, local LLMs, and others into Unity for assets, scenes, scripts, tests, and workflows. Source: https://github.com/CoplayDev/unity-mcp | Keep MCP client export first-class. |
| Unity industrial/digital twin | `game4automation/io.realvirtual.mcp` exposes tools through C# attributes, auto-discovery, WebSocket transport, multi-instance support, and digital twin controls. Source: https://github.com/game4automation/io.realvirtual.mcp | Allow project-specific endpoints and future tool discovery metadata. |
| Unity editor operations | `usmanbutt-dev/unity-mcp` lists hierarchy, GameObject, prefab, scene, asset, console, compilation, screenshot, play-mode, input, animation, and material tools. Source: https://github.com/usmanbutt-dev/unity-mcp | A safe dry-run layer is needed because live tools mutate editor state. |
| Unreal | `runreal/unreal-mcp` uses Unreal Python Remote Execution without a new plugin and warns that agents have full editor access. Source: https://github.com/runreal/unreal-mcp | Treat Unreal targets as privileged. Prefer localhost, consent, and dry-run inspection. |
| BioRender | BioRender documents an MCP connector at `https://mcp.services.biorender.com/mcp`; users authenticate with BioRender credentials, approve permissions, then search icons and templates from compatible AI assistants. Source: https://help.biorender.com/hc/en-gb/articles/36112020714141-How-to-use-the-BioRender-MCP-connector | Use official connector metadata and browser handoff; avoid scraping or unofficial automation. |
| GitHub presentation | GitHub recommends README files explain what a project does, why it is useful, how to start, where to get help, and who maintains it. Source: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes | Keep README landing-page quality but move deep notes into docs. |
| GitHub discovery | GitHub topics help users find and contribute to projects and must use lowercase letters, numbers, and hyphens, with no more than 20 topics. Source: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics | Set concise repository topics for MCP, agents, Blender, Unity, Unreal, and automation. |

## Recommended Direction

1. Keep AppAutoAction as a neutral dispatcher and metadata hub.
2. Support MCP config generation for existing bridge projects.
3. Add transport adapters incrementally: HTTP JSON, local command, browser handoff, then native MCP client/server modes.
4. Add target capability discovery after a bridge reports structured tools.
5. Keep dry-run output as the default demo path and as the safety review surface.

## Security Notes

Editor bridges can create files, run scripts, alter scenes, export assets, or execute Python/C# in privileged processes. Treat every live target as a local automation endpoint with write access. Prefer localhost, explicit config, short-lived credentials, and reviewable dispatch logs.
