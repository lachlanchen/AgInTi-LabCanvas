# Auto Order System Runbook

This runbook documents the exact system used for the HYBEC HBL-273/HBL-667 G4 bare-PCB JLC order.

## Scope

The system prepares a manufacturable KiCad board package, uploads the Gerber ZIP to JLC/JiaLiChuang, fills prototype settings, and stops at JLC's final order-check/payment boundary.

It is not a blind payment bot. Final submission requires explicit `--allow-submit`, a complete address/contact, and no visible payment/wallet blocker.

## PCB Inputs

- KiCad board: `pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb`.
- Gerber ZIP: `pcb/hybec-hbl-273-g4/jlcpcb_order/hybec-hbl-273-g4-jlcpcb-gerber.zip`.
- Preflight manifest: `pcb/hybec-hbl-273-g4/jlcpcb_order/preflight-manifest.json`.
- Order settings: `pcb/hybec-hbl-273-g4/jlcpcb_order/order-settings.json`.
- DRC/ERC: `pcb/hybec-hbl-273-g4/artifacts/drc.json`, `erc.json`.
- Renders: `pcb/hybec-hbl-273-g4/artifacts/hybec-hbl-273-g4-render*.png`.

## Browser Architecture

The stable route uses a normal Chrome profile with CDP enabled:

```bash
JLCPCB_CDP_PORT=49237 \
JLCPCB_CHROME_PROFILE=~/.cache/jlcpcb-order-shared \
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
```

The Python driver attaches with `playwright.chromium.connect_over_cdp("http://127.0.0.1:49237")`.

This avoids the earlier one-off Playwright persistent-context path that triggered Chrome's unsupported/no-sandbox banner.

## Live Order Steps

1. Uploaded the HYBEC Gerber ZIP on the China site.
2. Opened the parsed order form from the uploaded-file history.
3. Dismissed JLC onboarding overlays and the material selector.
4. Filled settings:
   - FR-4, 2 layers.
   - `2.4 cm x 2.4 cm`.
   - quantity `5`.
   - 1.6 mm, 1 oz, green mask, white silkscreen.
   - lead-free HASL: `无铅喷锡`.
   - normal compensation: `按标准合同常规处理`.
   - no SMT and no stencil.
5. Ran `检查订单`.
6. Filled address region/detail:
   - `广东省 / 深圳市 / 南山区 / 西丽街道`.
   - detail line from the private address.

Remaining live blocker: JLC requires recipient name and mobile phone before the address can be saved and the order can be submitted.

## Safety Rules

- Keep `~/.config/jlcpcb-order/private.json` mode `600`.
- Do not commit recipient, phone, address, cookies, screenshots containing personal details, or tokens.
- Do not click payment, recharge, wallet, or final submit controls without explicit user confirmation.
- For first prototypes, keep quantity low and inspect Gerber preview manually.
- Treat JLC option labels as unstable UI text; verify screenshots after automation.

## Fallback Tools

- JLC assistant: `/opt/jlc-assistant/jlc-assistant`.
- `xdotool`: click stubborn visible controls when selectors are blocked by overlays.
- ImageMagick `import`: capture visible desktop screenshots for manual verification.
