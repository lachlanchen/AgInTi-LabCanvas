"""Read exact-task article evidence for a source-summary recovery turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wechat_source_recovery import (
    MAX_RESPONSE_BYTES,
    MIN_ARTICLE_CHARS,
    article_identity_key,
    detect_verification_gate,
    extract_mp_weixin_urls,
    parse_wechat_article,
)


def retained_article_evidence(
    artifact_dir: Path,
    items: list[dict[str, Any]],
    *,
    max_chars: int = 100_000,
) -> list[dict[str, Any]]:
    """Require evidence for every current URL; never substitute nearby files."""
    wanted: dict[str, dict[str, Any]] = {}
    for item in items:
        urls = extract_mp_weixin_urls(str(item.get("text") or ""))
        if not urls:
            return []
        for url in urls:
            key = article_identity_key(url)
            entry = wanted.setdefault(key, {"item_ids": [], "source_text": str(item.get("text") or "")})
            entry["item_ids"].append(str(item.get("item_id") or ""))
    if not wanted:
        return []
    root = artifact_dir.resolve()
    found: dict[str, dict[str, Any]] = {}
    for meta in sorted((root / "articles").glob("*/meta.json")):
        html = meta.with_name("article.html")
        if not all(path.resolve().is_relative_to(root) for path in (meta, html)):
            continue
        try:
            if meta.stat().st_size > 64_000 or html.stat().st_size > MAX_RESPONSE_BYTES:
                continue
            metadata = json.loads(meta.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                continue
            url = str(metadata.get("url") or "")
            if not extract_mp_weixin_urls(url):
                continue
            key = article_identity_key(url)
            if key not in wanted:
                continue
            raw_html = html.read_text(encoding="utf-8")
            article = parse_wechat_article(raw_html)
            full = len(article.body) >= MIN_ARTICLE_CHARS and not detect_verification_gate(raw_html)
            found[key] = {
                **wanted[key],
                "title": article.title or str(metadata.get("title") or ""),
                "quality": "full_article" if full else "card_metadata",
                "body": article.body if full else "",
                "description": article.description,
            }
        except (OSError, ValueError, TypeError):
            continue
    if found.keys() != wanted.keys():
        return []
    evidence = [found[key] for key in wanted]
    # Oversized batches stay on the normal worker path; never drop late items.
    return evidence if len(json.dumps(evidence, ensure_ascii=False)) <= max_chars else []


def persist_retained_article_evidence(artifact_dir: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Use the established article preflight contract for durable knowledge."""
    root = artifact_dir / "retained_source_evidence"
    root.mkdir(parents=True, exist_ok=True)
    articles = []
    for index, source in enumerate(evidence, start=1):
        entry = {
            "title": source["title"], "source_quality": source["quality"],
            "source_scope": "exact_current_message",
            "identity": {"item_ids": source["item_ids"]},
        }
        if source["quality"] == "full_article":
            path = root / f"article-{index}.md"
            path.write_text(source["body"], encoding="utf-8")
            path.chmod(0o600)
            entry["markdown_path"] = str(path.resolve())
        articles.append(entry)
    path = root / "manifest.json"
    manifest = {"status": "ok", "read_only": True, "articles": articles, "manifest_json": str(path.resolve())}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return manifest
