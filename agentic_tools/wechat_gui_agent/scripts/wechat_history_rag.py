#!/usr/bin/env python3
"""Build model-aware lifetime memory plus exact excerpts from private chat history.

The immutable SQLite history remains the source of truth. Every authorized row
contributes to a hierarchical, loss-aware memory compaction. Query-relevant raw
excerpts are added separately so compaction never pretends to preserve exact
wording that the model window cannot hold.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[3]
MODEL_POLICY = ROOT / "configs" / "model-policy.json"
COMPACTION_SCHEMA = "labcanvas.chat.lifetime_memory.v2"
COMPACTION_ALGORITHM = "hierarchical-extractive-v2"
LATIN_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+.-]{1,}", flags=re.I)
CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]{2,}")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？；;])\s+|\n+")

MEMORY_MARKERS: dict[str, tuple[str, ...]] = {
    "correction": (
        "correction",
        "wrong",
        "not that",
        "instead",
        "更正",
        "不是",
        "错了",
        "应该是",
        "不要",
    ),
    "constraint": (
        "must",
        "never",
        "only",
        "do not",
        "don't",
        "without",
        "必须",
        "绝不",
        "只能",
        "不要",
        "不能",
        "限制",
    ),
    "decision": (
        "i decided",
        "we decided",
        "use this",
        "keep this",
        "final choice",
        "我决定",
        "就用",
        "保留",
        "最终",
        "选择",
    ),
    "preference": (
        "i prefer",
        "i like",
        "i dislike",
        "better",
        "default",
        "我喜欢",
        "我不喜欢",
        "更喜欢",
        "最好",
        "默认",
    ),
    "goal": (
        "i want",
        "i wish",
        "my goal",
        "we want",
        "long term",
        "我想",
        "我要",
        "我希望",
        "目标",
        "长期",
    ),
    "request": (
        "could you",
        "can you",
        "please",
        "help me",
        "请",
        "能不能",
        "可以帮",
        "帮我",
    ),
    "outcome": (
        "done",
        "finished",
        "works",
        "successful",
        "failed",
        "完成",
        "成功",
        "失败",
        "可以用了",
        "已经",
    ),
    "identity": (
        "i am",
        "my name",
        "my project",
        "my research",
        "我是",
        "我的名字",
        "我的项目",
        "我的研究",
    ),
}

TOPIC_STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "have",
    "will",
    "would",
    "could",
    "should",
    "please",
    "about",
    "because",
    "then",
    "there",
    "what",
    "when",
    "where",
    "which",
    "your",
    "you",
    "the",
    "and",
    "for",
    "not",
    "can",
    "use",
    "make",
    "also",
}


@dataclass(frozen=True)
class HistoryMessage:
    source_id: int
    chat_name: str
    direction: str
    sender_display: str
    body: str
    created_at: datetime
    recurrence: int = 1
    source_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class MemorySignal:
    source_id: int
    created_at: str
    sender: str
    category: str
    text: str
    score: float


@dataclass
class MemoryNode:
    digest: str
    level: int
    date_start: str
    date_end: str
    represented_messages: int
    unique_messages: int
    leaf_segments: int
    chats: dict[str, int]
    directions: dict[str, int]
    senders: dict[str, int]
    categories: dict[str, int]
    topics: dict[str, int]
    signals: list[MemorySignal]


def parse_datetime(create_time: object, observed_at: object) -> datetime:
    try:
        epoch = int(create_time or 0)
    except (TypeError, ValueError):
        epoch = 0
    if epoch > 0:
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    text = str(observed_at or "").strip()
    if text:
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def normalize_body(value: object) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())


def estimate_tokens(value: object) -> int:
    """Conservative approximation shared with AgInTi's context controller."""

    text = str(value or "")
    ascii_chars = sum(1 for char in text if ord(char) <= 0x7F)
    non_ascii = len(text) - ascii_chars
    return math.ceil(ascii_chars / 3) + math.ceil(non_ascii * 1.5)


def lexical_terms(value: str) -> set[str]:
    text = str(value or "").casefold()
    terms = {match.group(0) for match in LATIN_TOKEN_RE.finditer(text)}
    for run in CJK_RUN_RE.findall(text):
        if len(run) <= 12:
            terms.add(run)
        for width in (2, 3):
            terms.update(run[index : index + width] for index in range(len(run) - width + 1))
    return terms


def topic_terms(value: str) -> set[str]:
    text = str(value or "").casefold()
    terms = {
        match.group(0)
        for match in LATIN_TOKEN_RE.finditer(text)
        if len(match.group(0)) >= 3 and match.group(0) not in TOPIC_STOPWORDS
    }
    for run in CJK_RUN_RE.findall(text):
        if 2 <= len(run) <= 10:
            terms.add(run)
    return terms


def _allowed_chats(chats: Iterable[str]) -> list[str]:
    return [str(chat).strip() for chat in dict.fromkeys(chats) if str(chat).strip()]


def load_history(
    db: Path,
    chats: Iterable[str],
    *,
    directions: Iterable[str] | None = None,
) -> list[HistoryMessage]:
    """Load every authorized personal-WeChat row; there is deliberately no LIMIT."""

    allowed = _allowed_chats(chats)
    if not db.is_file() or not allowed:
        return []
    placeholders = ",".join("?" for _ in allowed)
    allowed_directions = [
        str(direction).strip().casefold()
        for direction in dict.fromkeys(directions or ())
        if str(direction).strip()
    ]
    direction_clause = ""
    params: list[object] = [*allowed]
    if allowed_directions:
        direction_placeholders = ",".join("?" for _ in allowed_directions)
        direction_clause = f" AND lower(direction) IN ({direction_placeholders})"
        params.extend(allowed_directions)
    query = f"""
        SELECT id, chat_name, direction, sender_display, body, create_time, observed_at
        FROM source_messages
        WHERE chat_name IN ({placeholders})
        {direction_clause}
        ORDER BY create_time ASC, id ASC
    """
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    messages = []
    for row in rows:
        body = normalize_body(row["body"])
        if not body:
            continue
        source_id = int(row["id"])
        messages.append(
            HistoryMessage(
                source_id=source_id,
                chat_name=str(row["chat_name"] or ""),
                direction=str(row["direction"] or ""),
                sender_display=str(row["sender_display"] or ""),
                body=body,
                created_at=parse_datetime(row["create_time"], row["observed_at"]),
                source_ids=(source_id,),
            )
        )
    return messages


def load_wecom_history(db: Path, chats: Iterable[str]) -> list[HistoryMessage]:
    """Load every authorized WeCom row without assuming optional columns."""

    allowed = _allowed_chats(chats)
    if not db.is_file() or not allowed:
        return []
    placeholders = ",".join("?" for _ in allowed)
    try:
        with sqlite3.connect(db) as connection:
            connection.row_factory = sqlite3.Row
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(messages)")}
            if not {"id", "chat", "direction", "body"}.issubset(columns):
                return []
            sender_expression = (
                "COALESCE(sender_display, sender, '')"
                if "sender_display" in columns and "sender" in columns
                else "COALESCE(sender_display, '')"
                if "sender_display" in columns
                else "COALESCE(sender, '')"
                if "sender" in columns
                else "''"
            )
            create_expression = "create_time" if "create_time" in columns else "0"
            observed_expression = "created_at" if "created_at" in columns else "''"
            rows = connection.execute(
                f"""
                SELECT id, chat, direction, {sender_expression} AS sender_display,
                       body, {create_expression} AS create_time,
                       {observed_expression} AS observed_at
                FROM messages
                WHERE chat IN ({placeholders})
                ORDER BY COALESCE({create_expression}, 0) ASC, id ASC
                """,
                allowed,
            ).fetchall()
    except sqlite3.Error:
        return []
    messages = []
    for row in rows:
        body = normalize_body(row["body"])
        if not body:
            continue
        source_id = int(row["id"])
        messages.append(
            HistoryMessage(
                source_id=source_id,
                chat_name=str(row["chat"] or ""),
                direction=str(row["direction"] or ""),
                sender_display=str(row["sender_display"] or ""),
                body=body,
                created_at=parse_datetime(row["create_time"], row["observed_at"]),
                source_ids=(source_id,),
            )
        )
    return messages


def deduplicate_history(messages: Iterable[HistoryMessage]) -> list[HistoryMessage]:
    """Collapse exact repeats while retaining complete row coverage provenance."""

    grouped: dict[str, list[HistoryMessage]] = defaultdict(list)
    for message in messages:
        identity = "\x1f".join(
            (
                message.chat_name.casefold(),
                message.direction.casefold(),
                message.sender_display.casefold(),
                message.body.casefold(),
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        grouped[digest].append(message)
    unique = []
    for records in grouped.values():
        newest = max(records, key=lambda item: (item.created_at, item.source_id))
        source_ids = sorted(
            {
                source_id
                for record in records
                for source_id in (record.source_ids or (record.source_id,))
            }
        )
        recurrence = sum(max(1, int(record.recurrence or 1)) for record in records)
        unique.append(
            HistoryMessage(
                source_id=newest.source_id,
                chat_name=newest.chat_name,
                direction=newest.direction,
                sender_display=newest.sender_display,
                body=newest.body,
                created_at=newest.created_at,
                recurrence=recurrence,
                source_ids=tuple(source_ids),
            )
        )
    return sorted(unique, key=lambda item: (item.created_at, item.source_id))


def _load_memory_policy(path: Path = MODEL_POLICY) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    memory = payload.get("memory") if isinstance(payload, dict) else {}
    return dict(memory) if isinstance(memory, dict) else {}


def _positive_int(value: object, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def resolve_memory_budget(
    *,
    model: str = "",
    role: str = "task",
    token_budget: int | None = None,
    char_budget: int | None = None,
    policy_path: Path = MODEL_POLICY,
) -> dict[str, object]:
    """Reserve task/tool/output room, then use the remaining model-aware share."""

    policy = _load_memory_policy(policy_path)
    windows = policy.get("context_window_tokens")
    windows = dict(windows) if isinstance(windows, dict) else {}
    model_key = str(model or "").strip().casefold()
    aliases = [model_key]
    if "local" in model_key:
        aliases.append("localllm")
    if "deepseek" in model_key:
        aliases.append("deepseek")
    if "gpt" in model_key or "code-review" in model_key:
        aliases.append("codex")
    aliases.append("default")
    context_window = 0
    for alias in aliases:
        if alias and alias in windows:
            context_window = _positive_int(windows[alias], 0)
            if context_window:
                break
    if not context_window:
        env_name = "AGINTI_LOCALLLM_CONTEXT_TOKENS" if "local" in model_key else "AGINTI_CONTEXT_WINDOW_TOKENS"
        context_window = _positive_int(os.environ.get(env_name), 32768)

    output_reserve = _positive_int(policy.get("output_reserve_tokens"), 6144)
    tool_reserve = _positive_int(policy.get("tool_reserve_tokens"), 6144)
    available = max(2048, context_window - output_reserve - tool_reserve)
    fractions = policy.get("role_memory_fraction")
    fractions = dict(fractions) if isinstance(fractions, dict) else {}
    try:
        fraction = float(fractions.get(role, fractions.get("default", 0.34)))
    except (TypeError, ValueError):
        fraction = 0.34
    fraction = min(0.65, max(0.12, fraction))
    minimum = _positive_int(policy.get("minimum_memory_tokens"), 2048)
    maximum = _positive_int(policy.get("maximum_memory_tokens"), 24576)
    resolved_tokens = int(token_budget or min(maximum, max(minimum, available * fraction)))
    resolved_tokens = max(512, min(resolved_tokens, available))
    resolved_chars = max(2000, int(char_budget or resolved_tokens * 2.1))
    if char_budget is not None:
        resolved_chars = max(1000, int(char_budget))
    try:
        full_fraction = float(policy.get("full_memory_fraction", 0.72))
    except (TypeError, ValueError):
        full_fraction = 0.72
    full_fraction = min(0.9, max(0.55, full_fraction))
    return {
        "model": model or "policy-default",
        "role": role,
        "context_window_tokens": context_window,
        "available_input_tokens": available,
        "memory_token_budget": resolved_tokens,
        "memory_char_budget": resolved_chars,
        "full_memory_fraction": full_fraction,
        "output_reserve_tokens": output_reserve,
        "tool_reserve_tokens": tool_reserve,
    }


def _message_category(message: HistoryMessage) -> str:
    folded = message.body.casefold()
    for category, markers in MEMORY_MARKERS.items():
        if any(marker in folded for marker in markers):
            return category
    return "conversation"


def _signal_text(message: HistoryMessage, *, max_chars: int = 420) -> str:
    sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(message.body) if part.strip()]
    if not sentences:
        return message.body[:max_chars]
    marker_sentences = [
        sentence
        for sentence in sentences
        if any(marker in sentence.casefold() for markers in MEMORY_MARKERS.values() for marker in markers)
    ]
    selected = marker_sentences[:2] or [sentences[0]]
    if len(sentences) > 1 and sentences[-1] not in selected:
        selected.append(sentences[-1])
    text = " ".join(selected)
    if len(text) > max_chars:
        head = max_chars * 2 // 3
        tail = max_chars - head - 1
        text = f"{text[:head].rstrip()}…{text[-tail:].lstrip()}"
    return text


def _signal_score(message: HistoryMessage, category: str) -> float:
    base = {
        "correction": 9.0,
        "constraint": 8.5,
        "decision": 8.0,
        "preference": 7.5,
        "goal": 7.5,
        "request": 5.5,
        "outcome": 5.0,
        "identity": 6.5,
        "conversation": 1.0,
    }.get(category, 1.0)
    if message.direction.casefold() == "inbound":
        base += 0.8
    base += min(2.0, math.log2(max(1, message.recurrence)))
    base += min(1.0, len(message.body) / 800.0)
    return base


def _segment_messages(
    messages: Sequence[HistoryMessage],
    *,
    max_messages: int = 48,
    max_chars: int = 18000,
) -> list[list[HistoryMessage]]:
    """Create append-stable month buckets and bounded subsegments."""

    buckets: dict[tuple[str, str], list[HistoryMessage]] = defaultdict(list)
    for message in messages:
        month = message.created_at.astimezone().strftime("%Y-%m")
        buckets[(message.chat_name, month)].append(message)
    segments: list[list[HistoryMessage]] = []
    for key in sorted(buckets, key=lambda item: (item[1], item[0])):
        current: list[HistoryMessage] = []
        current_chars = 0
        for message in buckets[key]:
            size = len(message.body)
            if current and (len(current) >= max_messages or current_chars + size > max_chars):
                segments.append(current)
                current = []
                current_chars = 0
            current.append(message)
            current_chars += size
        if current:
            segments.append(current)
    return segments


def _counter_dict(values: Iterable[str]) -> dict[str, int]:
    return dict(Counter(value for value in values if value))


def _segment_digest(messages: Sequence[HistoryMessage]) -> str:
    digest = hashlib.sha256()
    digest.update(COMPACTION_ALGORITHM.encode("ascii"))
    for message in messages:
        digest.update(str(message.source_id).encode("ascii"))
        digest.update(b"\0")
        digest.update(message.body.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(str(message.recurrence).encode("ascii"))
    return digest.hexdigest()


def _node_to_json(node: MemoryNode) -> dict[str, object]:
    payload = asdict(node)
    payload["schema"] = COMPACTION_SCHEMA
    payload["algorithm"] = COMPACTION_ALGORITHM
    return payload


def _node_from_json(payload: dict[str, object]) -> MemoryNode | None:
    if payload.get("schema") != COMPACTION_SCHEMA or payload.get("algorithm") != COMPACTION_ALGORITHM:
        return None
    try:
        return MemoryNode(
            digest=str(payload["digest"]),
            level=int(payload["level"]),
            date_start=str(payload["date_start"]),
            date_end=str(payload["date_end"]),
            represented_messages=int(payload["represented_messages"]),
            unique_messages=int(payload["unique_messages"]),
            leaf_segments=int(payload["leaf_segments"]),
            chats={str(key): int(value) for key, value in dict(payload["chats"]).items()},
            directions={str(key): int(value) for key, value in dict(payload["directions"]).items()},
            senders={str(key): int(value) for key, value in dict(payload["senders"]).items()},
            categories={str(key): int(value) for key, value in dict(payload["categories"]).items()},
            topics={str(key): int(value) for key, value in dict(payload["topics"]).items()},
            signals=[MemorySignal(**dict(item)) for item in list(payload["signals"])],
        )
    except (KeyError, TypeError, ValueError):
        return None


def _cache_node(cache_dir: Path | None, node: MemoryNode) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        cache_dir.chmod(0o700)
    except OSError:
        pass
    path = cache_dir / f"{node.digest}.json"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(_node_to_json(node), ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _load_cached_node(cache_dir: Path | None, digest: str) -> MemoryNode | None:
    if cache_dir is None:
        return None
    path = cache_dir / f"{digest}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("digest") != digest:
        return None
    return _node_from_json(payload)


def _select_diverse_signals(signals: Sequence[MemorySignal], limit: int) -> list[MemorySignal]:
    if len(signals) <= limit:
        return sorted(signals, key=lambda item: (item.created_at, item.source_id))
    ranked = sorted(signals, key=lambda item: (item.score, item.created_at), reverse=True)
    selected: list[MemorySignal] = []
    used: set[int] = set()
    for key_fn in (
        lambda item: item.category,
        lambda item: item.created_at[:7],
        lambda item: item.sender.casefold(),
    ):
        seen_keys: set[str] = set()
        for item in ranked:
            key = str(key_fn(item) or "")
            if not key or key in seen_keys or item.source_id in used:
                continue
            selected.append(item)
            used.add(item.source_id)
            seen_keys.add(key)
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break
    for item in ranked:
        if len(selected) >= limit:
            break
        if item.source_id not in used:
            selected.append(item)
            used.add(item.source_id)
    return sorted(selected, key=lambda item: (item.created_at, item.source_id))


def _leaf_node(messages: Sequence[HistoryMessage], cache_dir: Path | None) -> tuple[MemoryNode, bool]:
    digest = _segment_digest(messages)
    cached = _load_cached_node(cache_dir, digest)
    if cached is not None:
        return cached, True
    category_values = [_message_category(message) for message in messages]
    topics = Counter(term for message in messages for term in topic_terms(message.body))
    signals = [
        MemorySignal(
            source_id=message.source_id,
            created_at=message.created_at.astimezone().isoformat(timespec="minutes"),
            sender=message.sender_display or message.direction or "unknown",
            category=category,
            text=_signal_text(message),
            score=_signal_score(message, category),
        )
        for message, category in zip(messages, category_values)
    ]
    node = MemoryNode(
        digest=digest,
        level=0,
        date_start=min(message.created_at for message in messages).astimezone().isoformat(timespec="minutes"),
        date_end=max(message.created_at for message in messages).astimezone().isoformat(timespec="minutes"),
        represented_messages=sum(max(1, message.recurrence) for message in messages),
        unique_messages=len(messages),
        leaf_segments=1,
        chats=_counter_dict(message.chat_name for message in messages),
        directions=_counter_dict(message.direction for message in messages),
        senders=_counter_dict(message.sender_display for message in messages),
        categories=dict(Counter(category_values)),
        topics=dict(topics.most_common(32)),
        signals=_select_diverse_signals(signals, 32),
    )
    _cache_node(cache_dir, node)
    return node, False


def _merge_counter_dicts(nodes: Sequence[MemoryNode], field: str, limit: int = 40) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for node in nodes:
        counter.update(getattr(node, field))
    return dict(counter.most_common(limit))


def _merge_nodes(nodes: Sequence[MemoryNode]) -> MemoryNode:
    digest = hashlib.sha256(
        (COMPACTION_ALGORITHM + "\0" + "\0".join(node.digest for node in nodes)).encode("utf-8")
    ).hexdigest()
    signals = [signal for node in nodes for signal in node.signals]
    return MemoryNode(
        digest=digest,
        level=max(node.level for node in nodes) + 1,
        date_start=min(node.date_start for node in nodes),
        date_end=max(node.date_end for node in nodes),
        represented_messages=sum(node.represented_messages for node in nodes),
        unique_messages=sum(node.unique_messages for node in nodes),
        leaf_segments=sum(node.leaf_segments for node in nodes),
        chats=_merge_counter_dicts(nodes, "chats"),
        directions=_merge_counter_dicts(nodes, "directions"),
        senders=_merge_counter_dicts(nodes, "senders"),
        categories=_merge_counter_dicts(nodes, "categories"),
        topics=_merge_counter_dicts(nodes, "topics"),
        signals=_select_diverse_signals(signals, 64),
    )


def _hierarchy(leaf_nodes: list[MemoryNode], fanout: int = 6) -> list[list[MemoryNode]]:
    levels = [leaf_nodes]
    while len(levels[-1]) > 1:
        current = levels[-1]
        levels.append(
            [_merge_nodes(current[index : index + fanout]) for index in range(0, len(current), fanout)]
        )
    return levels


def _compact_counter(values: dict[str, int], limit: int) -> str:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return ", ".join(f"{key}({count})" for key, count in ordered) or "none"


def _render_node(node: MemoryNode, max_chars: int) -> str:
    header = (
        f"### {node.date_start[:10]} to {node.date_end[:10]} | "
        f"{node.represented_messages} source messages | {node.leaf_segments} segment(s)"
    )
    fixed = [
        header,
        f"Activity: {_compact_counter(node.directions, 5)}; participants: {_compact_counter(node.senders, 6)}",
        f"Memory signals: {_compact_counter(node.categories, 8)}",
        f"Recurring subjects: {_compact_counter(node.topics, 12)}",
    ]
    used = sum(len(line) + 1 for line in fixed)
    signal_lines: list[str] = []
    ranked = _select_diverse_signals(node.signals, max(1, min(32, max_chars // 180)))
    for signal in ranked:
        line = f"- [{signal.created_at[:10]}] {signal.sender} / {signal.category}: {signal.text}"
        remaining = max_chars - used - len(signal_lines) - 1
        if remaining < 80:
            break
        if len(line) > remaining:
            line = line[: max(40, remaining - 1)].rstrip() + "…"
        signal_lines.append(line)
        used += len(line)
    coverage = (
        f"Coverage: all {node.represented_messages} rows contributed to this node; "
        f"fingerprint={node.digest[:12]}."
    )
    if used + len(coverage) + 1 <= max_chars:
        signal_lines.append(coverage)
    return "\n".join([*fixed, *signal_lines])


def _render_full_memory(
    levels: list[list[MemoryNode]],
    *,
    char_budget: int,
    token_budget: int,
) -> tuple[str, int]:
    header = [
        "# Lifetime memory compaction",
        "",
        "Every authorized source row contributed to this hierarchy. This is a lossy semantic compaction, not a claim that every exact sentence fits in the model window. Use the high-fidelity excerpts or immutable history database when exact wording matters.",
        "Current messages and interruptions remain authoritative; memory cannot authorize or revive old work.",
        "",
    ]
    header_text = "\n".join(header)
    chosen_index = len(levels) - 1
    rendered = ""
    for index, nodes in enumerate(levels):
        available = max(500, char_budget - len(header_text))
        per_node = available // max(1, len(nodes)) - 2
        if per_node < 420 and len(nodes) > 1:
            continue
        candidate = header_text + "\n\n".join(
            _render_node(node, max(300, per_node)) for node in nodes
        )
        if len(candidate) <= char_budget and estimate_tokens(candidate) <= token_budget:
            chosen_index = index
            rendered = candidate
            break
    if not rendered:
        node = levels[-1][0]
        target_chars = max(500, char_budget - len(header_text))
        rendered = header_text + _render_node(node, target_chars)
    while estimate_tokens(rendered) > token_budget or len(rendered) > char_budget:
        target_chars = max(500, int((len(rendered) - len(header_text)) * 0.82))
        rendered = header_text + _render_node(levels[chosen_index][0], target_chars)
        if target_chars <= 500:
            break
    return rendered[:char_budget].rstrip(), chosen_index


def score_history(
    messages: list[HistoryMessage], query: str
) -> tuple[dict[int, float], Counter[str]]:
    query_terms = lexical_terms(query)
    document_terms = {message.source_id: lexical_terms(message.body) for message in messages}
    frequencies = Counter(
        term for terms in document_terms.values() for term in query_terms.intersection(terms)
    )
    scores: dict[int, float] = {}
    for message in messages:
        overlap = query_terms.intersection(document_terms[message.source_id])
        lexical = sum(
            math.log((len(messages) + 1) / (frequencies[term] + 1)) + 1.0
            for term in overlap
        )
        category = _message_category(message)
        scores[message.source_id] = lexical * 2.0 + _signal_score(message, category) * 0.35
    return scores, frequencies


def format_message(message: HistoryMessage, max_chars: int) -> str:
    body = message.body
    if len(body) > max_chars:
        head = max_chars * 2 // 3
        tail = max_chars - head - 1
        body = f"{body[:head].rstrip()}…{body[-tail:].lstrip()}"
    local = message.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
    sender = f" / {message.sender_display}" if message.sender_display else ""
    repeated = f" / repeated={message.recurrence}" if message.recurrence > 1 else ""
    return f"- [{local}] {message.chat_name} / {message.direction}{sender}{repeated}: {body}"


def neighboring_messages(
    anchors: Iterable[HistoryMessage],
    corpus: list[HistoryMessage],
    *,
    window_seconds: int,
) -> list[HistoryMessage]:
    by_chat: dict[str, list[HistoryMessage]] = defaultdict(list)
    for message in corpus:
        by_chat[message.chat_name].append(message)
    neighbors: dict[int, HistoryMessage] = {}
    for anchor in anchors:
        for message in by_chat[anchor.chat_name]:
            if abs((message.created_at - anchor.created_at).total_seconds()) <= window_seconds:
                neighbors[message.source_id] = message
    return sorted(neighbors.values(), key=lambda item: (item.created_at, item.source_id))


def _render_exact_excerpts(
    messages: list[HistoryMessage],
    query: str,
    *,
    char_budget: int,
    token_budget: int,
) -> tuple[str, list[int], Counter[str]]:
    scores, frequencies = score_history(messages, query)
    ranked = sorted(
        messages,
        key=lambda item: (scores[item.source_id], item.created_at, item.source_id),
        reverse=True,
    )
    anchors = ranked[: max(4, min(24, len(ranked)))]
    candidates = [
        *anchors,
        *neighboring_messages(
            anchors,
            messages,
            window_seconds=int(os.environ.get("WECHAT_HISTORY_RAG_NEIGHBOR_SECONDS", "1800")),
        ),
    ]
    used: set[int] = set()
    lines = [
        "# High-fidelity query excerpts",
        "",
        "These are exact-history excerpts selected for the current task. They supplement, but do not replace, the lifetime compaction above.",
    ]
    per_message = min(2400, max(320, char_budget // 5))
    for message in candidates:
        if message.source_id in used:
            continue
        line = format_message(message, per_message)
        candidate = "\n".join([*lines, line])
        if len(candidate) > char_budget or estimate_tokens(candidate) > token_budget:
            continue
        lines.append(line)
        used.add(message.source_id)
    return "\n".join(lines).strip(), sorted(used), frequencies


def _source_fingerprint(messages: Sequence[HistoryMessage]) -> str:
    digest = hashlib.sha256()
    for message in messages:
        for source_id in message.source_ids or (message.source_id,):
            digest.update(str(source_id).encode("ascii"))
            digest.update(b",")
        digest.update(hashlib.sha256(message.body.encode("utf-8")).digest())
    return digest.hexdigest()


def build_context_from_messages(
    raw_messages: Iterable[HistoryMessage],
    query: str,
    *,
    char_budget: int | None = None,
    token_budget: int | None = None,
    model: str = "",
    role: str = "task",
    cache_dir: Path | None = None,
    policy_path: Path = MODEL_POLICY,
) -> dict[str, object]:
    """Compact the full corpus, then add query-specific exact excerpts."""

    budget = resolve_memory_budget(
        model=model,
        role=role,
        token_budget=token_budget,
        char_budget=char_budget,
        policy_path=policy_path,
    )
    total_char_budget = int(budget["memory_char_budget"])
    total_token_budget = int(budget["memory_token_budget"])
    raw_messages = list(raw_messages)
    messages = deduplicate_history(raw_messages)
    if not messages:
        return {
            "full_memory": "(no lifetime chat history found)",
            "high_fidelity_excerpts": "",
            "snapshot": "(no lifetime chat history found)",
            "manifest": {
                "schema": COMPACTION_SCHEMA,
                "scanned_messages": 0,
                "represented_messages": 0,
                "coverage_ratio": 1.0,
                "unique_messages": 0,
                "selected_messages": 0,
                **budget,
            },
        }

    leaf_nodes: list[MemoryNode] = []
    cache_hits = 0
    for segment in _segment_messages(messages):
        node, hit = _leaf_node(segment, cache_dir)
        leaf_nodes.append(node)
        cache_hits += int(hit)
    levels = _hierarchy(leaf_nodes)
    full_fraction = float(budget["full_memory_fraction"])
    full_char_budget = max(1200, int(total_char_budget * full_fraction))
    full_token_budget = max(700, int(total_token_budget * full_fraction))
    excerpt_char_budget = max(800, total_char_budget - full_char_budget - 2)
    excerpt_token_budget = max(500, total_token_budget - full_token_budget)
    full_memory, selected_level = _render_full_memory(
        levels,
        char_budget=full_char_budget,
        token_budget=full_token_budget,
    )
    excerpts, excerpt_ids, frequencies = _render_exact_excerpts(
        messages,
        query,
        char_budget=excerpt_char_budget,
        token_budget=excerpt_token_budget,
    )
    snapshot = f"{full_memory}\n\n{excerpts}".strip()
    if len(snapshot) > total_char_budget:
        snapshot = snapshot[:total_char_budget].rstrip()

    represented = sum(node.represented_messages for node in leaf_nodes)
    first = min(message.created_at for message in messages).astimezone().isoformat(timespec="minutes")
    last = max(message.created_at for message in messages).astimezone().isoformat(timespec="minutes")
    manifest = {
        "schema": COMPACTION_SCHEMA,
        "algorithm": COMPACTION_ALGORITHM,
        "scanned_messages": len(raw_messages),
        "represented_messages": represented,
        "coverage_ratio": represented / len(raw_messages) if raw_messages else 1.0,
        "unique_messages": len(messages),
        "selected_messages": len(excerpt_ids),
        "exact_excerpt_source_ids": excerpt_ids,
        "authorized_chats": sorted({item.chat_name for item in messages}),
        "date_start": first,
        "date_end": last,
        "leaf_segments": len(leaf_nodes),
        "compaction_levels": len(levels),
        "selected_compaction_level": selected_level,
        "cache_hits": cache_hits,
        "cache_misses": len(leaf_nodes) - cache_hits,
        "source_fingerprint": _source_fingerprint(messages),
        "full_memory_chars": len(full_memory),
        "full_memory_estimated_tokens": estimate_tokens(full_memory),
        "excerpt_chars": len(excerpts),
        "excerpt_estimated_tokens": estimate_tokens(excerpts),
        "snapshot_chars": len(snapshot),
        "snapshot_estimated_tokens": estimate_tokens(snapshot),
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "query_term_hits": dict(frequencies.most_common(24)),
        **budget,
    }
    return {
        "full_memory": full_memory,
        "high_fidelity_excerpts": excerpts,
        "snapshot": snapshot,
        "manifest": manifest,
    }


def _default_cache_dir(db: Path) -> Path:
    return db.parent / "history_compaction_cache"


def build_history_context(
    db: Path,
    chats: Iterable[str],
    query: str,
    *,
    char_budget: int | None = None,
    token_budget: int | None = None,
    model: str = "",
    role: str = "task",
    cache_dir: Path | None = None,
    directions: Iterable[str] | None = None,
) -> dict[str, object]:
    """Build lifetime memory from the complete authorized personal-WeChat corpus."""

    payload = build_context_from_messages(
        load_history(db, chats, directions=directions),
        query,
        char_budget=char_budget,
        token_budget=token_budget,
        model=model,
        role=role,
        cache_dir=cache_dir if cache_dir is not None else _default_cache_dir(db),
    )
    manifest = payload.get("manifest")
    if isinstance(manifest, dict):
        manifest["authorized_directions"] = sorted(
            {
                str(direction).strip().casefold()
                for direction in (directions or ())
                if str(direction).strip()
            }
        ) or ["all"]
    return payload


def build_wecom_history_context(
    db: Path,
    chats: Iterable[str],
    query: str,
    *,
    char_budget: int | None = None,
    token_budget: int | None = None,
    model: str = "",
    role: str = "task",
    cache_dir: Path | None = None,
) -> dict[str, object]:
    """Build lifetime memory from the complete authorized WeCom corpus."""

    return build_context_from_messages(
        load_wecom_history(db, chats),
        query,
        char_budget=char_budget,
        token_budget=token_budget,
        model=model,
        role=role,
        cache_dir=cache_dir if cache_dir is not None else _default_cache_dir(db),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--chat", action="append", dest="chats", default=[], required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--role", default="task")
    parser.add_argument("--char-budget", type=int, default=0)
    parser.add_argument("--token-budget", type=int, default=0)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_history_context(
        args.db,
        args.chats,
        args.query,
        char_budget=args.char_budget or None,
        token_budget=args.token_budget or None,
        model=args.model,
        role=args.role,
        cache_dir=None if args.no_cache else _default_cache_dir(args.db),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["snapshot"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
