# Security Policy

## Supported Surface

AppAutoAction is currently a local CLI and target registry. It does not host a network server by default. Security-sensitive behavior starts when a configured target points to an editor bridge, browser session, command, or remote MCP endpoint.

## Reporting

Open a GitHub issue for non-sensitive bugs. For suspected credential exposure, unsafe default behavior, or command execution vulnerabilities, contact the maintainer through https://lazying.art before publishing details.

## Local Automation Rules

- Keep editor bridges bound to `127.0.0.1` unless remote access is intentional.
- Run `dispatch --dry-run` before live dispatch to inspect the exact envelope.
- Do not commit `agenticapp.targets.json`; it may contain local ports, private paths, or tokens.
- Store secrets in environment variables such as `BIORENDER_API_KEY`.
- Treat `local_command` targets as code execution. Only configure commands you trust.
- Treat Unreal, Unity, and Blender script execution bridges as privileged editor access.

## BioRender

Use BioRender's documented MCP connector and normal authentication flow. Do not automate BioRender by scraping the web application unless the account owner has explicit permission and the workflow complies with BioRender's terms.

## Future Hardening

Planned improvements include per-target allowlists, persistent audit logs, schema validation for target payloads, and explicit confirmation gates for live write operations.
