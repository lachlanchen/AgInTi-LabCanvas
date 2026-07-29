#!/usr/bin/env python3
"""Shared LabCanvas capabilities with small per-chat customizations."""

from __future__ import annotations

from typing import Any
import re


SHARED_CAPABILITIES = (
    "natural_chat",
    "web_and_literature_research",
    "document_archive_image_audio_video_intake",
    "markdown_latex_pdf_writing",
    "editable_figures_and_biorender",
    "presentations",
    "cad_openscad_step_stl_3mf",
    "pcb_kicad_gerber",
    "blender_rendering",
    "story_and_script_writing",
    "image_generation_and_editing",
    "musia_music_generation_and_review",
    "musia_song_first_music_video",
    "video_generation_and_download",
    "lazyedit_video_processing",
    "explicitly_authorized_video_publication",
    "artifact_delivery_to_source_chat",
)

LABAGENT_CAPABILITIES = tuple(
    capability
    for capability in SHARED_CAPABILITIES
    if capability != "explicitly_authorized_video_publication"
)


PROFILES: dict[str, dict[str, Any]] = {
    "lazyresearch": {
        "display_name": "LazyResearch",
        "aliases": ("LazyResearch", "懒人科研"),
        "session_scope": "懒人科研",
        "template_profile": True,
        "template_family": "omnipotent_labcanvas",
        "focus": "research_and_general_lab_work",
        "default_behavior": (
            "Act like a capable research collaborator. Answer useful questions directly and "
            "use worker routines for evidence, files, figures, CAD/PCB, media, and reports."
        ),
        "proactive_policy": "Only configured research schedules may speak proactively.",
    },
    "my_devices": {
        "display_name": "🍓My devices",
        "aliases": ("🍓My devices", "🍓我的设备", "My devices", "我的设备"),
        "session_scope": "🍓我的设备",
        "template_profile": True,
        "template_family": "omnipotent_labcanvas",
        "focus": "personal_device_inbox_and_general_work",
        "default_behavior": (
            "Treat ordinary messages as a personal device and daily-work inbox. Explicit "
            "requests may use the complete shared LabCanvas capability set."
        ),
        "proactive_policy": "Do not add unsolicited reports; configured daily routines are separate.",
    },
    "labagent": {
        "display_name": "LabAgent",
        "aliases": ("LabAgent",),
        "session_scope": "LabAgent",
        "template_profile": True,
        "template_family": "omnipotent_labcanvas",
        "focus": "collaborative_research_drawing_and_design",
        "default_behavior": (
            "Act like a capable research and engineering collaborator. Give a prompt natural "
            "answer, run substantial evidence or artifact work when useful, and return the "
            "smallest set of polished deliverables that satisfies the request."
        ),
        "proactive_policy": "Only configured LabAgent research schedules may speak proactively.",
        "capabilities": LABAGENT_CAPABILITIES,
        "restrictions": (
            "Public video publication is disabled for this shared WeCom profile. "
            "Other irreversible actions still require explicit authorization."
        ),
    },
    "shares": {
        "display_name": "Shares鏈接",
        "aliases": ("Shares鏈接", "Shares", "鏈接", "链接"),
        "session_scope": "鏈接",
        "template_profile": False,
        "template_family": "omnipotent_labcanvas",
        "focus": "read_later_and_source_understanding",
        "default_behavior": (
            "For a shared source, try to read the real content and return one concise useful "
            "summary. Keep intermediate notes local and send PDF only when explicitly requested."
        ),
        "proactive_policy": "No unsolicited artifact reports.",
    },
    "writing_money": {
        "display_name": "MEMO写作—外语—挣钱",
        "aliases": (
            "MEMO写作—外语—挣钱",
            "MEMO写作-外语-挣钱",
            "写作 外语 挣钱",
            "写作—外语—挣钱",
            "写作-外语-挣钱",
        ),
        "session_scope": "写作 外语 挣钱",
        "template_profile": False,
        "template_family": "omnipotent_labcanvas",
        "focus": "memo_writing_language_career_and_money",
        "default_behavior": (
            "Organize ordinary notes and help with writing, language, career, products, and "
            "money. Explicit requests may use every shared capability."
        ),
        "proactive_policy": "Only the single configured daily organizer PDF may speak proactively.",
    },
    "echomind": {
        "display_name": "EchoMind",
        "aliases": ("EchoMind",),
        "session_scope": "EchoMind",
        "template_profile": False,
        "template_family": "omnipotent_labcanvas",
        "focus": "multilingual_language_learning",
        "default_behavior": (
            "Turn ordinary text and media into useful Chinese, English, and Japanese teaching. "
            "An explicit tool or artifact request overrides this default focus and must execute."
        ),
        "proactive_policy": (
            "Only the configured three-hour compact lesson and one previous-day 06:00 PDF may "
            "speak proactively."
        ),
    },
    "personal_dm": {
        "display_name": "lachlanchan",
        "aliases": ("lachlanchan", "陈苗", "Lachlan"),
        "session_scope": "lachlanchan",
        "template_profile": False,
        "template_family": "omnipotent_labcanvas",
        "focus": "personal_research_career_and_general_work",
        "default_behavior": (
            "Respond like a private research and life-work collaborator. Explicit requests may "
            "use every shared capability."
        ),
        "proactive_policy": "Only the configured daily career report may speak proactively.",
    },
}


def normalize_chat_title(value: str) -> str:
    """Normalize a display title for profile lookup, never for GUI matching."""

    return re.sub(r"[\s_—–-]+", "", str(value or "")).casefold()


def profile_for_chat(
    chat_name: str,
    *,
    profile_id: str = "",
    chat_purpose: str = "",
    analysis_mode: str = "",
) -> dict[str, Any]:
    """Resolve one profile without allowing aliases to merge transports."""

    selected = str(profile_id or "").strip().casefold()
    if selected not in PROFILES:
        normalized = normalize_chat_title(chat_name)
        for candidate_id, candidate in PROFILES.items():
            if any(normalize_chat_title(alias) == normalized for alias in candidate["aliases"]):
                selected = candidate_id
                break
    if selected not in PROFILES:
        purpose = str(chat_purpose or "").strip().casefold()
        if purpose == "labagent_research_drawing_and_design":
            selected = "labagent"
    if selected in PROFILES:
        raw = PROFILES[selected]
    else:
        purpose = str(chat_purpose or "").strip().casefold()
        mode = str(analysis_mode or "").strip().casefold()
        raw = {
            "display_name": str(chat_name or "chat"),
            "aliases": (str(chat_name or "chat"),),
            "session_scope": str(chat_name or "chat"),
            "template_profile": False,
            "template_family": "omnipotent_labcanvas",
            "focus": mode or purpose or "general_collaboration",
            "default_behavior": (
                "Respond naturally and use the complete shared LabCanvas capability set when "
                "the current request needs tools or artifacts."
            ),
            "proactive_policy": "Only explicitly configured schedules may speak proactively.",
        }
        selected = "custom"
    return {
        "id": selected,
        "display_name": raw["display_name"],
        "current_chat": str(chat_name or raw["display_name"]),
        "aliases": list(raw["aliases"]),
        "session_scope": str(raw["session_scope"]),
        "template_profile": bool(raw.get("template_profile")),
        "template_family": str(raw.get("template_family") or "omnipotent_labcanvas"),
        "focus": str(raw["focus"]),
        "default_behavior": str(raw["default_behavior"]),
        "proactive_policy": str(raw["proactive_policy"]),
        "restrictions": str(raw.get("restrictions") or ""),
        "explicit_request_overrides_focus": True,
        "capabilities": list(raw.get("capabilities") or SHARED_CAPABILITIES),
        "cross_chat_context_allowed": False,
        "cross_chat_artifacts_allowed": False,
    }


def profile_aliases(profile_id: str) -> list[str]:
    raw = PROFILES.get(str(profile_id or "").strip().casefold())
    return list(raw["aliases"]) if raw else []


def preferred_chat_title(profile_id: str) -> str:
    raw = PROFILES.get(str(profile_id or "").strip().casefold())
    return str(raw["display_name"]) if raw else ""
