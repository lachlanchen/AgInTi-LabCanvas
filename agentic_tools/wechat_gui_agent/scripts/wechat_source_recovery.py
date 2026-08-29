#!/usr/bin/env python3
"""Recover readable WeChat article and Channels evidence without GUI verification.

The helper is deliberately read-only. It never opens a browser, focuses WeChat,
posts a comment, or attempts to defeat a login/CAPTCHA. For official-account
articles it tries ordinary HTTP requests with the mobile WeChat user agent,
extracts ``#js_content``, and keeps a private local cache. When a source remains
unreadable it emits an evidence/reconstruction packet for the worker agent.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any
from urllib import parse as urlparse
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_CACHE = PRIVATE / "source_recovery_cache"
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MIN_ARTICLE_CHARS = 240

WECHAT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.43 NetType/WIFI Language/zh_CN"
)
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
GATE_MARKERS = (
    "环境异常",
    "完成验证后继续访问",
    "请完成验证",
    "访问环境异常",
    "wappoc_appmsgcaptcha",
    "appmsgcaptcha",
)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK_TAGS = {"article", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul"}


@dataclass
class ParsedArticle:
    title: str = ""
    author: str = ""
    account: str = ""
    publish_time: str = ""
    description: str = ""
    body: str = ""
    image_urls: list[str] = field(default_factory=list)


class WeChatArticleParser(HTMLParser):
    """Extract article metadata and visible text from WeChat article HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, Any]] = []
        self.content_depth = 0
        self.skip_depth = 0
        self.capture_ids: list[str] = []
        self.capture_text: dict[str, list[str]] = {
            "activity-name": [],
            "js_name": [],
            "publish_time": [],
            "js_profile_desc": [],
        }
        self.meta: dict[str, str] = {}
        self.body_parts: list[str] = []
        self.image_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        starts_content = values.get("id") == "js_content"
        starts_skip = tag in {"script", "style", "noscript", "template"}
        content_active = starts_content or bool(self.content_depth)
        increments_content = content_active and tag not in VOID_TAGS
        if increments_content:
            self.content_depth += 1
        if starts_skip:
            self.skip_depth += 1

        capture_id = values.get("id", "") if values.get("id", "") in self.capture_text else ""
        if capture_id:
            self.capture_ids.append(capture_id)

        meta_key = values.get("property") or values.get("name") or ""
        if tag == "meta" and meta_key and values.get("content"):
            self.meta[meta_key.casefold()] = values["content"].strip()

        if content_active and not self.skip_depth:
            if tag in BLOCK_TAGS:
                self.body_parts.append("\n")
            if tag == "img":
                image_url = values.get("data-src") or values.get("src") or ""
                if image_url.startswith(("http://", "https://")) and image_url not in self.image_urls:
                    self.image_urls.append(image_url)
                alt = values.get("alt", "").strip()
                if alt:
                    self.body_parts.append(f" [{alt}] ")

        if tag not in VOID_TAGS:
            self.stack.append(
                {
                    "tag": tag,
                    "content": increments_content,
                    "skip": starts_skip,
                    "capture_id": capture_id,
                }
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        entry: dict[str, Any] | None = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                entry = self.stack.pop(index)
                break
        if self.content_depth and tag in BLOCK_TAGS and not self.skip_depth:
            self.body_parts.append("\n")
        if entry:
            if entry.get("capture_id"):
                for index in range(len(self.capture_ids) - 1, -1, -1):
                    if self.capture_ids[index] == entry["capture_id"]:
                        self.capture_ids.pop(index)
                        break
            if entry.get("skip") and self.skip_depth:
                self.skip_depth -= 1
            if entry.get("content") and self.content_depth:
                self.content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.capture_ids and not self.skip_depth:
            self.capture_text[self.capture_ids[-1]].append(data)
        if self.content_depth and not self.skip_depth:
            self.body_parts.append(data)

    def article(self) -> ParsedArticle:
        body = clean_article_text("".join(self.body_parts))
        title = first_nonempty(
            self.meta.get("og:title"),
            clean_inline("".join(self.capture_text["activity-name"])),
        )
        author = first_nonempty(
            self.meta.get("author"),
            self.meta.get("article:author"),
            clean_inline("".join(self.capture_text["js_name"])),
        )
        return ParsedArticle(
            title=title,
            author=author,
            account=clean_inline("".join(self.capture_text["js_name"])),
            publish_time=clean_inline("".join(self.capture_text["publish_time"])),
            description=first_nonempty(self.meta.get("og:description"), self.meta.get("description")),
            body=body,
            image_urls=self.image_urls,
        )


def recover_task_sources(
    task: dict[str, Any],
    output_dir: Path,
    *,
    timeout: float = 18.0,
    cache_dir: Path = DEFAULT_CACHE,
) -> dict[str, Any]:
    """Recover current-message article text and a Shipinhao evidence plan."""
    output_dir.mkdir(parents=True, exist_ok=True)
    source_text = task_source_text(task)
    urls = extract_mp_weixin_urls(source_text)
    card = extract_article_card_profile(source_text)
    articles: list[dict[str, Any]] = []
    for index, url in enumerate(urls[:3], start=1):
        articles.append(
            recover_mp_weixin_article(
                url,
                output_dir / f"article-{index}",
                card_profile=card,
                timeout=timeout,
                cache_dir=cache_dir,
            )
        )
    if not articles and card.get("title") and any(
        marker in source_text.casefold()
        for marker in ("公众号", "公眾號", "gongzhonghao", "mp.weixin")
    ):
        card_only = {
            "status": "reconstruction_required",
            "source_quality": "card_metadata",
            "title": card.get("title", ""),
            "author": card.get("author", ""),
            "description": card.get("description", ""),
            "article_chars": 0,
            "verification_requested": False,
        }
        card_only["recovery_queries"] = article_recovery_queries(card_only, card, {})
        articles.append(card_only)

    shipinhao = build_shipinhao_recovery_packet(source_text)
    qualities = [str(item.get("source_quality") or "") for item in articles]
    if "full_article" in qualities:
        status = "ok"
    elif articles or shipinhao.get("detected"):
        status = "reconstruction_required"
    else:
        status = "not_applicable"

    manifest: dict[str, Any] = {
        "status": status,
        "read_only": True,
        "verification_policy": "never_request_user_verification_for_read_only_research",
        "browser_policy": "do_not_open_or_focus_external_browser",
        "articles": articles,
        "shipinhao": shipinhao,
        "agent_next_action": (
            "Read full_article Markdown when available. Otherwise use the exact-title/author/object-id reconstruction queries "
            "with web search and authoritative public sources, report evidence quality, and answer without asking the user to verify."
        ),
    }
    manifest_json = output_dir / "manifest.json"
    manifest_md = output_dir / "manifest.md"
    manifest["manifest_json"] = str(manifest_json)
    manifest["manifest_md"] = str(manifest_md)
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_md.write_text(render_recovery_manifest(manifest), encoding="utf-8")
    return manifest


def task_needs_source_recovery(task: dict[str, Any]) -> bool:
    text = task_source_text(task).casefold()
    markers = (
        "mp.weixin.qq.com",
        "公众号",
        "公眾號",
        "gongzhonghao",
        "finderfeed",
        "shipinhao",
        "视频号",
        "視頻號",
        "channels.weixin.qq.com",
        "objectnonceid",
    )
    return any(marker.casefold() in text for marker in markers)


def recover_mp_weixin_article(
    url: str,
    output_dir: Path,
    *,
    card_profile: dict[str, str] | None = None,
    timeout: float = 18.0,
    cache_dir: Path = DEFAULT_CACHE,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    card_profile = card_profile or {}
    normalized_url = normalize_wechat_article_url(url)
    identity = article_identity(normalized_url)
    cache_key = sha256(article_identity_key(normalized_url).encode("utf-8")).hexdigest()[:24]
    cached = load_cached_article(cache_dir / "articles" / cache_key, output_dir)
    if cached:
        cached["requested_url"] = normalized_url
        cached["identity"] = identity
        cached["recovery_queries"] = article_recovery_queries(cached, card_profile, identity)
        return cached

    attempts: list[dict[str, Any]] = []
    best_article = ParsedArticle()
    best_html = ""
    final_url = normalized_url
    for agent_name, user_agent in (("wechat_mobile", WECHAT_USER_AGENT), ("desktop", DESKTOP_USER_AGENT)):
        try:
            response = fetch_html(normalized_url, user_agent=user_agent, timeout=timeout)
        except Exception as exc:
            attempts.append({"agent": agent_name, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:240]}"})
            continue
        final_url = response["final_url"]
        html_text = response["text"]
        gated = detect_verification_gate(html_text)
        article = parse_wechat_article(html_text)
        attempts.append(
            {
                "agent": agent_name,
                "ok": True,
                "status": response["status"],
                "bytes": response["bytes"],
                "verification_gate": gated,
                "article_chars": len(article.body),
            }
        )
        if len(article.body) > len(best_article.body):
            best_article = article
            best_html = html_text
        if not gated and len(article.body) >= MIN_ARTICLE_CHARS:
            break

    title = first_nonempty(best_article.title, card_profile.get("title"))
    author = first_nonempty(best_article.author, best_article.account, card_profile.get("author"))
    description = first_nonempty(best_article.description, card_profile.get("description"))
    full = len(best_article.body) >= MIN_ARTICLE_CHARS and not detect_verification_gate(best_html)
    result: dict[str, Any] = {
        "status": "ok" if full else "reconstruction_required",
        "source_quality": "full_article" if full else ("card_metadata" if title or description else "blocked"),
        "requested_url": normalized_url,
        "final_url": final_url,
        "identity": identity,
        "title": title,
        "author": author,
        "publish_time": best_article.publish_time,
        "description": description,
        "article_chars": len(best_article.body),
        "image_count": len(best_article.image_urls),
        "attempts": attempts,
        "verification_requested": False,
    }
    result["recovery_queries"] = article_recovery_queries(result, card_profile, identity)
    if full:
        article_md = output_dir / "article.md"
        raw_html = output_dir / "article.html"
        article_md.write_text(render_article_markdown(result, best_article.body), encoding="utf-8")
        raw_html.write_text(best_html, encoding="utf-8")
        result["markdown_path"] = str(article_md)
        result["html_path"] = str(raw_html)
        result["body_excerpt"] = clean_inline(best_article.body)[:1600]
        save_article_cache(cache_dir / "articles" / cache_key, result, best_article.body, best_html)
    else:
        result["agent_next_action"] = (
            "Do not ask for verification. Search the exact title/account and identity tokens, read any canonical paper/GitHub/author source "
            "or trustworthy same-title copy, corroborate claims, and label the answer as reconstructed if the full article remains unavailable."
        )
    return result


def fetch_html(url: str, *, user_agent: str, timeout: float) -> dict[str, Any]:
    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Referer": "https://mp.weixin.qq.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        },
    )
    with urlrequest.urlopen(req, timeout=timeout) as response:
        payload = response.read(MAX_RESPONSE_BYTES)
        content_type = response.headers.get_content_charset() or "utf-8"
        text = payload.decode(content_type, errors="replace")
        return {
            "status": int(response.status),
            "bytes": len(payload),
            "final_url": str(response.geturl()),
            "text": text,
        }


def parse_wechat_article(html_text: str) -> ParsedArticle:
    parser = WeChatArticleParser()
    parser.feed(html_text)
    article = parser.article()
    if not article.title:
        article.title = extract_js_string(html_text, "msg_title")
    if not article.author:
        article.author = first_nonempty(
            extract_js_string(html_text, "nickname"),
            extract_js_string(html_text, "author"),
        )
    if not article.publish_time:
        article.publish_time = extract_js_string(html_text, "publish_time")
    return article


def detect_verification_gate(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(marker.casefold() in lowered for marker in GATE_MARKERS)


def normalize_wechat_article_url(url: str) -> str:
    value = unescape(str(url or "").strip().strip("<>'\""))
    value = value.rstrip("),.，;；]】")
    for _ in range(3):
        parsed = urlparse.urlsplit(value)
        query = urlparse.parse_qs(parsed.query)
        target = first_nonempty(*(query.get("target_url") or []), *(query.get("url") or []))
        if "wappoc_appmsgcaptcha" not in parsed.path or not target:
            break
        decoded = urlparse.unquote(target)
        if decoded == value:
            break
        value = decoded
    parsed = urlparse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"mp.weixin.qq.com", "weixin.qq.com"}:
        return value
    return urlparse.urlunsplit(("https", "mp.weixin.qq.com", parsed.path, parsed.query, ""))


def extract_mp_weixin_urls(text: str) -> list[str]:
    decoded = unescape(str(text or "")).replace("\\u0026", "&")
    matches = re.findall(r"https?://(?:mp\.)?weixin\.qq\.com/[^\s<>\"']+", decoded, flags=re.I)
    for value in extract_xml_values(decoded, "url"):
        if "mp.weixin.qq.com" in value:
            matches.insert(0, value)
    seen: set[str] = set()
    urls: list[str] = []
    for match in matches:
        normalized = normalize_wechat_article_url(match)
        key = article_identity_key(normalized)
        if "mp.weixin.qq.com" not in normalized or key in seen:
            continue
        seen.add(key)
        urls.append(normalized)
    return urls


def extract_article_card_profile(text: str) -> dict[str, str]:
    return {
        "title": first_nonempty(*extract_xml_values(text, "title")),
        "author": first_nonempty(
            *extract_xml_values(text, "sourcedisplayname"),
            *extract_xml_values(text, "author"),
        ),
        "description": first_nonempty(*extract_xml_values(text, "des"), *extract_xml_values(text, "description")),
    }


def article_identity(url: str) -> dict[str, str]:
    query = urlparse.parse_qs(urlparse.urlsplit(url).query)
    return {key: str((query.get(key) or [""])[0]) for key in ("__biz", "mid", "idx", "sn") if (query.get(key) or [""])[0]}


def article_identity_key(url: str) -> str:
    identity = article_identity(url)
    if identity.get("sn"):
        return f"sn:{identity['sn']}"
    if identity.get("__biz") and identity.get("mid"):
        return "params:" + ":".join(identity.get(key, "") for key in ("__biz", "mid", "idx"))
    parsed = urlparse.urlsplit(url)
    return urlparse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def article_recovery_queries(result: dict[str, Any], card: dict[str, str], identity: dict[str, str]) -> list[str]:
    title = first_nonempty(result.get("title"), card.get("title"))
    author = first_nonempty(result.get("author"), card.get("author"))
    queries: list[str] = []
    if title and author:
        queries.append(f'"{title}" "{author}"')
    if title:
        queries.extend([f'"{title}"', f'site:github.com "{title}"', f'site:arxiv.org "{title}"'])
    if identity.get("sn"):
        queries.append(f'"{identity["sn"]}"')
    if identity.get("__biz") and identity.get("mid"):
        queries.append(f'"{identity["__biz"]}" "{identity["mid"]}"')
    description = first_nonempty(result.get("description"), card.get("description"))
    for token in re.findall(r"(?:10\.\d{4,9}/[-._;()/:A-Z0-9]+|arXiv:\s*\d{4}\.\d{4,5}|github\.com/[\w.-]+/[\w.-]+)", description, flags=re.I):
        queries.append(f'"{token}"')
    return unique_strings(queries)[:8]


def build_shipinhao_recovery_packet(text: str) -> dict[str, Any]:
    lowered = text.casefold()
    detected = any(marker in lowered for marker in ("finderfeed", "shipinhao", "视频号", "視頻號", "channels.weixin.qq.com", "objectnonceid"))
    if not detected:
        return {"detected": False}
    object_id = first_nonempty(*extract_xml_values(text, "objectId"))
    nonce_id = first_nonempty(*extract_xml_values(text, "objectNonceId"))
    title = first_nonempty(*extract_xml_values(text, "desc"), *extract_xml_values(text, "title"))
    author = first_nonempty(*extract_xml_values(text, "nickname"), *extract_xml_values(text, "sourcedisplayname"))
    queries = []
    if title and author:
        queries.append(f'"{title}" "{author}"')
    if title:
        queries.append(f'"{title}" 视频号')
    if object_id:
        queries.append(f'"{object_id}"')
    return {
        "detected": True,
        "object_id": object_id,
        "nonce_id": nonce_id,
        "title": title,
        "author": author,
        "recovery_queries": unique_strings(queries),
        "preferred_evidence_order": [
            "exact_same_chat_cached_video_or_transcript",
            "wx_channel_local_profile_and_comment_export",
            "exact_matching_local_comment_json",
            "existing_visible_native_capture",
            "public_exact_title_author_or_object_id_corroboration",
        ],
        "verification_requested": False,
        "write_actions_allowed": False,
    }


def task_source_text(task: dict[str, Any]) -> str:
    request = str(task.get("request") or "")
    focus = extract_current_request(request)
    reference_section = extract_reference_section(request)
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    source_id = safe_int(source.get("local_id"))
    source_rows: list[str] = []
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        if source_id is not None and safe_int(row.get("local_id")) == source_id:
            source_rows.append(str(row.get("content") or ""))
    adjacent_references = adjacent_source_references(task, source, source_id)
    route = task.get("route_decision") if isinstance(task.get("route_decision"), dict) else {}
    route_values = [str(route.get(key) or "") for key in ("url", "source_url", "object_id", "nonce_id", "title", "author")]
    source_kind = str(source.get("kind") or "").casefold()
    if source_rows:
        # A file/link/card row is the authoritative source. Older coalesced
        # references and generic handling instructions must not make a later
        # article look like an earlier Finder card (or vice versa).
        scoped_values = [*source_rows]
        if source_kind == "text":
            scoped_values.insert(0, focus)
    elif adjacent_references:
        scoped_values = [focus, *adjacent_references]
    else:
        scoped_values = [focus, reference_section]
    return "\n".join(
        value
        for value in [*scoped_values, *route_values]
        if value
    ).strip()


def adjacent_source_references(
    task: dict[str, Any],
    source: dict[str, Any],
    source_id: int | None,
) -> list[str]:
    """Return only an exact attachment immediately preceding a text command."""
    if source_id is None or str(source.get("kind") or "").casefold() != "text":
        return []
    source_time = safe_int(source.get("create_time"))
    source_sender = str(source.get("sender") or "").strip()
    references: list[str] = []
    for row in task.get("context") or []:
        if not isinstance(row, dict) or safe_int(row.get("local_id")) != source_id - 1:
            continue
        row_kind = str(row.get("kind") or "").casefold()
        row_type = safe_int(row.get("local_type"))
        if row_kind == "text" or row_type == 1:
            continue
        row_time = safe_int(row.get("create_time"))
        if source_time is not None and row_time is not None:
            if row_time > source_time or source_time - row_time > 120:
                continue
        row_sender = str(row.get("sender") or "").strip()
        if source_sender and row_sender and source_sender != row_sender:
            continue
        content = str(row.get("content") or "").strip()
        if content:
            references.append(content)
    return references


def extract_current_request(request: str) -> str:
    text = str(request or "")
    match = re.search(
        r"Current coalesced request:\n(?P<body>.*?)(?:\n\nRecent history:|\n\nSame-chat reference media/context rows:|\Z)",
        text,
        flags=re.S,
    )
    return match.group("body").strip() if match else text


def extract_reference_section(request: str) -> str:
    text = str(request or "")
    match = re.search(
        r"Same-chat reference media/context rows:\n(?P<body>.*?)(?:\n\nAutomatic media sync:|\n\nRecent synced WeChat files:|\Z)",
        text,
        flags=re.S,
    )
    return match.group("body").strip() if match else ""


def extract_xml_values(text: str, tag: str) -> list[str]:
    pattern = rf"<{re.escape(tag)}>\s*(?:<!\[CDATA\[(?P<cdata>.*?)\]\]>|(?P<plain>.*?))\s*</{re.escape(tag)}>"
    values: list[str] = []
    for match in re.finditer(pattern, str(text or ""), flags=re.I | re.S):
        value = match.group("cdata") if match.group("cdata") is not None else match.group("plain")
        cleaned = clean_inline(unescape(str(value or "")))
        if cleaned and cleaned != "0" and cleaned not in values:
            values.append(cleaned)
    return values


def extract_js_string(text: str, name: str) -> str:
    match = re.search(rf"(?:var\s+)?{re.escape(name)}\s*=\s*(['\"])(?P<value>.*?)\1\s*;", text, flags=re.I | re.S)
    if not match:
        return ""
    value = match.group("value")
    try:
        value = json.loads(f'"{value.replace(chr(34), chr(92) + chr(34))}"')
    except (json.JSONDecodeError, TypeError):
        pass
    return clean_inline(unescape(str(value)))


def render_article_markdown(result: dict[str, Any], body: str) -> str:
    lines = [f"# {result.get('title') or 'WeChat Article'}", ""]
    if result.get("author"):
        lines.append(f"- Account/author: {result['author']}")
    if result.get("publish_time"):
        lines.append(f"- Published: {result['publish_time']}")
    lines.extend([f"- Source: {result.get('final_url') or result.get('requested_url')}", "", body.strip(), ""])
    return "\n".join(lines)


def render_recovery_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        "# WeChat Source Recovery",
        "",
        f"- Status: `{manifest.get('status')}`",
        "- Mode: read-only; no GUI/browser focus and no user verification request",
        "",
    ]
    for index, article in enumerate(manifest.get("articles") or [], start=1):
        lines.extend(
            [
                f"## Article {index}",
                "",
                f"- Quality: `{article.get('source_quality')}`",
                f"- Title: {article.get('title') or '(unknown)'}",
                f"- Author/account: {article.get('author') or '(unknown)'}",
                f"- Characters: {article.get('article_chars') or 0}",
                f"- Markdown: `{article.get('markdown_path') or ''}`",
                f"- Reconstruction queries: `{json.dumps(article.get('recovery_queries') or [], ensure_ascii=False)}`",
                "",
            ]
        )
    shipinhao = manifest.get("shipinhao") if isinstance(manifest.get("shipinhao"), dict) else {}
    if shipinhao.get("detected"):
        lines.extend(
            [
                "## Shipinhao",
                "",
                f"- Title: {shipinhao.get('title') or '(unknown)'}",
                f"- Author: {shipinhao.get('author') or '(unknown)'}",
                f"- Object ID present: `{bool(shipinhao.get('object_id'))}`",
                f"- Reconstruction queries: `{json.dumps(shipinhao.get('recovery_queries') or [], ensure_ascii=False)}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def save_article_cache(cache_path: Path, result: dict[str, Any], body: str, html_text: str) -> None:
    cache_path.mkdir(parents=True, exist_ok=True)
    md_path = cache_path / "article.md"
    html_path = cache_path / "article.html"
    metadata_path = cache_path / "metadata.json"
    md_path.write_text(render_article_markdown(result, body), encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    metadata = {key: value for key, value in result.items() if key not in {"markdown_path", "html_path", "body_excerpt"}}
    metadata["cached_at"] = datetime.now(timezone.utc).isoformat()
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_cached_article(cache_path: Path, output_dir: Path) -> dict[str, Any] | None:
    metadata_path = cache_path / "metadata.json"
    source_md = cache_path / "article.md"
    source_html = cache_path / "article.html"
    if not metadata_path.is_file() or not source_md.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict) or metadata.get("source_quality") != "full_article":
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    target_md = output_dir / "article.md"
    shutil.copy2(source_md, target_md)
    metadata["markdown_path"] = str(target_md)
    if source_html.is_file():
        target_html = output_dir / "article.html"
        shutil.copy2(source_html, target_html)
        metadata["html_path"] = str(target_html)
    metadata["cache_hit"] = True
    metadata["verification_requested"] = False
    return metadata


def clean_article_text(text: str) -> str:
    lines = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        cleaned = re.sub(r"[\t \f\v]+", " ", unescape(raw)).strip()
        if cleaned:
            lines.append(cleaned)
        elif lines and lines[-1] != "":
            lines.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_inline(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def first_nonempty(*values: Any) -> str:
    for value in values:
        cleaned = clean_inline(value)
        if cleaned:
            return cleaned
    return ""


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = clean_inline(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", default=[], help="mp.weixin article URL; may be repeated.")
    parser.add_argument("--task-json", type=Path, help="Queued WeChat task JSON to inspect.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=18.0)
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    task: dict[str, Any] = {}
    if args.task_json:
        loaded = json.loads(args.task_json.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise SystemExit("--task-json must contain an object")
        task = loaded
    if args.url:
        task = dict(task)
        task["request"] = "Current coalesced request:\n" + "\n".join(args.url)
    if not task:
        raise SystemExit("--url or --task-json is required")
    result = recover_task_sources(task, args.output_dir, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render_recovery_manifest(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
