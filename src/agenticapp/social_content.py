from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
from typing import Any, Callable, Iterable
import uuid

from .workspace_agent import run_backend_turn, select_agent_policy


DEFAULT_STORAGE_DIR = Path("output/social")
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_EFFORT = "ultra"

PLATFORM_POLICIES: dict[str, dict[str, Any]] = {
    "x": {
        "label": "X",
        "write_providers": ["postiz", "x-mcp"],
        "agent_drafting": True,
        "max_chars": 280,
        "notes": "Prefer one concise post or a short thread. Do not automate replies, follows, likes, or DMs.",
    },
    "reddit": {
        "label": "Reddit",
        "write_providers": ["postiz"],
        "agent_drafting": True,
        "notes": "Review the exact community rules before approval. Write a community-specific post, not a copied advertisement.",
    },
    "bluesky": {
        "label": "Bluesky",
        "write_providers": ["postiz", "atproto"],
        "agent_drafting": True,
        "max_chars": 300,
        "notes": "Use a concise technical or learner-facing post with useful alt text for media.",
    },
    "mastodon": {
        "label": "Mastodon",
        "write_providers": ["postiz", "mastodon-api"],
        "agent_drafting": True,
        "max_chars": 500,
        "notes": "Respect the selected instance's local rules and use content warnings when appropriate.",
    },
    "linkedin": {
        "label": "LinkedIn",
        "write_providers": ["postiz"],
        "agent_drafting": True,
        "max_chars": 3000,
        "notes": "Explain the practical problem, implementation, and who can use it without inflated claims.",
    },
    "devto": {
        "label": "DEV Community",
        "write_providers": ["postiz"],
        "agent_drafting": True,
        "notes": "Use a substantive technical article or release note, not a thin link post.",
    },
    "hackernews": {
        "label": "Hacker News",
        "write_providers": ["manual-browser"],
        "agent_drafting": False,
        "notes": "HN forbids generated or AI-edited submission text. The agent may prepare facts and a worksheet only; the human writes the final title and text.",
    },
}

PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "postiz": {
        "label": "Postiz Agent CLI",
        "kind": "multi-platform",
        "command": "postiz",
        "writes": True,
        "auth": "Postiz OAuth or POSTIZ_API_KEY",
        "source": "https://github.com/gitroomhq/postiz-agent",
        "platforms": ["x", "reddit", "bluesky", "mastodon", "linkedin", "devto"],
    },
    "x-mcp": {
        "label": "Official X FastMCP server",
        "kind": "mcp",
        "command": "xmcp-server",
        "writes": True,
        "auth": "X Developer Platform OAuth",
        "source": "https://github.com/xdevplatform/xmcp",
        "platforms": ["x"],
    },
    "hackernews-api": {
        "label": "Official Hacker News API",
        "kind": "read-only-api",
        "command": "",
        "writes": False,
        "auth": "none",
        "source": "https://github.com/HackerNews/API",
        "platforms": ["hackernews"],
    },
    "manual-browser": {
        "label": "Visible browser with human confirmation",
        "kind": "manual",
        "command": "",
        "writes": True,
        "auth": "browser session",
        "source": "",
        "platforms": ["hackernews"],
    },
}


class SocialContentError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_id(value: str, *, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return normalized or fallback


def normalize_platform(value: str) -> str:
    aliases = {
        "twitter": "x",
        "x.com": "x",
        "hn": "hackernews",
        "hacker-news": "hackernews",
        "dev.to": "devto",
    }
    platform = aliases.get(str(value or "").strip().casefold(), str(value or "").strip().casefold())
    if platform not in PLATFORM_POLICIES:
        raise SocialContentError(f"Unsupported platform: {value}")
    return platform


def parse_platform_target(value: str) -> dict[str, str]:
    raw = str(value or "").strip()
    platform, separator, target = raw.partition(":")
    return {"platform": normalize_platform(platform), "target": target.strip() if separator else ""}


def content_fingerprint(draft: dict[str, Any]) -> str:
    payload = {
        "platform": str(draft.get("platform") or ""),
        "target": str(draft.get("target") or ""),
        "title": str(draft.get("title") or ""),
        "body": str(draft.get("body") or ""),
        "media": draft.get("media") if isinstance(draft.get("media"), list) else [],
        "settings": draft.get("settings") if isinstance(draft.get("settings"), dict) else {},
        "metadata": draft.get("metadata") if isinstance(draft.get("metadata"), dict) else {},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SocialStore:
    def __init__(self, storage_dir: str | Path = DEFAULT_STORAGE_DIR):
        self.storage_dir = Path(storage_dir).expanduser().resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.storage_dir / "social-content.sqlite3"
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    repo_url TEXT NOT NULL DEFAULT '',
                    homepage TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    name TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    audience TEXT NOT NULL DEFAULT '',
                    platforms_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    strategy TEXT NOT NULL DEFAULT '',
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    platform TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    media_json TEXT NOT NULL DEFAULT '[]',
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    rationale TEXT NOT NULL DEFAULT '',
                    origin TEXT NOT NULL DEFAULT 'agent',
                    human_authored INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(campaign_id, platform, target)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    token TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL REFERENCES drafts(id),
                    content_hash TEXT NOT NULL,
                    review_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS publications (
                    id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL REFERENCES drafts(id),
                    provider TEXT NOT NULL,
                    integration_id TEXT NOT NULL DEFAULT '',
                    external_id TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    scheduled_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    response_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL DEFAULT '',
                    draft_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analytics_snapshots (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    platform TEXT NOT NULL,
                    integration_id TEXT NOT NULL,
                    days INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS maintenance_reports (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    model TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_project(self, profile: dict[str, Any]) -> dict[str, Any]:
        project_id = safe_id(str(profile.get("id") or profile.get("name") or "project"))
        now = utc_now()
        normalized = dict(profile)
        normalized["id"] = project_id
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects(id, name, repo_path, repo_url, homepage, summary, profile_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    repo_path=excluded.repo_path,
                    repo_url=excluded.repo_url,
                    homepage=excluded.homepage,
                    summary=excluded.summary,
                    profile_json=excluded.profile_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    str(normalized.get("name") or project_id),
                    str(normalized.get("repo_path") or ""),
                    str(normalized.get("repo_url") or ""),
                    str(normalized.get("homepage") or ""),
                    str(normalized.get("summary") or ""),
                    json.dumps(normalized, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (safe_id(project_id),)).fetchone()
        if row is None:
            raise SocialContentError(f"Unknown social project: {project_id}")
        result = dict(row)
        result["profile"] = json.loads(result.pop("profile_json"))
        return result

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [self.get_project(str(row["id"])) for row in rows]

    def create_campaign(
        self,
        *,
        project_id: str,
        name: str,
        objective: str,
        audience: str,
        platforms: list[dict[str, str]],
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
    ) -> dict[str, Any]:
        self.get_project(project_id)
        if not objective.strip():
            raise SocialContentError("Campaign objective cannot be empty")
        normalized_platforms = [
            {"platform": normalize_platform(item["platform"]), "target": str(item.get("target") or "").strip()}
            for item in platforms
        ]
        if not normalized_platforms:
            raise SocialContentError("Campaign requires at least one platform")
        campaign_id = f"{safe_id(name, fallback='campaign')}-{uuid.uuid4().hex[:8]}"
        now = utc_now()
        conversation_id = f"social-{safe_id(project_id)}"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO campaigns(
                    id, project_id, name, objective, audience, platforms_json, model, effort,
                    conversation_id, status, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'briefed', ?, ?)
                """,
                (
                    campaign_id,
                    safe_id(project_id),
                    name.strip(),
                    objective.strip(),
                    audience.strip(),
                    json.dumps(normalized_platforms, ensure_ascii=False),
                    model,
                    effort,
                    conversation_id,
                    now,
                    now,
                ),
            )
        self.add_event(campaign_id=campaign_id, event_type="campaign.created", details={"platforms": normalized_platforms})
        return self.get_campaign(campaign_id)

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if row is None:
            raise SocialContentError(f"Unknown campaign: {campaign_id}")
        result = dict(row)
        result["platforms"] = json.loads(result.pop("platforms_json"))
        result["warnings"] = json.loads(result.pop("warnings_json"))
        return result

    def list_campaigns(self, project_id: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            if project_id:
                rows = connection.execute(
                    "SELECT id FROM campaigns WHERE project_id = ? ORDER BY updated_at DESC", (safe_id(project_id),)
                ).fetchall()
            else:
                rows = connection.execute("SELECT id FROM campaigns ORDER BY updated_at DESC").fetchall()
        return [self.get_campaign(str(row["id"])) for row in rows]

    def update_campaign_generation(self, campaign_id: str, *, strategy: str, warnings: list[str], status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE campaigns SET strategy = ?, warnings_json = ?, status = ?, updated_at = ? WHERE id = ?",
                (strategy, json.dumps(warnings, ensure_ascii=False), status, utc_now(), campaign_id),
            )

    def upsert_draft(self, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        platform = normalize_platform(str(payload.get("platform") or ""))
        target = str(payload.get("target") or "").strip()
        existing = self.find_draft(campaign_id, platform, target)
        draft_id = str(existing.get("id")) if existing else uuid.uuid4().hex[:12]
        draft = {
            "id": draft_id,
            "campaign_id": campaign_id,
            "platform": platform,
            "target": target,
            "title": str(payload.get("title") or "").strip(),
            "body": str(payload.get("body") or "").strip(),
            "media": [str(item) for item in payload.get("media", []) if str(item).strip()],
            "settings": payload.get("settings") if isinstance(payload.get("settings"), dict) else {},
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            "rationale": str(payload.get("rationale") or "").strip(),
            "origin": str(payload.get("origin") or "agent"),
            "human_authored": bool(payload.get("human_authored")),
            "status": str(payload.get("status") or "draft"),
        }
        draft["content_hash"] = content_fingerprint(draft)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO drafts(
                    id, campaign_id, platform, target, title, body, media_json, settings_json,
                    metadata_json, rationale, origin, human_authored, content_hash, status,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id, platform, target) DO UPDATE SET
                    title=excluded.title,
                    body=excluded.body,
                    media_json=excluded.media_json,
                    settings_json=excluded.settings_json,
                    metadata_json=excluded.metadata_json,
                    rationale=excluded.rationale,
                    origin=excluded.origin,
                    human_authored=excluded.human_authored,
                    content_hash=excluded.content_hash,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    draft_id,
                    campaign_id,
                    platform,
                    target,
                    draft["title"],
                    draft["body"],
                    json.dumps(draft["media"], ensure_ascii=False),
                    json.dumps(draft["settings"], ensure_ascii=False, sort_keys=True),
                    json.dumps(draft["metadata"], ensure_ascii=False, sort_keys=True),
                    draft["rationale"],
                    draft["origin"],
                    int(draft["human_authored"]),
                    draft["content_hash"],
                    draft["status"],
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM approvals WHERE draft_id = ?", (draft_id,))
        self.add_event(
            campaign_id=campaign_id,
            draft_id=draft_id,
            event_type="draft.updated" if existing else "draft.created",
            details={"platform": platform, "target": target, "content_hash": draft["content_hash"]},
        )
        return self.get_draft(draft_id)

    def find_draft(self, campaign_id: str, platform: str, target: str = "") -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM drafts WHERE campaign_id = ? AND platform = ? AND target = ?",
                (campaign_id, normalize_platform(platform), target),
            ).fetchone()
        return self.get_draft(str(row["id"])) if row else None

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise SocialContentError(f"Unknown draft: {draft_id}")
        result = dict(row)
        result["media"] = json.loads(result.pop("media_json"))
        result["settings"] = json.loads(result.pop("settings_json"))
        result["metadata"] = json.loads(result.pop("metadata_json"))
        result["human_authored"] = bool(result["human_authored"])
        return result

    def list_drafts(self, campaign_id: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            if campaign_id:
                rows = connection.execute(
                    "SELECT id FROM drafts WHERE campaign_id = ? ORDER BY platform, target", (campaign_id,)
                ).fetchall()
            else:
                rows = connection.execute("SELECT id FROM drafts ORDER BY updated_at DESC").fetchall()
        return [self.get_draft(str(row["id"])) for row in rows]

    def approve(self, draft_id: str, *, review_note: str = "", ttl_hours: int = 24) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        if draft["platform"] == "hackernews" and not draft["human_authored"]:
            raise SocialContentError("Hacker News requires human-authored title and text before approval")
        if not draft["body"] and not draft["title"]:
            raise SocialContentError("Cannot approve an empty draft")
        if draft["status"] == "needs_revision":
            raise SocialContentError("Draft requires revision before approval")
        length_error = _platform_length_error(draft)
        if length_error:
            raise SocialContentError(length_error)
        token = secrets.token_urlsafe(18)
        created = datetime.now(timezone.utc)
        expires = created + timedelta(hours=max(1, ttl_hours))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO approvals(token, draft_id, content_hash, review_note, created_at, expires_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    draft_id,
                    draft["content_hash"],
                    review_note.strip(),
                    created.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
                ),
            )
            connection.execute("UPDATE drafts SET status = 'approved', updated_at = ? WHERE id = ?", (utc_now(), draft_id))
        self.add_event(
            campaign_id=draft["campaign_id"],
            draft_id=draft_id,
            event_type="draft.approved",
            details={"content_hash": draft["content_hash"], "expires_at": expires.isoformat()},
        )
        return {"draft": self.get_draft(draft_id), "approval_token": token, "expires_at": expires.isoformat()}

    def verify_approval(self, draft_id: str, token: str) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE token = ? AND draft_id = ?", (token, draft_id)
            ).fetchone()
        if row is None:
            raise SocialContentError("Approval token does not match this draft")
        approval = dict(row)
        if approval["used_at"]:
            raise SocialContentError("Approval token has already been used")
        expires = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expires:
            raise SocialContentError("Approval token has expired")
        if approval["content_hash"] != draft["content_hash"] or content_fingerprint(draft) != draft["content_hash"]:
            raise SocialContentError("Draft changed after approval; review and approve the new content")
        return approval

    def mark_approval_used(self, token: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE approvals SET used_at = ? WHERE token = ?", (utc_now(), token))

    def record_publication(
        self,
        *,
        draft_id: str,
        provider: str,
        integration_id: str,
        scheduled_at: str,
        status: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        publication_id = uuid.uuid4().hex[:12]
        now = utc_now()
        external_id = _first_string(response, ("id", "postId", "post_id", "releaseId", "release_id"))
        url = _first_string(response, ("url", "permalink", "postUrl", "post_url"))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO publications(
                    id, draft_id, provider, integration_id, external_id, url, scheduled_at,
                    status, response_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    publication_id,
                    draft_id,
                    provider,
                    integration_id,
                    external_id,
                    url,
                    scheduled_at,
                    status,
                    json.dumps(response, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            connection.execute("UPDATE drafts SET status = ?, updated_at = ? WHERE id = ?", (status, now, draft_id))
        return self.get_publication(publication_id)

    def get_publication(self, publication_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM publications WHERE id = ?", (publication_id,)).fetchone()
        if row is None:
            raise SocialContentError(f"Unknown publication: {publication_id}")
        result = dict(row)
        result["response"] = json.loads(result.pop("response_json"))
        return result

    def list_publications(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id FROM publications ORDER BY created_at DESC").fetchall()
        return [self.get_publication(str(row["id"])) for row in rows]

    def record_analytics(
        self,
        *,
        campaign_id: str,
        platform: str,
        integration_id: str,
        days: int,
        payload: Any,
    ) -> dict[str, Any]:
        snapshot_id = uuid.uuid4().hex[:12]
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO analytics_snapshots(id, campaign_id, platform, integration_id, days, payload_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    campaign_id,
                    normalize_platform(platform),
                    integration_id,
                    max(1, int(days)),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
        return {
            "id": snapshot_id,
            "campaign_id": campaign_id,
            "platform": normalize_platform(platform),
            "integration_id": integration_id,
            "days": max(1, int(days)),
            "payload": payload,
            "created_at": created_at,
        }

    def list_analytics(self, campaign_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analytics_snapshots WHERE campaign_id = ? ORDER BY created_at DESC", (campaign_id,)
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def record_maintenance_report(
        self,
        *,
        campaign_id: str,
        model: str,
        effort: str,
        report: dict[str, Any],
        artifact_path: str,
    ) -> dict[str, Any]:
        report_id = uuid.uuid4().hex[:12]
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO maintenance_reports(id, campaign_id, model, effort, report_json, artifact_path, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, campaign_id, model, effort, json.dumps(report, ensure_ascii=False, sort_keys=True), artifact_path, created_at),
            )
        return {
            "id": report_id,
            "campaign_id": campaign_id,
            "model": model,
            "effort": effort,
            "report": report,
            "artifact_path": artifact_path,
            "created_at": created_at,
        }

    def add_event(
        self,
        *,
        event_type: str,
        campaign_id: str = "",
        draft_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO events(campaign_id, draft_id, event_type, details_json, created_at) VALUES(?, ?, ?, ?, ?)",
                (campaign_id, draft_id, event_type, json.dumps(details or {}, ensure_ascii=False), utc_now()),
            )


def discover_project(
    repo_path: str | Path,
    *,
    project_id: str = "",
    name: str = "",
    homepage: str = "",
    summary: str = "",
) -> dict[str, Any]:
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise SocialContentError(f"Repository does not exist: {repo}")
    readme = _first_existing(repo, ("README.md", "README.rst", "README.txt"))
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme else ""
    detected_name = name.strip() or _markdown_title(readme_text) or repo.name
    repo_url = _normalize_git_remote(_git_output(repo, ["remote", "get-url", "origin"]))
    citation = _first_existing(repo, ("CITATION.cff", "citation.cff"))
    citation_text = citation.read_text(encoding="utf-8", errors="replace") if citation else ""
    detected_homepage = homepage.strip() or _yaml_scalar(citation_text, "url") or _first_http_link(readme_text)
    detected_summary = summary.strip() or _readme_summary(readme_text)
    assets = _discover_assets(repo)
    changes = [line for line in _git_output(repo, ["log", "-8", "--date=short", "--pretty=format:%h %ad %s"]).splitlines() if line]
    head = _git_output(repo, ["rev-parse", "HEAD"])
    profile = {
        "id": safe_id(project_id or detected_name),
        "name": detected_name,
        "repo_path": str(repo),
        "repo_url": repo_url,
        "homepage": detected_homepage,
        "summary": detected_summary,
        "default_branch": _git_output(repo, ["branch", "--show-current"]),
        "head": head,
        "readme_path": str(readme.relative_to(repo)) if readme else "",
        "readme_sha256": hashlib.sha256(readme_text.encode("utf-8")).hexdigest() if readme_text else "",
        "citation": _citation_facts(citation_text),
        "recent_changes": changes,
        "media_candidates": assets,
        "evidence_excerpt": readme_text[:18000],
        "discovered_at": utc_now(),
    }
    return profile


def build_campaign_prompt(project: dict[str, Any], campaign: dict[str, Any]) -> str:
    platform_contracts = {
        item["platform"]: {
            "target": item.get("target", ""),
            "policy": PLATFORM_POLICIES[item["platform"]],
        }
        for item in campaign["platforms"]
    }
    evidence = {
        "project": project["profile"],
        "campaign": {
            "id": campaign["id"],
            "name": campaign["name"],
            "objective": campaign["objective"],
            "audience": campaign["audience"],
            "platforms": campaign["platforms"],
        },
        "platform_contracts": platform_contracts,
    }
    return f"""You are the social-content editor for an open-source project. Produce a source-grounded campaign package, not generic marketing copy.

Rules:
1. Use only claims supported by the supplied repository evidence. Never invent usage numbers, users, benchmarks, endorsements, maturity, or capabilities.
2. Tailor each platform independently. Do not paste the same body everywhere.
3. Be useful before promotional: explain the concrete learner/developer problem, what is implemented, and what feedback would help.
4. Avoid hype, engagement bait, mass outreach, vote requests, automated replies, and repetitive cross-posting.
5. Reddit drafts must be specific to the named community and marked `needs_rules_review: true`; do not assume a community permits project promotion.
6. X may use one compact body or a short thread in `metadata.thread`. Include concise alt text when recommending an image.
   Every X body/thread segment must be at most 280 characters. Bluesky must be at most 300 characters. Keep Mastodon at or below the conservative 500-character default unless verified instance settings allow more. LinkedIn must be at most 3000 characters.
7. For Hacker News, do not generate or edit a submission title or body. HN's rules reject generated or AI-edited text. Return empty `title` and `body`, and put only verified facts, technical details, demo checks, and questions for the human author under `metadata.author_worksheet`.
8. Recommend at most two strong media assets per platform and only from `media_candidates`.
9. Return valid JSON only, with no Markdown fence or prose outside the object.

JSON shape:
{{
  "strategy": "short campaign strategy",
  "warnings": ["review items"],
  "drafts": [
    {{
      "platform": "x|reddit|bluesky|mastodon|linkedin|devto|hackernews",
      "target": "exact target from campaign",
      "title": "title where applicable, otherwise empty",
      "body": "platform-specific copy, or empty for Hacker News",
      "media": ["repo-relative asset path"],
      "settings": {{}},
      "metadata": {{"alt_text": "", "thread": [], "needs_rules_review": false}},
      "rationale": "why this fits the audience"
    }}
  ]
}}

Repository and campaign evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""


def generate_campaign_drafts(
    store: SocialStore,
    campaign_id: str,
    *,
    root: str | Path,
    agent_runner: Callable[[str, dict[str, Any]], str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id)
    project = store.get_project(campaign["project_id"])
    prompt = build_campaign_prompt(project, campaign)
    policy = select_agent_policy(
        prompt,
        model=campaign["model"],
        effort=campaign["effort"],
        mode="plan",
        backend="codex",
    )
    policy["fallback_to_aginti"] = False
    if dry_run:
        return {"ok": True, "dry_run": True, "campaign": campaign, "policy": policy, "prompt": prompt}
    runner = agent_runner or (lambda value, context: _run_social_agent(value, context, store=store, root=root))
    raw = runner(prompt, {"campaign": campaign, "policy": policy})
    package = parse_agent_json(raw)
    strategy = str(package.get("strategy") or "").strip()
    warnings = [str(item).strip() for item in package.get("warnings", []) if str(item).strip()]
    requested = {(item["platform"], str(item.get("target") or "")) for item in campaign["platforms"]}
    returned: set[tuple[str, str]] = set()
    drafts: list[dict[str, Any]] = []
    for item in package.get("drafts", []):
        if not isinstance(item, dict):
            continue
        platform = normalize_platform(str(item.get("platform") or ""))
        target = str(item.get("target") or "").strip()
        key = (platform, target)
        if key not in requested:
            warnings.append(f"Ignored unrequested draft for {platform}:{target}")
            continue
        returned.add(key)
        normalized = dict(item)
        normalized.update({"platform": platform, "target": target, "origin": "agent", "human_authored": False})
        normalized["media"] = _resolve_agent_media(project, normalized.get("media"), warnings)
        if platform == "hackernews":
            worksheet = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
            normalized.update({"title": "", "body": "", "status": "author_worksheet"})
            worksheet["human_authorship_required"] = True
            normalized["metadata"] = worksheet
        elif not str(normalized.get("body") or "").strip():
            warnings.append(f"Agent returned an empty {platform}:{target} draft")
            normalized["status"] = "needs_revision"
        _apply_platform_length_contract(normalized, warnings)
        drafts.append(store.upsert_draft(campaign_id, normalized))
    missing = requested - returned
    warnings.extend(f"Missing agent draft for {platform}:{target}" for platform, target in sorted(missing))
    _append_duplicate_warnings(drafts, warnings)
    store.update_campaign_generation(
        campaign_id,
        strategy=strategy,
        warnings=warnings,
        status="drafted" if drafts and not missing else "needs_revision",
    )
    store.add_event(
        campaign_id=campaign_id,
        event_type="campaign.drafted",
        details={"draft_ids": [item["id"] for item in drafts], "warnings": warnings},
    )
    return {"ok": bool(drafts), "campaign": store.get_campaign(campaign_id), "drafts": drafts, "warnings": warnings}


def import_human_draft(
    store: SocialStore,
    *,
    campaign_id: str,
    platform: str,
    target: str,
    title: str,
    body: str,
    media: Iterable[str] = (),
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id)
    normalized_platform = normalize_platform(platform)
    requested = {(item["platform"], str(item.get("target") or "")) for item in campaign["platforms"]}
    if (normalized_platform, target) not in requested:
        raise SocialContentError(f"Campaign does not include {normalized_platform}:{target}")
    return store.upsert_draft(
        campaign_id,
        {
            "platform": normalized_platform,
            "target": target,
            "title": title,
            "body": body,
            "media": list(media),
            "settings": settings or {},
            "metadata": {"human_authorship_confirmed": True},
            "rationale": "Human-authored or human-revised final copy.",
            "origin": "human",
            "human_authored": True,
            "status": "draft",
        },
    )


def export_campaign(store: SocialStore, campaign_id: str, output_dir: str | Path) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id)
    project = store.get_project(campaign["project_id"])
    drafts = store.list_drafts(campaign_id)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    manifest = {"campaign": campaign, "project": project, "drafts": drafts, "exported_at": utc_now()}
    manifest_path = destination / "campaign.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files.append(str(manifest_path))
    for draft in drafts:
        suffix = safe_id(draft["target"], fallback="default")
        path = destination / f"{draft['platform']}-{suffix}.md"
        if draft["platform"] == "hackernews" and not draft["human_authored"]:
            body = _hackernews_worksheet_markdown(draft)
        else:
            body = _draft_markdown(draft)
        path.write_text(body.rstrip() + "\n", encoding="utf-8")
        files.append(str(path))
    return {"ok": True, "campaign": campaign, "files": files}


def provider_status(*, probe: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for provider_id, item in PROVIDER_REGISTRY.items():
        status = dict(item)
        status["id"] = provider_id
        command = str(item.get("command") or "")
        status["resolved_command"] = _resolve_provider_command(command) if command else ""
        status["installed"] = bool(status["resolved_command"]) if command else True
        status["configured"] = _provider_configured(provider_id)
        if probe and provider_id == "postiz" and status["installed"]:
            checked = _run_json_command([status["resolved_command"], "auth:status"], timeout=30, check=False)
            status["probe"] = checked
        result.append(status)
    return result


def postiz_integrations(*, command_runner: Callable[..., dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    command = _resolve_provider_command("postiz")
    if not command and command_runner is None:
        raise SocialContentError("Postiz CLI is not installed; run the social tool installer first")
    runner = command_runner or _run_json_command
    result = runner([command or "postiz", "integrations:list"], timeout=60, check=True)
    payload = result.get("json")
    if not isinstance(payload, list):
        raise SocialContentError(f"Unexpected Postiz integrations response: {result.get('stdout', '')[-500:]}")
    return [item for item in payload if isinstance(item, dict)]


def postiz_analytics(
    integration_id: str,
    *,
    days: int = 30,
    command_runner: Callable[..., dict[str, Any]] | None = None,
) -> Any:
    if not integration_id.strip():
        raise SocialContentError("Postiz integration id is required")
    command = _resolve_provider_command("postiz")
    if not command and command_runner is None:
        raise SocialContentError("Postiz CLI is not installed; run the social tool installer first")
    runner = command_runner or _run_json_command
    result = runner(
        [command or "postiz", "analytics:platform", integration_id, "-d", str(max(1, int(days)))],
        timeout=90,
        check=True,
    )
    if result.get("json") is None:
        raise SocialContentError(f"Unexpected Postiz analytics response: {str(result.get('stdout') or '')[-500:]}")
    return result["json"]


def maintain_campaign(
    store: SocialStore,
    campaign_id: str,
    *,
    integrations: dict[str, str],
    days: int,
    root: str | Path,
    agent_runner: Callable[[str, dict[str, Any]], str] | None = None,
    analytics_runner: Callable[..., dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id)
    project = store.get_project(campaign["project_id"])
    integration_map = {normalize_platform(platform): value for platform, value in integrations.items() if value}
    local_evidence = {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "repo_url": project["repo_url"],
            "homepage": project["homepage"],
            "summary": project["summary"],
            "head": project["profile"].get("head", ""),
            "recent_changes": project["profile"].get("recent_changes", []),
        },
        "campaign": campaign,
        "drafts": store.list_drafts(campaign_id),
        "publications": [
            item for item in store.list_publications() if store.get_draft(item["draft_id"])["campaign_id"] == campaign_id
        ],
        "previous_analytics": store.list_analytics(campaign_id)[:20],
    }
    prompt = build_maintenance_prompt(local_evidence, integrations=integration_map, days=days)
    policy = select_agent_policy(
        prompt,
        model=campaign["model"],
        effort=campaign["effort"],
        mode="plan",
        backend="codex",
    )
    policy["fallback_to_aginti"] = False
    if dry_run:
        return {"ok": True, "dry_run": True, "campaign": campaign, "policy": policy, "prompt": prompt, "integrations": integration_map}

    snapshots: list[dict[str, Any]] = []
    for platform, integration_id in integration_map.items():
        payload = postiz_analytics(integration_id, days=days, command_runner=analytics_runner)
        snapshots.append(
            store.record_analytics(
                campaign_id=campaign_id,
                platform=platform,
                integration_id=integration_id,
                days=days,
                payload=payload,
            )
        )
    evidence = dict(local_evidence)
    evidence["current_analytics"] = snapshots
    prompt = build_maintenance_prompt(evidence, integrations=integration_map, days=days)
    runner = agent_runner or (lambda value, context: _run_social_agent(value, context, store=store, root=root))
    raw = runner(prompt, {"campaign": campaign, "policy": policy})
    report = _parse_maintenance_json(raw)
    reports_dir = store.storage_dir / "maintenance" / campaign_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifact = reports_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    artifact.write_text(_maintenance_markdown(campaign, report, snapshots), encoding="utf-8")
    stored = store.record_maintenance_report(
        campaign_id=campaign_id,
        model=policy["model"],
        effort=policy["reasoning_effort"],
        report=report,
        artifact_path=str(artifact),
    )
    store.add_event(
        campaign_id=campaign_id,
        event_type="campaign.maintained",
        details={"report_id": stored["id"], "analytics_snapshot_ids": [item["id"] for item in snapshots]},
    )
    return {"ok": True, "campaign": campaign, "maintenance": stored, "analytics": snapshots}


def build_maintenance_prompt(evidence: dict[str, Any], *, integrations: dict[str, str], days: int) -> str:
    return f"""You are maintaining an open-source project's social content program. Analyze the real local campaign state and any provider analytics. Recommend high-value next actions without posting, replying, voting, following, or changing external state.

Rules:
1. Separate observed evidence from inference. Do not invent metrics when analytics are absent.
2. Prefer a few substantive follow-ups over a high posting frequency. Never recommend repetitive cross-posts, unsolicited outreach, engagement bait, or automated comments.
3. Diagnose weak positioning, unclear claims, poor media, platform mismatch, unanswered technical questions, or missing documentation.
4. Ground recommendations in the current repository changes and campaign history.
5. Hacker News remains human-authored and manual-only. Do not generate HN title/body text.
6. Return JSON only. Do not modify drafts or publish anything.

JSON shape:
{{
  "summary": "concise state assessment",
  "observations": [{{"evidence": "measured fact", "meaning": "careful interpretation"}}],
  "next_actions": [{{"priority": 1, "action": "specific action", "reason": "why", "requires_human": true}}],
  "content_gaps": ["missing proof or documentation"],
  "stop_doing": ["low-value or risky behavior to avoid"],
  "followup_campaign_briefs": [{{"name": "short name", "objective": "grounded objective", "platforms": ["x"]}}]
}}

Analytics window: {max(1, int(days))} days
Connected integration map: {json.dumps(integrations, ensure_ascii=False, sort_keys=True)}

Evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""


def publish_draft(
    store: SocialStore,
    draft_id: str,
    *,
    provider: str,
    integration_id: str,
    approval_token: str,
    schedule_at: str = "",
    live: bool = False,
    command_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    draft = store.get_draft(draft_id)
    if not live:
        return {
            "ok": True,
            "dry_run": True,
            "draft": draft,
            "provider": provider,
            "integration_id": integration_id,
            "schedule_at": schedule_at,
            "content_hash": draft["content_hash"],
            "requires_live_flag": True,
            "requires_exact_approval": True,
        }
    if provider != "postiz":
        raise SocialContentError("Live publication currently supports Postiz only; use export/manual review for other providers")
    if draft["platform"] == "hackernews":
        raise SocialContentError("Hacker News submission is manual-only and must remain human-authored")
    if not integration_id.strip():
        raise SocialContentError("Postiz integration id is required")
    store.verify_approval(draft_id, approval_token)
    scheduled = schedule_at.strip() or (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds").replace("+00:00", "Z")
    command = _postiz_create_command(draft, integration_id=integration_id, schedule_at=scheduled)
    runner = command_runner or _run_json_command
    result = runner(command, timeout=180, check=False)
    if int(result.get("returncode", 1)) != 0:
        store.add_event(
            campaign_id=draft["campaign_id"],
            draft_id=draft_id,
            event_type="publication.failed",
            details={"provider": provider, "error": str(result.get("stderr") or result.get("stdout") or "")[-1000:]},
        )
        raise SocialContentError(f"Postiz publication failed: {str(result.get('stderr') or result.get('stdout') or '')[-800:]}")
    response = result.get("json") if isinstance(result.get("json"), dict) else {"stdout": result.get("stdout", "")}
    publication = store.record_publication(
        draft_id=draft_id,
        provider=provider,
        integration_id=integration_id,
        scheduled_at=scheduled,
        status="scheduled",
        response=response,
    )
    store.mark_approval_used(approval_token)
    store.add_event(
        campaign_id=draft["campaign_id"],
        draft_id=draft_id,
        event_type="publication.scheduled",
        details={"provider": provider, "publication_id": publication["id"], "scheduled_at": scheduled},
    )
    return {"ok": True, "publication": publication, "draft": store.get_draft(draft_id)}


def parse_agent_json(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, count=1, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value, count=1)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", value):
        try:
            payload, _ = decoder.raw_decode(value[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            if not isinstance(payload.get("drafts"), list):
                raise SocialContentError("Agent response JSON does not contain a drafts array")
            return payload
    raise SocialContentError("Agent did not return a valid campaign JSON object")


def _parse_maintenance_json(text: str) -> dict[str, Any]:
    payload = _parse_embedded_json(str(text or ""))
    if not isinstance(payload, dict) or not isinstance(payload.get("next_actions"), list):
        raise SocialContentError("Maintenance agent did not return the required JSON report")
    return payload


def _run_social_agent(prompt: str, context: dict[str, Any], *, store: SocialStore, root: str | Path) -> str:
    campaign = context["campaign"]
    policy = dict(context["policy"])
    policy["sandbox"] = "read-only"
    policy["mode"] = "plan"
    policy["fallback_to_aginti"] = False
    run_dir = store.storage_dir / "agent-runs" / f"{campaign['id']}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    result = run_backend_turn(
        prompt,
        policy=policy,
        conversation_id=campaign["conversation_id"],
        task_dir=run_dir,
        storage_dir=store.storage_dir,
        root=Path(root).resolve(),
        pid_callback=None,
    )
    raw = str(result.get("message") or "").strip()
    (run_dir / "response.txt").write_text(raw + ("\n" if raw else ""), encoding="utf-8")
    if not result.get("ok"):
        raise SocialContentError(f"Social drafting agent failed: {str(result.get('stderr_tail') or result.get('error') or '')[-1000:]}")
    return raw


def _postiz_create_command(draft: dict[str, Any], *, integration_id: str, schedule_at: str) -> list[str]:
    executable = _resolve_provider_command("postiz") or "postiz"
    command = [executable, "posts:create", "-c", draft["body"], "-s", schedule_at, "-i", integration_id]
    media = [str(Path(item).expanduser()) for item in draft.get("media", [])]
    if media:
        missing = [item for item in media if not Path(item).is_file()]
        if missing:
            raise SocialContentError(f"Media file does not exist: {missing[0]}")
        command.extend(["-m", ",".join(media)])
    thread = draft.get("metadata", {}).get("thread", []) if isinstance(draft.get("metadata"), dict) else []
    for segment in thread if isinstance(thread, list) else []:
        text = str(segment or "").strip()
        if text:
            command.extend(["-c", text])
    settings = dict(draft.get("settings") or {})
    if draft["platform"] == "reddit":
        subreddit = str(draft.get("target") or "").removeprefix("r/")
        if not subreddit:
            raise SocialContentError("Reddit draft requires a target subreddit")
        settings.setdefault(
            "subreddit",
            [{"value": {"subreddit": subreddit, "title": draft.get("title") or "", "type": "text"}}],
        )
    if settings:
        command.extend(["--settings", json.dumps(settings, ensure_ascii=False, separators=(",", ":"))])
    return command


def _run_json_command(command: list[str], *, timeout: int, check: bool) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    stdout = completed.stdout.strip()
    payload: Any = None
    if stdout:
        payload = _parse_embedded_json(stdout)
    result = {
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": completed.stderr.strip(),
        "json": payload,
    }
    if check and completed.returncode != 0:
        raise SocialContentError(f"Command failed: {completed.stderr.strip() or stdout}")
    return result


def _provider_configured(provider_id: str) -> bool:
    if provider_id == "postiz":
        # Postiz Agent stores OAuth credentials in ~/.postiz/credentials.json.
        return bool(
            os.environ.get("POSTIZ_API_KEY")
            or (Path.home() / ".postiz" / "credentials.json").is_file()
        )
    if provider_id == "x-mcp":
        required = ("X_OAUTH_CONSUMER_KEY", "X_OAUTH_CONSUMER_SECRET", "X_BEARER_TOKEN")
        return all(os.environ.get(item) for item in required)
    return True


def _resolve_provider_command(command: str) -> str:
    if not command:
        return ""
    resolved = shutil.which(command)
    if resolved:
        return resolved
    local = Path.home() / ".local" / "bin" / command
    return str(local) if local.is_file() and os.access(local, os.X_OK) else ""


def _git_output(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, timeout=20)
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _normalize_git_remote(value: str) -> str:
    remote = value.strip()
    match = re.fullmatch(r"git@github\.com:(.+?)(?:\.git)?", remote)
    if match:
        return f"https://github.com/{match.group(1).removesuffix('.git')}"
    return remote.removesuffix(".git")


def _first_existing(root: Path, names: Iterable[str]) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    return None


def _markdown_title(text: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _readme_summary(text: str) -> str:
    title_match = re.search(r"(?m)^#\s+.+?$", text)
    remainder = text[title_match.end() :] if title_match else text
    paragraphs = re.split(r"\n\s*\n", remainder)
    for paragraph in paragraphs:
        candidate = " ".join(line.strip() for line in paragraph.splitlines()).strip()
        if not candidate or candidate.startswith(("[", "!", "<", "#", "|", "```")):
            continue
        candidate = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", candidate)
        if len(candidate) >= 40:
            return candidate[:1000]
    return ""


def _first_http_link(text: str) -> str:
    preferred = re.search(r"https://(?:learn\.)?lazying\.art[^)\s]*", text)
    if preferred:
        return preferred.group(0)
    match = re.search(r"https://[^)\s]+", text)
    return match.group(0) if match else ""


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text)
    return match.group(1).strip() if match else ""


def _citation_facts(text: str) -> dict[str, str]:
    return {key: _yaml_scalar(text, key) for key in ("title", "version", "date-released", "abstract", "repository-code", "url") if _yaml_scalar(text, key)}


def _discover_assets(repo: Path) -> list[str]:
    patterns = (
        "studio/docs/images/*.png",
        "assets/edition-comparisons/*.png",
        "assets/*showcase*.png",
        "docs/images/*.png",
        "screenshots/*.png",
    )
    found: list[str] = []
    for pattern in patterns:
        for path in sorted(repo.glob(pattern)):
            if path.is_file():
                relative = path.relative_to(repo).as_posix()
                if relative not in found:
                    found.append(relative)
    return found[:20]


def _append_duplicate_warnings(drafts: list[dict[str, Any]], warnings: list[str]) -> None:
    seen: dict[str, str] = {}
    for draft in drafts:
        body = re.sub(r"\s+", " ", str(draft.get("body") or "")).strip().casefold()
        if not body:
            continue
        if body in seen:
            warnings.append(f"Draft bodies for {seen[body]} and {draft['platform']} are identical; tailor them before approval")
        else:
            seen[body] = draft["platform"]


def _apply_platform_length_contract(draft: dict[str, Any], warnings: list[str]) -> None:
    error = _platform_length_error(draft)
    if error:
        draft["status"] = "needs_revision"
        warnings.append(error)


def _platform_length_error(draft: dict[str, Any]) -> str:
    platform = normalize_platform(str(draft.get("platform") or ""))
    limit = int(PLATFORM_POLICIES[platform].get("max_chars") or 0)
    if not limit:
        return ""
    parts = [("body", str(draft.get("body") or ""))]
    metadata = draft.get("metadata") if isinstance(draft.get("metadata"), dict) else {}
    thread = metadata.get("thread") if isinstance(metadata.get("thread"), list) else []
    parts.extend((f"thread[{index}]", str(value or "")) for index, value in enumerate(thread))
    for label, text in parts:
        if len(text) > limit:
            return f"{platform} {label} has {len(text)} characters; conservative limit is {limit}"
    return ""


def _parse_embedded_json(text: str) -> Any:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text):
        try:
            payload, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        return payload
    return None


def _resolve_agent_media(project: dict[str, Any], values: Any, warnings: list[str]) -> list[str]:
    repo = Path(str(project.get("repo_path") or ""))
    allowed = {str(item) for item in project.get("profile", {}).get("media_candidates", [])}
    resolved: list[str] = []
    for value in values if isinstance(values, list) else []:
        candidate = str(value or "").strip()
        if not candidate:
            continue
        if candidate not in allowed:
            warnings.append(f"Ignored media outside discovered project assets: {candidate}")
            continue
        path = (repo / candidate).resolve()
        try:
            path.relative_to(repo.resolve())
        except ValueError:
            warnings.append(f"Ignored media outside project repository: {candidate}")
            continue
        if not path.is_file():
            warnings.append(f"Recommended media is missing: {candidate}")
            continue
        resolved.append(str(path))
    return resolved


def _draft_markdown(draft: dict[str, Any]) -> str:
    media = "\n".join(f"- `{item}`" for item in draft.get("media", [])) or "- none"
    return f"""# {PLATFORM_POLICIES[draft['platform']]['label']} Draft

- Draft ID: `{draft['id']}`
- Target: `{draft['target'] or 'default'}`
- Status: `{draft['status']}`
- Content hash: `{draft['content_hash']}`

## Title

{draft['title'] or '(not used)'}

## Body

{draft['body']}

## Media

{media}

## Review

{draft['rationale'] or 'Review claims, target rules, tone, links, media, and alt text before approval.'}
"""


def _hackernews_worksheet_markdown(draft: dict[str, Any]) -> str:
    worksheet = draft.get("metadata", {}).get("author_worksheet", draft.get("metadata", {}))
    return f"""# Hacker News Human-Author Worksheet

This is not submission copy. Hacker News asks users not to post generated or AI-edited text. Write the final title and text yourself after checking the project and demo.

## Verified Evidence

```json
{json.dumps(worksheet, ensure_ascii=False, indent=2, sort_keys=True)}
```

## Human Checks

- Confirm the project is usable by other people now.
- Submit the original project URL.
- Use a neutral title; use `Show HN:` only if the runnable tool fits Show HN.
- Explain what you built, why, and the technical choices in your own words.
- Be present to answer questions. Never ask for votes.
"""


def _maintenance_markdown(
    campaign: dict[str, Any],
    report: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Campaign Maintenance: {campaign['name']}",
        "",
        f"Generated: {utc_now()}",
        f"Campaign: `{campaign['id']}`",
        f"Analytics snapshots: {len(snapshots)}",
        "",
        "## Assessment",
        "",
        str(report.get("summary") or "No summary supplied."),
        "",
        "## Next Actions",
        "",
    ]
    for item in report.get("next_actions", []):
        if isinstance(item, dict):
            lines.append(f"- P{item.get('priority', '?')}: {item.get('action', '')} - {item.get('reason', '')}")
        else:
            lines.append(f"- {item}")
    lines.extend(["", "## Evidence Report", "", "```json", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def _first_string(value: Any, keys: Iterable[str]) -> str:
    if isinstance(value, dict):
        for key in keys:
            item = value.get(key)
            if isinstance(item, (str, int)) and str(item):
                return str(item)
        for item in value.values():
            found = _first_string(item, keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _first_string(item, keys)
            if found:
                return found
    return ""
