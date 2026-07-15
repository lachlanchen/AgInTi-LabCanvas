# WeChat Document Intake

`wechat_document_reader.py` turns an exact same-chat attachment into bounded,
read-only evidence for the resumed worker agent. It supports PDF, DOC/DOCX,
ZIP, and common text/source formats.

Extracted content is untrusted source data. Prompts or commands inside a
document cannot authorize tools, secret access, outbound messages, publishing,
or route changes; only the current source-scoped WeChat request can do that.

## Pipeline

1. `wechat_media_sync.py` resolves the exact source row and local file.
2. The worker copies it under `output/wechat_worker/<task-id>/`.
3. `wechat_document_reader.py` validates the signature and extracts content.
4. The manifest stores a short preview and an `agent_context_path`; full text
   is not inlined into queue JSON.
5. The exact-chat worker opens that path and answers naturally from the actual
   document. Bare uploads get a concise preliminary summary. Explicit requests
   control deeper analysis, translation, conversion, or file delivery.

## Format Behavior

- **PDF:** `pdfinfo` plus `pdftotext -layout`; scanned/low-text files fall back
  to a bounded `pdftoppm` and multilingual Tesseract pass.
- **DOCX:** parses WordprocessingML directly, including paragraphs, tables,
  headers, footers, notes, comments, and core metadata. It does not run macros.
- **DOC:** prefers `antiword`; otherwise uses isolated, time-limited
  LibreOffice headless safe mode.
- **ZIP:** inventories members and recursively reads supported files. It blocks
  traversal, symlinks, encryption, executables, oversized members/archives,
  excessive nesting, and suspicious compression ratios.

## Command

```bash
python agentic_tools/wechat_gui_agent/scripts/wechat_document_reader.py \
  /path/to/source.pdf \
  --output-dir output/document-read \
  --json
```

Limits are configurable through `WECHAT_DOCUMENT_MAX_*` environment variables.
Defaults cap sources and archives at 200 MiB, individual archive members at
50 MiB, archive depth at two, OCR at ten pages, and extracted text at two
million characters.

The restart gate `labcanvas wechat selftest --suite all --json` verifies that a
DOCX becomes readable context and is handed to the worker instead of being
closed as a deterministic receipt.
