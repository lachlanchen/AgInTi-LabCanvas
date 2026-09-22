"""Decode native reply references without confusing them with nearby messages."""

from __future__ import annotations

import html
import re
from typing import Any
import xml.etree.ElementTree as ET


def parse_quote_reference(value: Any) -> dict[str, str] | None:
    text = str(value or "").strip()
    if len(text) > 2_000_000:
        return None
    # The transport may prepend the group sender or entity-escape the envelope.
    for _ in range(3):
        start = text.find("<")
        candidate = text[start:] if start >= 0 else text
        if "<!DOCTYPE" in candidate.upper() or "<!ENTITY" in candidate.upper():
            return None
        try:
            root = ET.fromstring(candidate)
        except ET.ParseError:
            decoded = html.unescape(text)
            if decoded == text:
                return None
            text = decoded
            continue
        app = root if root.tag == "appmsg" else root.find(".//appmsg")
        if app is None or app.findtext("type") != "57":
            return None
        ref = app.find("refermsg")
        if ref is None:
            return None
        content = ref.find("content")
        body = ref.findtext("content") or ""
        if content is not None and len(content):
            body = "".join(ET.tostring(child, encoding="unicode") for child in content)
        return {
            "request": app.findtext("title") or "",
            "server_id": ref.findtext("svrid") or "",
            "sender": ref.findtext("fromusr") or "",
            "sender_display": ref.findtext("displayname") or "",
            "type": ref.findtext("type") or "",
            "create_time": ref.findtext("createtime") or "",
            "content": body,
        }
    return None


def exact_task_source_row(task: dict[str, Any]) -> dict[str, Any]:
    source = task.get("source") or {}
    chat = str(task.get("chat") or "")
    if source.get("chat") and source["chat"] != chat:
        return {}
    if source.get("content"):
        return source
    for row in task.get("context") or []:
        if not isinstance(row, dict) or (row.get("chat") and row["chat"] != chat):
            continue
        shard = source.get("message_db")
        if shard and row.get("message_db") != shard:
            continue
        if source.get("server_id"):
            matched = str(row.get("server_id")) == str(source["server_id"])
        else:
            matched = source.get("local_id") is not None and str(row.get("local_id")) == str(source["local_id"])
        if matched:
            return row
    return {}


def task_quote_reference(task: dict[str, Any]) -> dict[str, str] | None:
    return parse_quote_reference(exact_task_source_row(task).get("content"))


def task_has_explicit_quote(task: dict[str, Any]) -> bool:
    source = task.get("source") or {}
    if source.get("kind") == "quote_reply":
        return True
    try:
        if int(source.get("local_type") or 0) == ((57 << 32) | 49):
            return True
    except (TypeError, ValueError):
        pass
    row = exact_task_source_row(task)
    return bool(parse_quote_reference(row.get("content")) or row.get("quote_text")
                or task.get("quote_text") or source.get("quote_text")
                or re.search(r"\[quoted\s", str(task.get("original_request") or ""), re.I))
