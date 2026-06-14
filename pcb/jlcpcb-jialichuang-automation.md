# JLCPCB / Jialichuang Order Automation Research

Date: 2026-06-14

## Short Answer

Yes, AgInTi LabCanvas can support JLCPCB/Jialichuang ordering workflows, but the safe default should be **prepare, validate, upload, quote, and stop before final order/payment** unless the user explicitly confirms the exact order.

There are three practical routes:

1. Official JLCPCB API for approved partners.
2. EasyEDA/Jialichuang EDA order integration for designs authored in EasyEDA.
3. Browser/app-assisted workflow for KiCad-generated Gerber zip uploads.

## Official API Status

JLCPCB now documents an official API platform. The PCB API is described as supporting file upload, automated pricing, PCB order creation, production progress, and order tracking. The same platform also lists stencil, 3D printing, and components APIs.

Access is not open by default. JLCPCB says users must apply, applications are reviewed, and approval depends on factors such as previous orders, company profile, and business situation. API partners must also follow branding restrictions.

Implication for AgInTi LabCanvas: add an API adapter, but make it optional and credential-gated. Store API credentials outside git, and keep dry-run mode as the default.

Sources:

- https://api.jlcpcb.com/
- https://jlcpcb.com/help/article/jlcpcb-online-api-available-now

## EasyEDA / Jialichuang EDA Automation

Jialichuang EDA documents direct manufacturing export and order flows. The standard flow generates local Gerber files, previews them, then uploads the Gerber zip to `jlc.com`. EasyEDA Pro's JavaScript API exposes beta manufacturing functions including Gerber export and PCB order placement methods.

This is powerful when the design lives in EasyEDA, but it is less direct for KiCad-native projects. For KiCad, prefer deterministic Gerber/BOM/CPL export first, then upload through the API or guarded browser automation.

Sources:

- https://docs.lceda.cn/cn/PCB/Order-PCB/index.html
- https://prodocs.lceda.cn/cn/api/reference/pro-api.pcb_manufacturedata.html

## JLCONE App

JLCPCB offers JLCONE as an official desktop/mobile app for PCB, PCBA, 3D printing, and CNC ordering. It supports file upload, automated quotes, ordering, and tracking. App automation may be possible through desktop UI automation, but this should be treated as less stable than an official API.

Source:

- https://jlcpcb.com/DOWNLOAD

## MCP and GitHub Options

Current public MCP-style tools are more useful for component search, BOM validation, KiCad editing, and fabrication package generation than for final paid order submission. I did not find a safe public MCP that can log into JLCPCB/JiaLiChuang, submit a paid PCB fabrication order, and stop at the correct payment boundary for arbitrary accounts.

Relevant options:

- `@jlcpcb/mcp` / `l3wi/jlc-cli`: JLC/EasyEDA component sourcing, library fetching, and KiCad-format conversion. Useful for PCBA component workflows, not needed for the bare through-hole HYBEC carrier.
- `jlcmcp.dev`: independent JLCPCB component search MCP, BOM export, stock/pricing checks. It states it is not affiliated with JLCPCB.
- `mixelpixx/KiCAD-MCP-Server`: KiCad MCP server with JLCPCB parts catalog and Freerouting integration.
- `BeckhamLabsLLC/kicad-jlcpcb`: Claude Code plugin plus MCP server that sources LCSC/JLCPCB parts and hands off a wired KiCad PCB to EasyEDA/JLCPCB-style workflows.
- `asukiaaa/gerber_to_order`: KiCad plugin to generate Gerber zip packages for vendors including JLCPCB.

Sources:

- https://www.npmjs.com/package/@jlcpcb/mcp
- https://github.com/l3wi/jlc-cli
- https://jlcmcp.dev/
- https://github.com/mixelpixx/KiCAD-MCP-Server
- https://github.com/BeckhamLabsLLC/kicad-jlcpcb
- https://github.com/asukiaaa/gerber_to_order

## Recommended AgInTi LabCanvas Workflow

For KiCad projects:

```bash
kicad-cli pcb drc --format json --severity-all -o artifacts/drc.json board.kicad_pcb
kicad-cli pcb export gerbers -o gerber board.kicad_pcb
kicad-cli pcb export drill -o gerber board.kicad_pcb
zip -r artifacts/jlcpcb-gerber.zip gerber
```

Then:

1. Verify DRC is clean or explicitly waived.
2. Verify Gerber layer names, outline, drill file, dimensions, board count, and order-number marking.
3. Upload through official API if approved.
4. Otherwise use browser/app automation to upload and fill quote settings.
5. Stop before final submit/payment and ask for human confirmation.

For the HYBEC HBL-273/HBL-667 carrier in this repository, the ready upload file is:

```text
pcb/hybec-hbl-273-g4/jlcpcb_order/hybec-hbl-273-g4-jlcpcb-gerber.zip
```

That order pack is bare-PCB only and includes an order-settings JSON, preflight manifest, DRC/ERC reports, renders, and a back-side `JLCJLCJLCJLC` marker for JLCPCB's order number placement.

## Implemented Local Tool

The reusable implementation now lives in:

```text
agentic_tools/jlcpcb_order_agent/
```

It provides:

- `scripts/launch_shared_chrome.sh`: launches or reuses a normal Chrome profile with CDP on port `49237`.
- `scripts/jlc_order_cdp.py`: attaches to the logged-in browser, uploads Gerbers, opens the parsed order form, fills prototype settings, fills shipping address/contact from private config, runs `检查订单`, and optionally submits with `--allow-submit`.
- `config.example.json`: public non-secret schema for order, browser, and shipping settings.
- `docs/AUTO_ORDER_SYSTEM.md`: detailed runbook for the tools, scripts, browser state, fallback utilities, and live HYBEC order state.

The live HYBEC order used this flow successfully through JLC order check. The blocking fields are recipient name and mobile phone; the address region/detail is already entered in the page but cannot be saved without those required contact values.

## Safety Boundary

The agent may automate:

- package generation;
- DRC and mechanical checks;
- Gerber zip creation;
- quote-page upload;
- option prefill;
- order-tracking reads.

The agent should not silently automate:

- final paid order submission;
- address changes;
- payment method selection;
- accepting engineering file changes;
- mass-production quantity changes.

Those steps need explicit confirmation because a small mistake can produce unusable boards or spend money.
