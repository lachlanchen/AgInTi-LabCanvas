# Nature.shapr Workspace Probe

Source: `/home/lachlan/Downloads/Nature.shapr`

## Summary

- Container: `.shapr` ZIP with `workspace` SQLite database.
- Tables with rows: `24`.
- History operation nodes: `12`.
- Imports: `3`; transforms: `5`; sketches: `2`; extrudes: `2`.
- Imported Parasolid body blobs: `77`.
- The native history here is mainly imported STEP assemblies plus transforms; it is not a full editable Shapr feature tree for the OpenHI 4f parts.

## Public Tooling Check

- `looking-glass-station/Shapr3d_backup`: useful reference for locating and packaging Shapr3D local projects as `.shapr`; it does not decode native body/history geometry.
- `DleBlancNT/shapr-backup`: another local-project backup/export utility; it also preserves `.shapr` packages rather than converting workspace internals.
- `tinyprocessing/Shapr3DConverter`: sample iOS conversion project with `.shapr` fixtures, but not a usable native geometry decoder for this task.
- `Alfredoalv13/shapr3d-mcp`: relevant direction for AI-driven CAD through build123d/STEP exchange, not direct `.shapr` feature editing.
- Conclusion: use this probe for SQLite/history/body extraction, and use exported STEP/Parasolid conversion for geometry work.
- The script uses `msgpack` when available to decode Shapr history properties; without it, table/body summaries still work but operation details are sparse.

## Operation Tree

| Node | Title | Operation | Bodies | Positions |
| ---: | --- | --- | --- | --- |
| 11180 | `Sketch 01` | `MaterializeSketchPlane` |  |  |
| 11245 | `Extrusion 01` | `Extrude` |  |  |
| 11370 | `Sketch 02` | `MaterializeSketchPlane` |  |  |
| 11485 | `Extrusion 02` | `Extrude` |  |  |
| 1016921 | `Import "Microscope yx umot large.step"` | `MaterializeImportedBodies` | 182, 184, 185, 183, 191, 192, 186, 187, 189, 190, 188, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204 |  |
| 1016924 | `Movement/Rotation 01` | `Transform` |  | [0.15, 0, 0.12] |
| 1017493 | `Import "42 stepper FH PLP.step"` | `MaterializeImportedBodies` | 205, 209, 211, 207, 210, 214, 208, 212, 213, 206, 216, 215, 226, 217, 225, 219, 218, 220, 221, 223, 222, 224, 227, 228, ... |  |
| 1017496 | `Movement/Rotation 02` | `Transform` |  | [0.2, 0.06, 0.07] |
| 1018058 | `Movement/Rotation 03` | `Transform` |  | [0, 0.09, 0.04] |
| 1018368 | `Import "BS lateral.step"` | `MaterializeImportedBodies` | 238, 239, 241, 240, 248, 249, 242, 243, 245, 244, 246, 247, 250, 251, 252, 253, 254, 255, 256, 257, 258 |  |
| 1018371 | `Movement/Rotation 04` | `Transform` |  | [0.2, 0.165, 0.6] |
| 1018710 | `Movement/Rotation 05` | `Transform` |  | [0.03, 0.02, 0] |

## Row Counts

| Table | Rows |
| --- | ---: |
| `BodyRevisionPartitions` | 243 |
| `ConstraintPointProperties` | 2 |
| `Constraints` | 2 |
| `ConstructionSketches` | 2 |
| `HistoryFolders` | 47 |
| `HistoryImportedBodies` | 77 |
| `HistoryManagedSketchCurves` | 2 |
| `HistoryManagedSketchPoints` | 1 |
| `HistoryNameAnchoringPoints` | 2652 |
| `HistoryNames` | 42454 |
| `HistorySketchDescriptorOrder` | 2 |
| `HistorySketchPointCoincidences` | 2 |
| `HistoryTreeNodes` | 82 |
| `MaterialInstances` | 18 |
| `MaterializedCurveNameToCurveID` | 2 |
| `Metadata` | 1615 |
| `MetadataAssignments` | 2807 |
| `PersistedCalls` | 23 |
| `Settings` | 19 |
| `SketchControllers` | 2 |
| `SketchCurves` | 227 |
| `StandaloneConstraintPoints` | 1 |
| `Symbols` | 1 |
| `VisualEnvironmentInstances` | 2 |

## Largest Imported Bodies

| Body ID | Bytes | Header clue |
| ---: | ---: | --- |
| 239 | 1247623 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 188 | 1077704 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 218 | 978102 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 257 | 551740 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 205 | 390520 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 246 | 365048 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 242 | 317967 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 248 | 315663 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 245 | 288871 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 251 | 255395 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 183 | 220909 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 253 | 218246 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 207 | 199945 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 234 | 191564 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 212 | 190160 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 252 | 158020 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 247 | 152099 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 241 | 133387 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 243 | 84012 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |
| 214 | 67152 | `PS...3: TRANSMIT FILE created by modeller version 3700173....SCH_3700173_36001_13006........$CCC` |

## Interpretation For 4f Redesign

- Use `Nature.shapr` to recover assembly intent, imported body IDs, transforms, and Parasolid payloads.
- Use the already-exported STEP files under `cad/extracted/OpenHI_STEP/` for direct geometric measurement of A/B/C/lens-holder thread axes.
- To change only the larger female receiver from the loose old `30.4 mm` fit toward `30.0 mm`, the safest route is a new derived CAD reconstruction that preserves measured body envelopes and rebuilds only the local female-thread socket.
- A native Shapr feature edit is possible only if you provide the original file where that specific holder was modeled with editable sketches/features, not only imported STEP bodies.
