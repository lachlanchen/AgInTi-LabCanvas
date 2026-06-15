# Reusable Board and CAD Tasks

LabCanvas exposes PCB and CAD generation through one shared backend used by both
the CLI and the web studio. The goal is to make repeatable design tasks usable
from chat without hiding the source files, commands, or manufacturing guardrails.

## What It Discovers

- PCB workflows from `pcb/*/jlcpcb_order/order-settings.json`.
- KiCad generators such as `pcb/lumileds-no-resistor/generate_lumileds_no_resistor_board.py`.
- Board previews, STEP files, Gerber ZIPs, ERC/DRC reports, and JLC preflight manifests.
- CAD workflows from `cad/designs/*`, including OpenSCAD, STEP/STL, support drawings, and Blender renders.

Current high-signal examples are:

- `pcb/lumileds-no-resistor` for a no-resistor Lumileds board.
- `pcb/hybec-hbl-273-g4` for the two-pin halogen lamp board.
- `cad/designs/cmount_threaded_reflector_assembly` for the threaded C-mount reflector holder.

## CLI Usage

Plan from a prompt and register artifacts:

```bash
PYTHONPATH=src python -m agenticapp studio lab-task \
  "prepare Lumileds no-resistor PCB and C-mount reflector CAD" \
  --storage-dir output/webapp
```

Run safe default local steps, such as deterministic generation and JLC preflight
package/validate:

```bash
PYTHONPATH=src python -m agenticapp studio lab-task \
  "prepare Lumileds no-resistor PCB" --mode pcb --execute
```

`--execute` does not submit orders. JLC submission remains guarded by
`agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py` and requires
that script's explicit `--allow-submit` path.

## Web Studio Usage

Start the app:

```bash
PYTHONPATH=src python -m agenticapp web --port 19473
```

In chat, ask for a concrete board/CAD task, for example:

```text
Prepare the Lumileds no-resistor PCB and C-mount reflector CAD task
```

The canvas receives a Markdown plan, JSON manifest, and copied preview/source
artifacts. The Board/CAD button runs the same endpoint, `/api/lab-task`.

## Guardrails

- Web chat is plan-only by default.
- Private shipping, account, phone, token, and browser-session data stays in
  local ignored config files.
- Manufacturing upload/submit steps are visible in the plan but marked manual
  unless a dedicated order script is called explicitly.
