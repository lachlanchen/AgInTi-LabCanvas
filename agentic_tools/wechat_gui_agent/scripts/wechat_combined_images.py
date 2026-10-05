"""Native merged-display membership; never infer an album from nearby files."""

import xml.etree.ElementTree as ET

MAX_GROUP_ITEMS = 100
MAX_XML_CHARS = 2_000_000


def combined_image_group(content):
    text = str(content or "")
    if len(text) > MAX_XML_CHARS or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return None
    start = text.find("<msg")
    if start < 0:
        return None
    try:
        root = ET.fromstring(text[start:])
    except ET.ParseError:
        return None
    group = root.find("./extcommoninfo/groupinfo")
    if group is None or group.findtext("type") != "1":
        return None
    identity = (group.findtext("id") or "").strip()
    try:
        count = int(group.findtext("count") or "0")
    except ValueError:
        return None
    if not identity or len(identity) > 256 or not 2 <= count <= MAX_GROUP_ITEMS:
        return None
    return {"id": identity, "count": count, "type": "1"}


def same_image_group(left, right):
    return bool(left and right and left == right)
