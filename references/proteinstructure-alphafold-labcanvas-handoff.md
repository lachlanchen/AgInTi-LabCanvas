# ProteinStructure AlphaFold LabCanvas Handoff

LabCanvas reuses the existing `ProteinStructure` repository instead of
reimplementing its AlphaFold Server automation. Reusable code and scientific
inputs are pinned as the `external/ProteinStructure` submodule. Runtime work is
written to the sibling `/home/lachlan/ProjectsLFS/ProteinStructure` workspace so
current projects and downloaded artifacts remain available locally.

## Start and Inspect

```bash
PYTHONPATH=src python -m agenticapp protein start --json
PYTHONPATH=src python -m agenticapp protein status --json
PYTHONPATH=src python -m agenticapp protein screenshot
```

The stack uses a persistent Chrome profile at
`~/.cache/alphafold-server-chrome`, CDP `http://127.0.0.1:9222`, and localhost
noVNC at `http://127.0.0.1:6187/vnc.html?host=127.0.0.1&port=6187&autoconnect=1&resize=scale`.
This preserves the existing AlphaFold login and keeps browser control visible.

## Run the Existing Pipeline

Use `labcanvas protein submit`, `submit-json`, or `submit-mixed` for validated
job input; `poll --download --all-pages` for completed result bundles;
`metrics --detailed` for confidence/interface tables; `render all` for local
plots and backbone views; and `capture` for result-page evidence. These commands
delegate to `external/ProteinStructure/scripts/alphafold_server/` with the
sibling workspace as their working directory.

## Git and Evidence Contract

Git tracks scripts, runbooks, FASTA/JSON inputs, compact metrics, TeX/Markdown
sources, and reference PDB files. It ignores AlphaFold downloads, generated
figures, compiled PDFs, screenshots, copied full result payloads, build output,
and runtime logs. `git rm --cached` is used for cleanup, so ignored artifacts
remain on the machine.

For inhibitor research, report four layers separately: predicted structure,
confidence/limitations, literature or database evidence, and docking/design
hypotheses. Do not call a predicted pose a validated inhibitor. Nontrivial chat
tasks use the persistent per-chat worker with `gpt-5.6-sol` Ultra and return
models, plots, metrics, screenshots, and reports to the originating chat.
