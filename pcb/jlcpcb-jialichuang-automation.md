# JLCPCB / Jialichuang Order Automation Research

Date: 2026-06-09

## Short Answer

Yes, AppAutoAction can support JLCPCB/Jialichuang ordering workflows, but the safe default should be **prepare, validate, upload, quote, and stop before final order/payment** unless the user explicitly confirms the exact order.

There are three practical routes:

1. Official JLCPCB API for approved partners.
2. EasyEDA/Jialichuang EDA order integration for designs authored in EasyEDA.
3. Browser/app-assisted workflow for KiCad-generated Gerber zip uploads.

## Official API Status

JLCPCB now documents an official API platform. The PCB API is described as supporting file upload, automated pricing, PCB order creation, production progress, and order tracking. The same platform also lists stencil, 3D printing, and components APIs.

Access is not open by default. JLCPCB says users must apply, applications are reviewed, and approval depends on factors such as previous orders, company profile, and business situation. API partners must also follow branding restrictions.

Implication for AppAutoAction: add an API adapter, but make it optional and credential-gated. Store API credentials outside git, and keep dry-run mode as the default.

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

Current public MCP-style tools are more useful for component search, BOM validation, KiCad editing, and fabrication package generation than for final paid order submission.

Relevant options:

- `jlcmcp.dev`: independent JLCPCB component search MCP, BOM export, stock/pricing checks. It states it is not affiliated with JLCPCB.
- `mixelpixx/KiCAD-MCP-Server`: KiCad MCP server with JLCPCB parts catalog and Freerouting integration.
- `asukiaaa/gerber_to_order`: KiCad plugin to generate Gerber zip packages for vendors including JLCPCB.

Sources:

- https://jlcmcp.dev/
- https://github.com/mixelpixx/KiCAD-MCP-Server
- https://github.com/asukiaaa/gerber_to_order

## Recommended AppAutoAction Workflow

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
