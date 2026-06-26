#!/usr/bin/env python3
"""Download Hengyang Optics reference drawings/models for 30 mm cage work."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
BASE_URL = "https://www.hengyangbuy.com"
TIMEOUT = 40
USER_AGENT = "LabCanvas reference downloader"


CATEGORIES = [
    {
        "slug": "gt-090101-waveplate-polarizer",
        "label": "GT-090101 rotating waveplate/polarizer holder",
        "page_cid": 790,
        "api_cids": [1042],
        "reason": "Primary 30 mm cage geometry reference requested by the user.",
    },
    {
        "slug": "hcp-22-23-24-lens-cage-plates",
        "label": "HCP-22/HCP23/HCP24 1 inch lens cage plates",
        "page_cid": 869,
        "api_cids": [869],
        "reason": "Simple 30 mm cage lens holder references for Ø25.4 mm optics.",
    },
    {
        "slug": "hcp-08-quick-lens-holders",
        "label": "HCP-08 quick install lens holders",
        "page_cid": 873,
        "api_cids": [873],
        "reason": "Quick removable Ø25.4 mm optic holder references.",
    },
    {
        "slug": "gt-0803-precision-lens-holders",
        "label": "GT-0803 precision 1 inch lens holders",
        "page_cid": 878,
        "api_cids": [912, 913],
        "reason": "Precision adjustable Ø25.4 mm cage holder references.",
    },
    {
        "slug": "hcm-3-beam-splitter-cube",
        "label": "HCM-3 beam splitter cube holders",
        "page_cid": 879,
        "api_cids": [914, 1036],
        "reason": "Beam splitter cube and adapter references.",
    },
    {
        "slug": "hcm-3-flat-optic-45deg",
        "label": "HCM-3 45 degree flat optic holders",
        "page_cid": 880,
        "api_cids": [915, 916, 917, 918],
        "reason": "45 degree round/rectangular beam splitter or mirror holder references.",
    },
    {
        "slug": "hkcb1pm-right-angle-mirror-holder",
        "label": "HKCB1PM right-angle mirror holder",
        "page_cid": 1035,
        "api_cids": [1035],
        "reason": "Triangle/right-angle cage mirror holder reference.",
    },
    {
        "slug": "gkm-010-polarizer-waveplate-holders",
        "label": "GKM-010 circular thin polarizer/waveplate holders",
        "page_cid": 999,
        "api_cids": [999],
        "reason": "GKM-0102 Ø25.4 mm polarizer/waveplate holder requested for future optomechanical references.",
    },
    {
        "slug": "hct-6mm-cage-rods",
        "label": "HCT 6 mm 30 mm cage rods",
        "page_cid": 837,
        "api_cids": [837],
        "reason": "Shared metal rod interface for 30 mm cage assemblies.",
    },
]


def safe_name(value: str) -> str:
    value = value.strip().replace("Ø", "D").replace("φ", "D")
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "download"


def absolute_url(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith(("http://", "https://")) else urljoin(BASE_URL, url)


def extension_from_url(url: str, fallback: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix else fallback


def fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read(), response.headers.get("content-type", "")


def fetch_text(url: str) -> tuple[str, str]:
    body, content_type = fetch(url)
    return body.decode("utf-8", errors="replace"), content_type


def clean_snapshot_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def get_json(cid: int) -> list[dict[str, Any]]:
    query = urlencode({"cid": cid})
    text, _ = fetch_text(f"{BASE_URL}/API/Web/Goods/GetGoodsByCategoryId?{query}")
    payload = json.loads(text)
    if not payload.get("success"):
        raise RuntimeError(f"API cid={cid} failed: {payload!r}")
    return payload.get("data") or []


def download(url: str, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    body, content_type = fetch(url)
    path.write_bytes(body)
    return {
        "path": str(path.relative_to(ROOT)),
        "url": url,
        "bytes": path.stat().st_size,
        "content_type": content_type,
    }


def item_parameters(item: dict[str, Any]) -> list[dict[str, str]]:
    params = item.get("AllParameterList") or []
    result = []
    for param in params:
        key = str(param.get("key") or param.get("Name") or "").strip()
        value = str(param.get("value") or param.get("Value") or "").strip()
        unit = str(param.get("Unit") or param.get("unit") or "").strip()
        if key or value:
            result.append({"key": key, "value": value, "unit": unit})
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="SLUG",
        help="Download only the named category slug and merge it into the existing manifest.",
    )
    return parser.parse_args()


def ordered_categories(categories_by_slug: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = []
    seen = set()
    for category in CATEGORIES:
        slug = category["slug"]
        if slug in categories_by_slug:
            ordered.append(categories_by_slug[slug])
            seen.add(slug)
    ordered.extend(value for slug, value in categories_by_slug.items() if slug not in seen)
    return ordered


def main() -> None:
    args = parse_args()
    only = set(args.only)
    known_slugs = {category["slug"] for category in CATEGORIES}
    unknown = sorted(only - known_slugs)
    if unknown:
        raise SystemExit(f"Unknown category slug(s): {', '.join(unknown)}")

    manifest_path = ROOT / "manifest.json"
    if only and manifest_path.exists():
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["downloaded_at"] = datetime.now(timezone.utc).isoformat()
        categories_by_slug = {category["slug"]: category for category in manifest.get("categories", [])}
    else:
        manifest = {
            "source": BASE_URL,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "categories": [],
        }
        categories_by_slug = {}

    categories_to_download = [category for category in CATEGORIES if not only or category["slug"] in only]
    for category in categories_to_download:
        category_dir = ROOT / category["slug"]
        category_dir.mkdir(parents=True, exist_ok=True)
        category_record: dict[str, Any] = {
            "slug": category["slug"],
            "label": category["label"],
            "reason": category["reason"],
            "page": f"{BASE_URL}/Product3?cid={category['page_cid']}",
            "api_cids": category["api_cids"],
            "files": [],
            "items": [],
        }

        page_url = f"{BASE_URL}/Product3?cid={category['page_cid']}"
        page_text, page_content_type = fetch_text(page_url)
        page_path = category_dir / f"Product3-cid-{category['page_cid']}.html"
        page_path.write_text(clean_snapshot_text(page_text), encoding="utf-8")
        category_record["files"].append(
            {
                "path": str(page_path.relative_to(ROOT)),
                "url": page_url,
                "bytes": page_path.stat().st_size,
                "content_type": page_content_type,
            }
        )

        all_items: list[dict[str, Any]] = []
        for api_cid in category["api_cids"]:
            items = get_json(api_cid)
            all_items.extend(items)
            api_path = category_dir / f"api-cid-{api_cid}.json"
            api_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            category_record["files"].append(
                {
                    "path": str(api_path.relative_to(ROOT)),
                    "url": f"{BASE_URL}/API/Web/Goods/GetGoodsByCategoryId?cid={api_cid}",
                    "bytes": api_path.stat().st_size,
                    "content_type": "application/json",
                }
            )

        for item in all_items:
            model = safe_name(str(item.get("Model") or item.get("Name") or item.get("Id")))
            item_dir = category_dir / model
            item_dir.mkdir(parents=True, exist_ok=True)
            item_record: dict[str, Any] = {
                "model": item.get("Model"),
                "name": item.get("Name"),
                "id": item.get("Id"),
                "price_cny": item.get("Price"),
                "category_id": item.get("CategoryId"),
                "parameters": item_parameters(item),
                "downloads": [],
            }
            item_path = item_dir / "item.json"
            item_path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            item_record["downloads"].append(
                {
                    "kind": "item-json",
                    "path": str(item_path.relative_to(ROOT)),
                    "bytes": item_path.stat().st_size,
                }
            )

            for field, fallback_ext, kind in [
                ("PdfUrl", ".pdf", "drawing-pdf"),
                ("STPUrl", ".stp", "model-stp"),
                ("StepUrl", ".step", "model-step"),
                ("ImageUrl", ".jpg", "product-image"),
            ]:
                url = absolute_url(item.get(field))
                if not url:
                    continue
                ext = extension_from_url(url, fallback_ext)
                target = item_dir / f"{model}_{kind}{ext}"
                try:
                    info = download(url, target)
                except Exception as exc:  # Keep going; manifest should show gaps.
                    item_record["downloads"].append({"kind": kind, "url": url, "error": str(exc)})
                    continue
                info["kind"] = kind
                item_record["downloads"].append(info)
            category_record["items"].append(item_record)

        categories_by_slug[category["slug"]] = category_record

    manifest["categories"] = ordered_categories(categories_by_slug)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(manifest, ROOT / "README.md")
    print(manifest_path)


def write_readme(manifest: dict[str, Any], path: Path) -> None:
    lines = [
        "# Hengyang Optics 30 mm Cage References",
        "",
        "Downloaded public reference materials for the Lumileds cage-holder design.",
        "The files are local references only; verify dimensions against vendor drawings before machining.",
        "",
        f"Source site: <{BASE_URL}>",
        f"Downloaded at: `{manifest['downloaded_at']}`",
        "",
        "## Categories",
        "",
    ]
    for category in manifest["categories"]:
        lines.append(f"### {category['label']}")
        lines.append("")
        lines.append(f"- Page: <{category['page']}>")
        lines.append(f"- Folder: `{category['slug']}/`")
        lines.append(f"- Why included: {category['reason']}")
        lines.append(f"- Product rows: {len(category['items'])}")
        for item in category["items"][:12]:
            files = [d for d in item["downloads"] if "path" in d and d.get("kind") != "item-json"]
            params = "; ".join(
                f"{p['key']}={p['value']}{p['unit']}" for p in item.get("parameters", [])[:5]
            )
            lines.append(f"  - `{item['model']}` {item['name']}: {len(files)} files. {params}")
        if len(category["items"]) > 12:
            lines.append(f"  - ... {len(category['items']) - 12} more rows in the manifest.")
        lines.append("")
    lines += [
        "## Notes For Lumileds Holder Design",
        "",
        "- Use GT-090101 and HCP/HCT dimensions for the shared 30 mm cage interface.",
        "- Use the Lumileds PCB data for the central aperture and rear pocket; do not copy the GT-090101 rotating optic clamp.",
        "- The essential shared geometry is four Ø6 mm cage rods on a 30 x 30 mm square pitch.",
        "- Keep vendor STEP/PDF files as references. New printable holders should remain independent derivative designs.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
