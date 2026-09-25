"""Recipient addressing for agent-written group replies, not intent routing."""

from __future__ import annotations

import re


GROUP_REPLY_ADDRESSING = (
    "In a group reply to a member's question/request, address the actual people you are "
    "answering with their exact sender_display names: put @Name, or @Name One @Name Two, "
    "on a separate first line, followed by your natural answer. For a combined reply, "
    "include each person whose request you actually answer exactly once, using the "
    "current message ledger and same-chat interruptions, not just the last sender. "
    "Do not tag everyone in recent history, quoted/forwarded authors who did not ask, "
    "the assistant itself, or people from another chat. Never use @all/@所有人. "
    "Do not repeat mentions for each sentence, file, or continuation part. A scheduled "
    "general briefing, DM, silent save or NO_REPLY needs no mention. Keep attribution "
    "correct when answering different people together; do not split one useful answer "
    "into separate messages solely to mention each recipient. If a name is uncertain, "
    "do not invent it or expose an internal account ID."
)


def mention_header(text: str) -> tuple[list[str], str, str]:
    """Parse only an explicit recipient header, never @names inside the answer."""
    original = str(text)
    marker = ""
    value = original
    first, sep, rest = value.partition("\n")
    if re.fullmatch(r"\[\d+/\d+\]", first.strip()) and sep:
        marker = first + "\n"
        value = rest.lstrip("\n")
    header, sep, body = value.partition("\n")
    header = header.strip()
    if not sep or not body.strip() or not header.startswith("@"):
        return [], original, original
    names = [part.strip() for part in re.split(r"\s+@", header[1:])]
    forbidden = {"all", "everyone", "所有人", "全体成员", "全部成员"}
    if any(not name or len(name) > 80 or "@" in name or "＠" in name
           or any(ord(char) < 32 for char in name) or name.casefold() in forbidden for name in names):
        return [], original, original
    names = list(dict.fromkeys(names))
    body = marker + body.lstrip("\n")
    canonical = " ".join("@" + name for name in names) + "\n" + body
    return names, body, canonical


def mention_picker_box(before, after, window, content_left):
    """Isolate a newly opened small picker; reject an unchanged or shifting chat."""
    from PIL import Image, ImageChops

    # The picker anchors beside the editor's left edge. Exclude the unrelated
    # history scrollbar and right-hand bubbles, which can repaint on focus.
    region = (max(window.x, content_left - 100), window.y + window.height - 500,
              min(window.x + window.width - 10, content_left + 350),
              window.y + window.height - 150)
    with Image.open(before) as a, Image.open(after) as b:
        if a.size != b.size or region[1] < 0:
            return None
        delta = ImageChops.difference(a.convert("RGB").crop(region), b.convert("RGB").crop(region))
        box = delta.convert("L").point(lambda v: 255 if v > 15 else 0).getbbox()
    if not box:
        return None
    left, top, right, bottom = box
    if not (80 <= right - left <= 350 and 20 <= bottom - top <= 350):
        return None
    if region[3] - (region[1] + bottom) > 35:
        return None
    # Native rows have an avatar before the full member label.
    return region[0] + left + 40, region[1] + top, right - left - 40, bottom - top
