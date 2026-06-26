# Optical Reference Downloader

This note documents the tools and repeatable workflow used to collect Hengyang
Optics and Thorlabs STEP/PDF/image references for fast optical-mechanical design.
The goal is a local, manifest-backed reference library under `cad/references/`
that agents can use before designing holders, cages, adapters, and renders.

## What Was Used

- `rg`, `find`, and shell inspection to locate existing CAD folders and manifests.
- Python standard library `urllib` to download pages, JSON, PDFs, STEP/STP files,
  DXF files, and product images without browser automation.
- Hengyang public pages such as `https://www.hengyangbuy.com/Product3?cid=999`.
- Hengyang category API:
  `https://www.hengyangbuy.com/API/Web/Goods/GetGoodsByCategoryId?cid=<CID>`.
- Thorlabs public product GraphQL endpoint:
  `https://www.thorlabs.com/graphql`.
- Thorlabs product asset URLs returned by GraphQL, especially asset groups
  `Step`, `CAD PDF`, and `CAD DXF`.
- CadQuery in `cad/.conda/cad-python` for optional STEP bounding-box checks.
- `pdflatex` for the compiled quick-design report.

I searched for a reusable GitHub downloader first, but did not find a reliable
current public project that handled Thorlabs' current web app and CAD assets.
The reusable code here therefore uses official vendor public endpoints directly.

## Main Script

Use:

```bash
python3 cad/tools/optical_reference_downloader.py --help
```

Download or refresh all Hengyang reference categories already curated for the
Lumileds cage-holder work:

```bash
python3 cad/tools/optical_reference_downloader.py hengyang
```

Download one Hengyang category, preserving the rest of the manifest:

```bash
python3 cad/tools/optical_reference_downloader.py hengyang \
  --only gkm-010-polarizer-waveplate-holders
```

Download Thorlabs by part number:

```bash
python3 cad/tools/optical_reference_downloader.py thorlabs SM1L10 CP02T \
  --asset-group Step \
  --asset-group "CAD PDF"
```

Download the current common 30 mm cage starter set:

```bash
python3 cad/tools/optical_reference_downloader.py thorlabs \
  --preset common-30mm-cage
```

Generate the design/report PDF:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate /home/lachlan/ProjectsLFS/AgenticApp/cad/.conda/cad-python
python cad/tools/optical_reference_downloader.py report --compile
```

## Outputs

- Hengyang manifest: `cad/references/hengyang-optics/manifest.json`
- Thorlabs manifest: `cad/references/thorlabs-optics/manifest.json`
- Thorlabs downloaded common set: `cad/references/thorlabs-optics/<PART>/`
- TeX report:
  `cad/reports/optical-reference-quick-design/optical_reference_quick_design.tex`
- Compiled PDF:
  `cad/reports/optical-reference-quick-design/optical_reference_quick_design.pdf`

The Thorlabs common preset currently downloads:

```text
C4W, CP02T, ER1, ER2, KCB1, KM100, LCP02, SM1L10
```

Each successful product folder stores `product.json`, a product image, CAD PDF,
CAD DXF, and STEP.

## Agent Workflow

1. Start with `git status --short` and preserve unrelated local edits.
2. Identify vendor, part numbers, and target role: lens holder, cage rod,
   beamsplitter cube, mirror holder, adapter, or custom printable holder.
3. Run the vendor downloader and inspect the manifest for errors.
4. Keep raw vendor files local and immutable; create new derivative designs under
   `cad/designs/` instead of editing vendor references.
5. Use CadQuery/FreeCAD/OpenSCAD/Blender only after the manifest is complete.
6. Regenerate the report PDF after adding a new reference family or design.
7. Verify critical dimensions from vendor PDFs before machining or ordering.

## Copy-Paste Agent Prompt

```text
Use the AgenticApp optical reference downloader.

Repo: /home/lachlan/ProjectsLFS/AgenticApp
Script: cad/tools/optical_reference_downloader.py
Reference folders:
- cad/references/hengyang-optics
- cad/references/thorlabs-optics
Report:
- cad/reports/optical-reference-quick-design/optical_reference_quick_design.pdf

Task:
1. Find exact optical part numbers or category slugs.
2. Download STEP/PDF/DXF/image/product JSON references with the script.
3. Inspect manifest errors and downloaded files.
4. Measure STEP bounds if cad/.conda/cad-python is available.
5. Update or generate the TeX/PDF quick-design report.
6. If designing a holder, create a new independent design under cad/designs/
   and use vendor files only as reference geometry.
```

## Render And Report Check

The downloader itself does not remodel vendor parts; it creates a reliable local
reference library. Use the existing design scripts after the reference set is
complete:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate /home/lachlan/ProjectsLFS/AgenticApp/cad/.conda/cad-python
python cad/designs/lumileds_hengyang_30mm_cage_holder/build_lumileds_hengyang_30mm_cage_holder.py
blender --background --python cad/designs/lumileds_hengyang_30mm_cage_holder/render_lumileds_hengyang_30mm_cage_holder.py
python cad/tools/optical_reference_downloader.py report --compile
```

The report embeds the current Lumileds holder render and dimension sketch so a
future agent can compare the designed device with the downloaded vendor library.

## Design Notes For Quick Optical Layout

- Hengyang GT-090101, HCP, HCM, HKCB1PM, GKM-0102, and HCT parts provide the
  current 30 mm cage and 25.4 mm optic geometry reference set.
- Thorlabs SM1L10, CP02T, ER rods, KCB1, C4W, KM100, and LCP02 provide a second
  vendor reference set for common SM1 and cage-layout decisions.
- The Lumileds cage holder remains an independent design; vendor STEP files are
  references for pitch, envelope, and setup compatibility, not copied geometry.
- STEP bounding boxes in the PDF are fast planning aids only. Use the vendor
  drawing PDF for exact screw, thread, and optical-clearance dimensions.
