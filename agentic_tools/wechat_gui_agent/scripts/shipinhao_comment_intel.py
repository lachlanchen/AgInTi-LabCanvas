#!/usr/bin/env python3
"""Summarize Shipinhao/WeChat Channels comment exports for source clues."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any
from urllib import request as urlrequest


DEFAULT_KEYWORDS = [
    "@元宝",
    "元宝",
    "腾讯元宝",
    "英文全文",
    "中文全文",
    "全文",
    "总结",
    "摘要",
    "字幕",
    "转写",
    "轉寫",
    "逐字稿",
    "transcript",
    "summary",
]


@dataclass
class CommentHit:
    path: str
    nickname: str
    content: str
    like_count: int
    keywords: list[str]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comments-json", type=Path, help="wx_channel exported comments JSON.")
    parser.add_argument("--api-url", default="", help="Local wx_channel API, e.g. http://127.0.0.1:2026.")
    parser.add_argument("--object-id", default="", help="Shipinhao object_id for API export.")
    parser.add_argument("--nonce-id", default="", help="Shipinhao nonce_id for API export.")
    parser.add_argument("--title", default="", help="Video title/description for API export.")
    parser.add_argument("--author", default="", help="Video author for API export.")
    parser.add_argument("--keyword", action="append", default=[], help="Extra keyword to search in comments.")
    parser.add_argument("--markdown-out", type=Path, help="Write a Markdown summary.")
    parser.add_argument("--json-out", type=Path, help="Write machine-readable JSON summary.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    try:
        source_path = args.comments_json
        if source_path is None and args.api_url:
            source_path = export_comments_from_api(args)
        if source_path is None:
            raise SystemExit("--comments-json or --api-url with --object-id/--nonce-id is required")

        payload = load_json(source_path)
        summary = summarize_comment_payload(payload, source_path=source_path, keywords=DEFAULT_KEYWORDS + args.keyword)
        markdown = render_markdown(summary)
        json_text = json.dumps(summary, ensure_ascii=False, indent=2)

        if args.markdown_out:
            args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_out.write_text(markdown, encoding="utf-8")
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json_text + "\n", encoding="utf-8")

        print(json_text if args.json else markdown)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


def export_comments_from_api(args: argparse.Namespace) -> Path:
    if not args.object_id or not args.nonce_id:
        raise ValueError("--object-id and --nonce-id are required for API export")
    api = args.api_url.rstrip("/")
    body = json.dumps(
        {
            "object_id": args.object_id,
            "nonce_id": args.nonce_id,
            "title": args.title,
            "author": args.author,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urlrequest.Request(
        f"{api}/api/channels/feed/comment/export",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if int(data.get("code", -1)) != 0 or not isinstance(data.get("data"), dict):
        raise RuntimeError(f"comment export failed: {data.get('message') or data}")
    saved = str(data["data"].get("saved_path") or "")
    if not saved:
        raise RuntimeError("comment export succeeded but returned no saved_path")
    path = Path(saved)
    if not path.exists():
        raise RuntimeError(f"comment export file missing: {path}")
    return path


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def summarize_comment_payload(payload: dict[str, Any], *, source_path: Path, keywords: list[str]) -> dict[str, Any]:
    comments = payload.get("commentInfo")
    if not isinstance(comments, list):
        comments = payload.get("comments")
    if not isinstance(comments, list):
        comments = []

    flat = flatten_comments(comments)
    hits = find_hits(flat, keywords)
    high_signal = sorted(flat, key=lambda item: item.like_count, reverse=True)[:8]
    source_quality = "comment_hits" if hits else ("comments_available" if flat else "no_comments")

    return {
        "ok": True,
        "source_path": str(source_path),
        "object_id": str(payload.get("objectId") or payload.get("object_id") or ""),
        "object_nonce_id": str(payload.get("objectNonceId") or payload.get("object_nonce_id") or ""),
        "title": str(payload.get("title") or ""),
        "author": str(payload.get("author") or ""),
        "source": str(payload.get("source") or ""),
        "source_quality": source_quality,
        "comment_count": len(flat),
        "keyword_hits": [hit.__dict__ for hit in hits[:30]],
        "high_signal_comments": [comment.__dict__ for comment in high_signal],
        "recommended_use": recommendation(source_quality, hits),
    }


def flatten_comments(comments: list[Any], prefix: str = "comment") -> list[CommentHit]:
    result: list[CommentHit] = []
    for index, raw in enumerate(comments, start=1):
        if not isinstance(raw, dict):
            continue
        path = f"{prefix}[{index}]"
        entry = CommentHit(
            path=path,
            nickname=str(raw.get("nickname") or raw.get("username") or ""),
            content=normalize_text(str(raw.get("content") or "")),
            like_count=safe_int(raw.get("likeCount") or raw.get("like_count") or 0),
            keywords=[],
        )
        if entry.content:
            result.append(entry)
        replies = raw.get("levelTwoComment") or raw.get("replies") or []
        if isinstance(replies, list):
            result.extend(flatten_comments(replies, prefix=f"{path}.reply"))
    return result


def find_hits(comments: list[CommentHit], keywords: list[str]) -> list[CommentHit]:
    hits: list[CommentHit] = []
    normalized_keywords = [(kw, kw.casefold()) for kw in keywords if kw]
    for comment in comments:
        lowered = comment.content.casefold()
        matched = [kw for kw, folded in normalized_keywords if folded in lowered]
        if matched:
            hits.append(
                CommentHit(
                    path=comment.path,
                    nickname=comment.nickname,
                    content=comment.content,
                    like_count=comment.like_count,
                    keywords=matched,
                )
            )
    hits.sort(key=lambda item: (len(item.keywords), item.like_count), reverse=True)
    return hits


def recommendation(source_quality: str, hits: list[CommentHit]) -> str:
    if hits:
        return "Use keyword-hit comments as auxiliary evidence for transcript/summary intent; still verify against video/media when possible."
    if source_quality == "comments_available":
        return "Use high-signal comments for context only; no Yuanbao/transcript request was found."
    return "No comment evidence found. Do not claim comment-based understanding."


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Shipinhao Comment Intelligence",
        "",
        f"- Source: `{summary['source_path']}`",
        f"- Title: {summary.get('title') or '(unknown)'}",
        f"- Author: {summary.get('author') or '(unknown)'}",
        f"- Comments scanned: {summary['comment_count']}",
        f"- Keyword hits: {len(summary['keyword_hits'])}",
        f"- Quality: `{summary['source_quality']}`",
        "",
        "## Yuanbao / Transcript / Summary Hits",
    ]
    hits = summary["keyword_hits"]
    if not hits:
        lines.append("No matching Yuanbao/transcript/summary comments found.")
    else:
        for hit in hits[:10]:
            lines.append(f"- `{hit['path']}` {hit['nickname']}: {hit['content']} [{', '.join(hit['keywords'])}]")
    lines.extend(["", "## High-Signal Comments"])
    for item in summary["high_signal_comments"][:8]:
        lines.append(f"- `{item['path']}` likes={item['like_count']} {item['nickname']}: {item['content']}")
    lines.extend(["", "## Use", summary["recommended_use"], ""])
    return "\n".join(lines)


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split())


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
