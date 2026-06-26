#!/usr/bin/env python3
"""Download optical CAD references and build a quick-design report.

This script keeps vendor files in cad/references/ so optical setup design can
start from local STEP/PDF/image material instead of repeated manual browsing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


CAD_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CAD_ROOT.parent
HENGYANG_ROOT = CAD_ROOT / "references" / "hengyang-optics"
THORLABS_ROOT = CAD_ROOT / "references" / "thorlabs-optics"
REPORT_ROOT = CAD_ROOT / "reports" / "optical-reference-quick-design"

TIMEOUT = 60
USER_AGENT = "AgInTi LabCanvas optical reference downloader"
THORLABS_BASE_URL = "https://www.thorlabs.com"
THORLABS_GRAPHQL_URL = f"{THORLABS_BASE_URL}/graphql"

THORLABS_COMMON_PRESETS = {
    "common-30mm-cage": [
        "SM1L10",
        "CP02T",
        "ER1",
        "ER2",
        "LCP02",
        "KCB1",
        "C4W",
        "KM100",
    ],
    "lens-and-cage-starter": [
        "SM1L10",
        "SM1A9",
        "CP02T",
        "ER1",
        "LCP02",
    ],
}

DEFAULT_ASSET_GROUPS = ["Step", "CAD PDF", "CAD DXF"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    value = value.strip()
    value = value.replace("Ø", "D").replace("φ", "D").replace("∅", "D")
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "download"


def ascii_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback)
    replacements = {
        "Ø": "D",
        "φ": "D",
        "∅": "D",
        "×": "x",
        "≤": "<=",
        "≥": ">=",
        "±": "+/-",
        "°": " deg",
        "³": "^3",
        "μ": "u",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.encode("ascii", errors="ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def latex_escape(value: Any) -> str:
    text = ascii_text(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = TIMEOUT,
) -> tuple[bytes, str]:
    merged_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    if headers:
        merged_headers.update(headers)
    req = Request(url, data=data, headers=merged_headers)
    with urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("content-type", "")


def request_text(url: str, **kwargs: Any) -> tuple[str, str]:
    body, content_type = request(url, **kwargs)
    return body.decode("utf-8", errors="replace"), content_type


def request_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    text, _ = request_text(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": THORLABS_BASE_URL,
            "Referer": THORLABS_BASE_URL + "/",
        },
    )
    return json.loads(text)


def absolute_url(url: str | None, base_url: str) -> str | None:
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(base_url, url)


def extension_from_url(url: str, fallback: str = ".bin") -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix or fallback


def download_file(url: str, path: Path, *, force: bool = False) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return {
            "path": str(path.relative_to(REPO_ROOT)),
            "url": url,
            "bytes": path.stat().st_size,
            "content_type": "existing",
            "skipped": True,
        }
    body, content_type = request(url)
    path.write_bytes(body)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "url": url,
        "bytes": path.stat().st_size,
        "content_type": content_type,
        "skipped": False,
    }


def run_hengyang(args: argparse.Namespace) -> None:
    script = HENGYANG_ROOT / "download_hengyang_references.py"
    if not script.exists():
        raise SystemExit(f"Missing Hengyang downloader: {script}")
    command = [sys.executable, str(script)]
    if args.only:
        for slug in args.only:
            command.extend(["--only", slug])
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def thorlabs_store() -> dict[str, Any]:
    payload = {
        "operationName": "Store",
        "query": """
query Store($domain:String!){
  store(domain:$domain){
    storeId
    catalogId
    storeName
    storeUrl
    defaultLanguage{cultureName twoLetterLanguageName}
    defaultCurrency{code}
    settings{environmentName}
  }
}
""",
        "variables": {"domain": "www.thorlabs.com"},
    }
    result = request_json(THORLABS_GRAPHQL_URL, payload)
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], indent=2))
    return result["data"]["store"]


def thorlabs_search_part(
    part_number: str,
    *,
    store_id: str,
    culture_name: str,
    currency_code: str,
) -> dict[str, Any] | None:
    payload = {
        "operationName": "Products",
        "query": """
query Products($storeId:String!,$userId:String,$cultureName:String,$currencyCode:String,$query:String,$filter:String,$first:Int,$after:String){
  products(storeId:$storeId,userId:$userId,cultureName:$cultureName,currencyCode:$currencyCode,query:$query,filter:$filter,first:$first,after:$after){
    totalCount
    items{
      id
      code
      name
      slug
      imgSrc
      images{url}
      assets{id name group description url optiUrl mimeType size}
      descriptionsWithFallbacksTL{reviewType content}
    }
  }
}
""",
        "variables": {
            "storeId": store_id,
            "userId": "anonymous",
            "cultureName": culture_name,
            "currencyCode": currency_code,
            "query": part_number,
            "filter": f"sku:{part_number}",
            "first": 10,
            "after": "0",
        },
    }
    result = request_json(THORLABS_GRAPHQL_URL, payload)
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], indent=2))
    items = result.get("data", {}).get("products", {}).get("items", []) or []
    for item in items:
        if str(item.get("code", "")).upper() == part_number.upper():
            return item
    return items[0] if items else None


def thorlabs_parts_from_args(args: argparse.Namespace) -> list[str]:
    parts: list[str] = []
    for preset in args.preset or []:
        if preset not in THORLABS_COMMON_PRESETS:
            known = ", ".join(sorted(THORLABS_COMMON_PRESETS))
            raise SystemExit(f"Unknown Thorlabs preset {preset!r}. Known presets: {known}")
        parts.extend(THORLABS_COMMON_PRESETS[preset])
    parts.extend(args.parts or [])
    deduped = []
    seen = set()
    for part in parts:
        key = part.upper()
        if key not in seen:
            deduped.append(key)
            seen.add(key)
    if not deduped:
        raise SystemExit("Provide Thorlabs part numbers or --preset common-30mm-cage")
    return deduped


def selected_thorlabs_assets(
    item: dict[str, Any],
    selected_groups: set[str],
) -> list[dict[str, Any]]:
    assets = item.get("assets") or []
    result = []
    for asset in assets:
        group = str(asset.get("group") or "").strip()
        name = str(asset.get("name") or "").strip()
        if group in selected_groups or name in selected_groups:
            result.append(asset)
    return result


def write_thorlabs_readme(manifest: dict[str, Any], path: Path) -> None:
    lines = [
        "# Thorlabs Optics CAD References",
        "",
        "Downloaded public CAD and drawing files for quick optical setup design.",
        "The downloader uses Thorlabs' current public product GraphQL metadata and stores only local reference copies.",
        "",
        f"Source site: <{THORLABS_BASE_URL}>",
        f"Downloaded at: `{manifest['downloaded_at']}`",
        f"Asset groups: `{', '.join(manifest.get('asset_groups', []))}`",
        "",
        "## Products",
        "",
    ]
    for product in manifest.get("products", []):
        downloads = product.get("downloads", [])
        lines.append(f"### {product.get('code')} - {product.get('name')}")
        lines.append("")
        lines.append(f"- Page: <{product.get('page')}>")
        lines.append(f"- Folder: `{product.get('folder')}/`")
        lines.append(f"- Downloaded files: {len([d for d in downloads if d.get('path')])}")
        for download in downloads:
            if "path" not in download:
                lines.append(f"  - {download.get('kind', 'file')}: ERROR {download.get('error')}")
                continue
            status = "existing" if download.get("skipped") else "downloaded"
            lines.append(f"  - `{download['path']}` ({download.get('kind')}, {status}, {download.get('bytes')} bytes)")
        lines.append("")
    if manifest.get("errors"):
        lines += ["## Errors", ""]
        for error in manifest["errors"]:
            lines.append(f"- `{error.get('part')}`: {error.get('error')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_thorlabs(args: argparse.Namespace) -> None:
    THORLABS_ROOT.mkdir(parents=True, exist_ok=True)
    asset_groups = args.asset_group or DEFAULT_ASSET_GROUPS
    selected_groups = set(asset_groups)
    parts = thorlabs_parts_from_args(args)
    manifest_path = THORLABS_ROOT / "manifest.json"
    previous_products: dict[str, dict[str, Any]] = {}
    if manifest_path.exists() and not args.fresh_manifest:
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            previous_products = {
                str(product.get("code", "")).upper(): product
                for product in old_manifest.get("products", [])
                if product.get("code")
            }
        except json.JSONDecodeError:
            previous_products = {}

    store = thorlabs_store()
    language = store.get("defaultLanguage", {}).get("cultureName") or "en-US"
    currency = store.get("defaultCurrency", {}).get("code") or "USD"
    products: dict[str, dict[str, Any]] = dict(previous_products)
    errors: list[dict[str, str]] = []

    for part in parts:
        try:
            item = thorlabs_search_part(
                part,
                store_id=store["storeId"],
                culture_name=language,
                currency_code=currency,
            )
            if not item:
                raise RuntimeError("No product returned from Thorlabs search")
            code = str(item.get("code") or part).upper()
            product_dir = THORLABS_ROOT / safe_name(code)
            product_dir.mkdir(parents=True, exist_ok=True)
            (product_dir / "product.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            downloads: list[dict[str, Any]] = [
                {
                    "kind": "product-json",
                    "path": str((product_dir / "product.json").relative_to(REPO_ROOT)),
                    "bytes": (product_dir / "product.json").stat().st_size,
                }
            ]

            img_url = absolute_url(item.get("imgSrc"), THORLABS_BASE_URL)
            if args.include_images and img_url:
                image_target = product_dir / f"{safe_name(code)}_product-image{extension_from_url(img_url, '.jpg')}"
                try:
                    info = download_file(img_url, image_target, force=args.force)
                    info["kind"] = "product-image"
                    downloads.append(info)
                except (HTTPError, URLError, TimeoutError, OSError) as exc:
                    downloads.append({"kind": "product-image", "url": img_url, "error": str(exc)})

            for asset in selected_thorlabs_assets(item, selected_groups):
                asset_url = absolute_url(asset.get("optiUrl") or asset.get("url"), THORLABS_BASE_URL)
                if not asset_url:
                    continue
                group_name = safe_name(str(asset.get("group") or "asset"))
                raw_asset_name = str(asset.get("name") or asset.get("id") or "asset")
                asset_path = Path(urlparse(raw_asset_name).path)
                asset_name = safe_name(asset_path.stem or raw_asset_name)
                ext = asset_path.suffix or extension_from_url(asset_url, ".bin")
                target = product_dir / f"{safe_name(code)}_{group_name}_{asset_name}{ext}"
                try:
                    info = download_file(asset_url, target, force=args.force)
                    info["kind"] = str(asset.get("group") or asset.get("name") or "asset")
                    info["asset_id"] = asset.get("id")
                    downloads.append(info)
                except (HTTPError, URLError, TimeoutError, OSError) as exc:
                    downloads.append({"kind": str(asset.get("group") or "asset"), "url": asset_url, "error": str(exc)})

            if args.support_zip:
                zip_url = f"{THORLABS_BASE_URL}/api/thorlabs-products/support-documents-zip/{quote(str(item['id']))}"
                zip_target = product_dir / f"{safe_name(code)}_support-documents.zip"
                try:
                    info = download_file(zip_url, zip_target, force=args.force)
                    info["kind"] = "support-documents-zip"
                    downloads.append(info)
                except (HTTPError, URLError, TimeoutError, OSError) as exc:
                    downloads.append({"kind": "support-documents-zip", "url": zip_url, "error": str(exc)})

            products[code] = {
                "code": code,
                "id": item.get("id"),
                "name": item.get("name"),
                "slug": item.get("slug"),
                "page": f"{THORLABS_BASE_URL}/thorproduct.cfm?partnumber={quote(code)}",
                "folder": str(product_dir.relative_to(THORLABS_ROOT)),
                "downloads": downloads,
                "assets": item.get("assets") or [],
            }
        except Exception as exc:  # Keep a manifest of failures for future runs.
            errors.append({"part": part, "error": str(exc)})

    manifest = {
        "source": THORLABS_BASE_URL,
        "graphql_endpoint": THORLABS_GRAPHQL_URL,
        "downloaded_at": utc_now(),
        "store": store,
        "asset_groups": asset_groups,
        "products": [products[key] for key in sorted(products)],
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_thorlabs_readme(manifest, THORLABS_ROOT / "README.md")
    print(manifest_path)


def try_step_bounds(path: Path) -> dict[str, float] | None:
    try:
        import cadquery as cq  # type: ignore

        obj = cq.importers.importStep(str(path))
        shape = obj.val()
        box = shape.BoundingBox()
        return {
            "x_mm": round(float(box.xlen), 3),
            "y_mm": round(float(box.ylen), 3),
            "z_mm": round(float(box.zlen), 3),
        }
    except Exception:
        return None


def collect_step_files(root: Path, limit: int = 18) -> list[Path]:
    if not root.exists():
        return []
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".step", ".stp"}
    ]
    return sorted(paths)[:limit]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def count_download_kinds(downloads: list[dict[str, Any]]) -> str:
    kinds = {}
    for item in downloads:
        if "path" not in item:
            continue
        kind = str(item.get("kind") or "file")
        kinds[kind] = kinds.get(kind, 0) + 1
    return ", ".join(f"{key}:{value}" for key, value in sorted(kinds.items())) or "-"


def write_report_tex(args: argparse.Namespace) -> Path:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    tex_path = REPORT_ROOT / "optical_reference_quick_design.tex"
    hengyang_manifest = load_json(HENGYANG_ROOT / "manifest.json")
    thorlabs_manifest = load_json(THORLABS_ROOT / "manifest.json")
    holder_manifest = load_json(
        CAD_ROOT
        / "designs"
        / "lumileds_hengyang_30mm_cage_holder"
        / "artifacts"
        / "manifest.json"
    )

    holder_params = holder_manifest.get("parameters", {})
    holder_outputs = holder_manifest.get("outputs", {})
    render_rel = (
        "../../designs/lumileds_hengyang_30mm_cage_holder/artifacts/"
        "lumileds_hengyang_30mm_cage_holder_render.png"
    )
    sketch_rel = (
        "../../designs/lumileds_hengyang_30mm_cage_holder/artifacts/"
        "lumileds_hengyang_30mm_cage_holder_dimension_sketch.png"
    )

    selected_params = [
        "body_width_mm",
        "body_height_mm",
        "body_thickness_mm",
        "cage_rod_pitch_mm",
        "cage_rod_clearance_diameter_mm",
        "rod_boss_diameter_mm",
        "light_aperture_diameter_mm",
        "pcb_outer_diameter_mm",
        "pcb_pocket_diameter_mm",
        "pcb_pocket_depth_mm",
        "pcb_thickness_mm",
        "pcb_mount_pattern_mm",
        "pcb_mount_hole_diameter_mm",
        "bottom_post_mount_hole_diameter_mm",
    ]

    hengyang_rows = []
    for category in hengyang_manifest.get("categories", []):
        for item in category.get("items", [])[:6]:
            model = item.get("model") or "-"
            downloads = item.get("downloads", [])
            hengyang_rows.append(
                (
                    model,
                    category.get("slug", "-"),
                    count_download_kinds(downloads),
                )
            )

    thorlabs_rows = []
    for product in thorlabs_manifest.get("products", []):
        thorlabs_rows.append(
            (
                product.get("code", "-"),
                product.get("name", "-"),
                count_download_kinds(product.get("downloads", [])),
            )
        )

    bounds_rows = []
    for root in [HENGYANG_ROOT, THORLABS_ROOT]:
        for step_path in collect_step_files(root, limit=10):
            bounds = try_step_bounds(step_path) if args.measure_steps else None
            if not bounds:
                continue
            bounds_rows.append((step_path.relative_to(REPO_ROOT), bounds))

    lines = [
        r"\documentclass[10pt]{article}",
        r"\usepackage[margin=0.7in]{geometry}",
        r"\usepackage{graphicx}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{hyperref}",
        r"\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{6pt}",
        r"\begin{document}",
        r"\title{Optical Reference Downloader and Lumileds Cage Holder Report}",
        rf"\date{{Generated {latex_escape(utc_now())}}}",
        r"\maketitle",
        r"\section{Purpose}",
        (
            "This report documents the reusable downloader workflow and the "
            "current quick-design reference set for a Lumileds PCB holder that "
            "shares 30 mm cage geometry with Hengyang and Thorlabs optical parts."
        ),
        r"\section{Reusable Downloader}",
        r"\begin{verbatim}",
        "python3 cad/tools/optical_reference_downloader.py hengyang",
        "python3 cad/tools/optical_reference_downloader.py hengyang --only gkm-010-polarizer-waveplate-holders",
        "python3 cad/tools/optical_reference_downloader.py thorlabs --preset common-30mm-cage",
        "python3 cad/tools/optical_reference_downloader.py thorlabs SM1L10 CP02T --asset-group Step --asset-group \"CAD PDF\"",
        "python3 cad/tools/optical_reference_downloader.py report --compile",
        r"\end{verbatim}",
        r"\section{Lumileds Holder Geometry}",
        r"\begin{longtable}{p{0.47\linewidth}p{0.38\linewidth}}",
        r"\textbf{Parameter} & \textbf{Value} \\ \hline",
    ]
    for key in selected_params:
        value = holder_params.get(key, "-")
        lines.append(f"{latex_escape(key)} & {latex_escape(value)} \\\\")
    lines += [
        r"\end{longtable}",
        r"Reference family: " + latex_escape(holder_params.get("reference_family", "-")) + r"\\",
        r"Primary reference: " + latex_escape(holder_params.get("primary_reference", "-")) + r"\\",
        r"Print note: " + latex_escape(holder_params.get("print_clearance_note", "-")),
    ]

    if (REPORT_ROOT / render_rel).resolve().exists():
        lines += [
            r"\begin{figure}[h]",
            r"\centering",
            rf"\includegraphics[width=0.72\linewidth]{{{render_rel}}}",
            r"\caption{Lumileds holder inspection render.}",
            r"\end{figure}",
        ]
    if (REPORT_ROOT / sketch_rel).resolve().exists():
        lines += [
            r"\begin{figure}[h]",
            r"\centering",
            rf"\includegraphics[width=0.72\linewidth]{{{sketch_rel}}}",
            r"\caption{Dimension sketch for the holder.}",
            r"\end{figure}",
        ]

    lines += [
        r"\clearpage",
        r"\section{Hengyang Reference Set}",
        "The Hengyang downloader captures category pages, API JSON, item JSON, drawings, STEP/STP files, and product images.",
        rf"Manifest: \texttt{{{latex_escape(str((HENGYANG_ROOT / 'manifest.json').relative_to(REPO_ROOT)))}}}",
        r"\begin{longtable}{p{0.18\linewidth}p{0.34\linewidth}p{0.36\linewidth}}",
        r"\textbf{Model} & \textbf{Category folder} & \textbf{Local files} \\ \hline",
    ]
    for model, category_slug, downloads in hengyang_rows:
        lines.append(f"{latex_escape(model)} & {latex_escape(category_slug)} & {latex_escape(downloads)} \\\\")
    lines += [
        r"\end{longtable}",
        r"\section{Thorlabs Reference Set}",
        "The Thorlabs downloader queries public product metadata and stores selected CAD assets by part number.",
        rf"Manifest: \texttt{{{latex_escape(str((THORLABS_ROOT / 'manifest.json').relative_to(REPO_ROOT)))}}}",
    ]
    if thorlabs_rows:
        lines += [
            r"\begin{longtable}{p{0.16\linewidth}p{0.42\linewidth}p{0.30\linewidth}}",
            r"\textbf{Part} & \textbf{Name} & \textbf{Local files} \\ \hline",
        ]
        for code, name, downloads in thorlabs_rows:
            lines.append(f"{latex_escape(code)} & {latex_escape(name)} & {latex_escape(downloads)} \\\\")
        lines.append(r"\end{longtable}")
    else:
        lines.append("No Thorlabs manifest has been downloaded yet.")

    lines += [
        r"\section{Measured STEP Bounds}",
        "STEP bounds are approximate imported bounding boxes, useful for fast layout planning before detailed inspection.",
    ]
    if bounds_rows:
        lines += [
            r"\begin{longtable}{p{0.58\linewidth}p{0.10\linewidth}p{0.10\linewidth}p{0.10\linewidth}}",
            r"\textbf{STEP file} & \textbf{X mm} & \textbf{Y mm} & \textbf{Z mm} \\ \hline",
        ]
        for rel_path, bounds in bounds_rows[:24]:
            lines.append(
                f"{latex_escape(rel_path)} & {bounds['x_mm']} & {bounds['y_mm']} & {bounds['z_mm']} \\\\"
            )
        lines.append(r"\end{longtable}")
    else:
        lines.append("CadQuery measurement was not available or no STEP files imported cleanly in this run.")

    lines += [
        r"\section{Agent Contract}",
        r"\begin{enumerate}",
        r"\item Search or identify vendor part numbers, then download vendor material into \texttt{cad/references/}.",
        r"\item Keep raw pages, JSON, drawings, STEP files, images, and manifests together.",
        r"\item Measure STEP bounds when a CAD kernel is available, but verify critical dimensions in vendor drawings.",
        r"\item Use downloaded references only as design constraints. New printable parts should remain independent designs.",
        r"\item Regenerate this PDF after adding reference families or changing the Lumileds holder.",
        r"\end{enumerate}",
        r"\section{Key Local Outputs}",
        r"\begin{verbatim}",
    ]
    for key, value in holder_outputs.items():
        lines.append(f"{key}: {value}")
    lines += [
        r"\end{verbatim}",
        r"\end{document}",
        "",
    ]
    tex_path.write_text("\n".join(lines), encoding="utf-8")
    return tex_path


def run_pdflatex(tex_path: Path) -> None:
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise SystemExit("pdflatex is not installed; TeX file was written but PDF was not compiled.")
    for _ in range(2):
        subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            check=True,
        )


def run_report(args: argparse.Namespace) -> None:
    tex_path = write_report_tex(args)
    if args.compile:
        run_pdflatex(tex_path)
    print(tex_path)
    pdf_path = tex_path.with_suffix(".pdf")
    if pdf_path.exists():
        print(pdf_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    hengyang = subparsers.add_parser("hengyang", help="Run the Hengyang reference downloader")
    hengyang.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="SLUG",
        help="Download only one Hengyang category slug; can be repeated.",
    )
    hengyang.set_defaults(func=run_hengyang)

    thorlabs = subparsers.add_parser("thorlabs", help="Download Thorlabs CAD assets by part number")
    thorlabs.add_argument("parts", nargs="*", help="Thorlabs part numbers, for example SM1L10 CP02T")
    thorlabs.add_argument(
        "--preset",
        action="append",
        choices=sorted(THORLABS_COMMON_PRESETS),
        help="Named part list to download; can be repeated.",
    )
    thorlabs.add_argument(
        "--asset-group",
        action="append",
        help='Asset group/name to download. Defaults to Step, "CAD PDF", and "CAD DXF".',
    )
    thorlabs.add_argument("--support-zip", action="store_true", help="Also download Thorlabs support document ZIPs")
    thorlabs.add_argument("--force", action="store_true", help="Redownload files even when they already exist")
    thorlabs.add_argument(
        "--fresh-manifest",
        action="store_true",
        help="Do not merge with the existing Thorlabs manifest",
    )
    thorlabs.add_argument(
        "--no-images",
        dest="include_images",
        action="store_false",
        help="Skip product image downloads",
    )
    thorlabs.set_defaults(func=run_thorlabs, include_images=True)

    report = subparsers.add_parser("report", help="Generate the TeX/PDF quick-design report")
    report.add_argument("--compile", action="store_true", help="Compile the TeX report to PDF")
    report.add_argument(
        "--no-measure-steps",
        dest="measure_steps",
        action="store_false",
        help="Skip CadQuery STEP bounding-box measurements",
    )
    report.set_defaults(func=run_report, measure_steps=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
