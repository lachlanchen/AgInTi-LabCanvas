# Protein Structure Agent

This integration delegates AlphaFold Server work to the existing
`external/ProteinStructure/scripts/alphafold_server/` implementation. LabCanvas
does not duplicate submission, polling, download, metrics, render, or screenshot
logic.

The browser stack reuses the persistent login profile at
`~/.cache/alphafold-server-chrome` and exposes the dedicated desktop at:

```text
http://127.0.0.1:6187/vnc.html?host=127.0.0.1&port=6187&autoconnect=1&resize=scale
```

Source code comes from the `external/ProteinStructure` submodule. Generated
artifacts are written to the sibling workspace `../ProteinStructure`, where
AlphaFold downloads and publication renders remain local and ignored by Git.

Use `PYTHONPATH=src python -m agenticapp protein --help` for the supported thin
CLI wrappers.
