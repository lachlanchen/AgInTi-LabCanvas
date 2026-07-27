# Editable Presentation Pipeline

LabCanvas presentations are manifest-driven PowerPoint files. The source of
truth is `presentation.json`, not a set of rendered slide screenshots.

## Commands

```bash
PYTHONPATH=src python -m agenticapp presentation init \
  "Research roadmap" \
  --objective "Explain the evidence and recommend the next experiment" \
  --output-dir output/presentations/research-roadmap \
  --json

PYTHONPATH=src python -m agenticapp presentation validate \
  output/presentations/research-roadmap/presentation.json \
  --json

PYTHONPATH=src python -m agenticapp presentation build \
  output/presentations/research-roadmap/presentation.json \
  --render \
  --json
```

`build --render` creates an editable `.pptx`, a PDF, per-slide PNG previews
when `pdftoppm` is installed, and `presentation-build.json`.

## Interaction

Start the deck immediately with a sensible bright scientific theme when style
is unspecified. Send one short progress message:

> I have started the deck with a bright scientific theme. You can send the
> audience, color, style, logo, examples, or additional content while I work.

Do not repeatedly ask for confirmation. Ask one concise question only when an
unknown audience, language, confidentiality requirement, or another missing
fact materially changes the deck and cannot be inferred safely. Treat new
same-chat messages as interruptions to the same persistent presentation task.

## Image Generation

Image generation is optional material production, not slide production.

Allowed:

- a supporting illustration;
- a photo-like concept asset;
- an icon or texture;
- one bounded visual panel;
- text inside an asset when genuinely useful and manually reviewed.

Forbidden:

- a generated complete slide;
- a generated slide background containing the composition;
- a screenshot-like bitmap containing all slide text;
- generated figures used as evidence without provenance or verification.

Every generated asset records:

```json
{
  "path": "assets/mechanism.png",
  "role": "supporting_visual",
  "box": {"x": 7.65, "y": 1.45, "w": 4.9, "h": 4.85},
  "provenance": {
    "kind": "image_generation",
    "prompt_path": "assets/mechanism.prompt.md",
    "contains_text": false,
    "text_transcript": "",
    "text_reviewed": false
  }
}
```

If `contains_text` is true, `text_transcript` is required and
`text_reviewed` must be true. Essential titles, claims, labels, citations, and
body text still remain native editable slide text.

## Validation

The validator checks:

- supported layouts and unique slide IDs;
- readable source asset paths;
- bounded generated-image coverage;
- no generated full-slide/background roles;
- preserved prompts for generated assets;
- reviewed transcripts for generated bitmap text;
- readable PPTX ZIP structure and exact slide count;
- optional LibreOffice PDF/PNG rendering.

For substantive research, narrative structure, and visual synthesis, the
presentation routine uses `gpt-5.6-sol` with `xhigh` reasoning. Narrow edits,
rebuilds, and exports may use lower effort.
