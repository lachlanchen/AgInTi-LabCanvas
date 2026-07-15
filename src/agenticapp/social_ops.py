from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .social_content import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_STORAGE_DIR,
    SocialStore,
    discover_project,
    export_campaign,
    generate_campaign_drafts,
    import_human_draft,
    maintain_campaign,
    parse_platform_target,
    postiz_analytics,
    postiz_integrations,
    provider_status,
    publish_draft,
)


def add_social_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("social", help="Manage agent-assisted, approval-gated open-source project campaigns.")
    commands = parser.add_subparsers(dest="social_command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--storage-dir", default=str(DEFAULT_STORAGE_DIR), help="Ignored local campaign state. Default: output/social.")
    common.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    init_parser = commands.add_parser("init", parents=[common], help="Initialize the local campaign database.")
    init_parser.set_defaults(func=cmd_social_init)

    project_parser = commands.add_parser("project", help="Register and inspect source projects.")
    project_commands = project_parser.add_subparsers(dest="social_project_command", required=True)
    project_add = project_commands.add_parser("add", parents=[common], help="Discover one local git repository and register its evidence.")
    project_add.add_argument("--repo", required=True, help="Local repository path, such as ../ZhJpBook.")
    project_add.add_argument("--id", default="", help="Stable project id. Derived from the README title by default.")
    project_add.add_argument("--name", default="", help="Public project name override.")
    project_add.add_argument("--homepage", default="", help="Project homepage override.")
    project_add.add_argument("--summary", default="", help="Source-grounded project summary override.")
    project_add.set_defaults(func=cmd_social_project_add)
    project_list = project_commands.add_parser("list", parents=[common], help="List registered projects.")
    project_list.set_defaults(func=cmd_social_project_list)

    campaign_parser = commands.add_parser("campaign", help="Create and inspect campaigns.")
    campaign_commands = campaign_parser.add_subparsers(dest="social_campaign_command", required=True)
    campaign_create = campaign_commands.add_parser("create", parents=[common], help="Create a campaign brief.")
    campaign_create.add_argument("--project", required=True, help="Registered project id.")
    campaign_create.add_argument("--name", required=True, help="Short campaign name.")
    campaign_create.add_argument("--objective", required=True, help="Concrete campaign objective.")
    campaign_create.add_argument("--audience", default="", help="Intended audience and useful context.")
    campaign_create.add_argument(
        "--platform",
        action="append",
        required=True,
        help="Platform or platform:target. Repeat, for example x and reddit:r/languagelearning.",
    )
    campaign_create.add_argument("--model", default=DEFAULT_MODEL, help=f"Drafting model. Default: {DEFAULT_MODEL}.")
    campaign_create.add_argument(
        "--effort",
        choices=["low", "medium", "high", "ultra", "xhigh"],
        default=DEFAULT_EFFORT,
        help="Drafting effort. Ultra maps to xhigh.",
    )
    campaign_create.set_defaults(func=cmd_social_campaign_create)
    campaign_list = campaign_commands.add_parser("list", parents=[common], help="List campaigns.")
    campaign_list.add_argument("--project", default="", help="Filter by project id.")
    campaign_list.set_defaults(func=cmd_social_campaign_list)

    draft_parser = commands.add_parser("draft", help="Generate, import, and inspect exact post drafts.")
    draft_commands = draft_parser.add_subparsers(dest="social_draft_command", required=True)
    draft_generate = draft_commands.add_parser("generate", parents=[common], help="Use the persistent Codex project session to draft a campaign.")
    draft_generate.add_argument("campaign_id", help="Campaign id.")
    draft_generate.add_argument("--dry-run", action="store_true", help="Print the agent contract without using model quota.")
    draft_generate.set_defaults(func=cmd_social_draft_generate)
    draft_import = draft_commands.add_parser("import-human", parents=[common], help="Import final human-authored or human-revised copy.")
    draft_import.add_argument("campaign_id", help="Campaign id.")
    draft_import.add_argument("--platform", required=True, help="Platform name.")
    draft_import.add_argument("--target", default="", help="Exact campaign target, such as r/languagelearning.")
    draft_import.add_argument("--title", default="", help="Human-authored title.")
    body_group = draft_import.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Human-authored body.")
    body_group.add_argument("--body-file", help="UTF-8 file containing the human-authored body.")
    draft_import.add_argument("--media", action="append", default=[], help="Local media path. Repeatable.")
    draft_import.add_argument("--settings", default="{}", help="Provider settings JSON or @path.")
    draft_import.set_defaults(func=cmd_social_draft_import)
    draft_list = draft_commands.add_parser("list", parents=[common], help="List generated and human drafts.")
    draft_list.add_argument("--campaign", default="", help="Filter by campaign id.")
    draft_list.set_defaults(func=cmd_social_draft_list)

    approve_parser = commands.add_parser("approve", parents=[common], help="Approve the exact current content hash of one draft.")
    approve_parser.add_argument("draft_id", help="Draft id.")
    approve_parser.add_argument("--note", default="", help="Review note stored in the private ledger.")
    approve_parser.add_argument("--ttl-hours", type=int, default=24, help="Approval lifetime. Default: 24 hours.")
    approve_parser.set_defaults(func=cmd_social_approve)

    publish_parser = commands.add_parser("publish", parents=[common], help="Preview or publish an approved draft through a provider.")
    publish_parser.add_argument("draft_id", help="Draft id.")
    publish_parser.add_argument("--provider", default="postiz", choices=["postiz"], help="Write provider. Default: postiz.")
    publish_parser.add_argument("--integration", default="", help="Provider integration/account id.")
    publish_parser.add_argument("--approval", default="", help="Exact-content approval token. Required with --live.")
    publish_parser.add_argument("--schedule-at", default="", help="ISO-8601 time. Defaults to five minutes from now.")
    publish_parser.add_argument("--live", action="store_true", help="Perform the external write. Without this flag the command is a dry run.")
    publish_parser.set_defaults(func=cmd_social_publish)

    export_parser = commands.add_parser("export", parents=[common], help="Export a reviewable campaign package.")
    export_parser.add_argument("campaign_id", help="Campaign id.")
    export_parser.add_argument("--output", required=True, help="Destination folder.")
    export_parser.set_defaults(func=cmd_social_export)

    providers_parser = commands.add_parser("providers", parents=[common], help="Show supported providers and local readiness.")
    providers_parser.add_argument("--probe", action="store_true", help="Run non-writing provider status probes.")
    providers_parser.set_defaults(func=cmd_social_providers)

    integrations_parser = commands.add_parser("postiz-integrations", parents=[common], help="List connected Postiz accounts without posting.")
    integrations_parser.set_defaults(func=cmd_social_postiz_integrations)

    history_parser = commands.add_parser("history", parents=[common], help="List local publication records.")
    history_parser.set_defaults(func=cmd_social_history)

    analytics_parser = commands.add_parser("postiz-analytics", parents=[common], help="Read analytics for one connected Postiz account.")
    analytics_parser.add_argument("--integration", required=True, help="Postiz integration/account id.")
    analytics_parser.add_argument("--days", type=int, default=30, help="Analytics window. Default: 30 days.")
    analytics_parser.set_defaults(func=cmd_social_postiz_analytics)

    maintain_parser = commands.add_parser("maintain", parents=[common], help="Analyze campaign history and analytics with the persistent project agent.")
    maintain_parser.add_argument("campaign_id", help="Campaign id.")
    maintain_parser.add_argument(
        "--integration",
        action="append",
        default=[],
        help="Platform=PostizIntegrationId. Repeatable, for example x=twitter-123.",
    )
    maintain_parser.add_argument("--days", type=int, default=30, help="Analytics window. Default: 30 days.")
    maintain_parser.add_argument("--dry-run", action="store_true", help="Show the maintenance-agent contract without provider reads or model quota.")
    maintain_parser.set_defaults(func=cmd_social_maintain)


def cmd_social_init(args: argparse.Namespace) -> int:
    store = SocialStore(args.storage_dir)
    return _emit(
        {"ok": True, "storage_dir": str(store.storage_dir), "database": str(store.database_path)},
        args.json,
        f"social content database: {store.database_path}",
    )


def cmd_social_project_add(args: argparse.Namespace) -> int:
    store = SocialStore(args.storage_dir)
    profile = discover_project(
        args.repo,
        project_id=args.id,
        name=args.name,
        homepage=args.homepage,
        summary=args.summary,
    )
    project = store.upsert_project(profile)
    return _emit({"ok": True, "project": project}, args.json, f"social project: {project['id']} ({project['name']})")


def cmd_social_project_list(args: argparse.Namespace) -> int:
    projects = SocialStore(args.storage_dir).list_projects()
    return _emit({"ok": True, "projects": projects}, args.json, f"social projects: {len(projects)}")


def cmd_social_campaign_create(args: argparse.Namespace) -> int:
    store = SocialStore(args.storage_dir)
    campaign = store.create_campaign(
        project_id=args.project,
        name=args.name,
        objective=args.objective,
        audience=args.audience,
        platforms=[parse_platform_target(value) for value in args.platform],
        model=args.model,
        effort=args.effort,
    )
    return _emit({"ok": True, "campaign": campaign}, args.json, f"social campaign: {campaign['id']}")


def cmd_social_campaign_list(args: argparse.Namespace) -> int:
    campaigns = SocialStore(args.storage_dir).list_campaigns(args.project)
    return _emit({"ok": True, "campaigns": campaigns}, args.json, f"social campaigns: {len(campaigns)}")


def cmd_social_draft_generate(args: argparse.Namespace) -> int:
    store = SocialStore(args.storage_dir)
    result = generate_campaign_drafts(store, args.campaign_id, root=Path.cwd(), dry_run=args.dry_run)
    label = (
        f"social draft contract: {result['policy']['model']} {result['policy']['effort_label']}"
        if args.dry_run
        else f"social drafts: {len(result.get('drafts', []))}"
    )
    return _emit(result, args.json, label)


def cmd_social_draft_import(args: argparse.Namespace) -> int:
    body = args.body if args.body is not None else Path(args.body_file).expanduser().read_text(encoding="utf-8")
    draft = import_human_draft(
        SocialStore(args.storage_dir),
        campaign_id=args.campaign_id,
        platform=args.platform,
        target=args.target,
        title=args.title,
        body=body,
        media=args.media,
        settings=_load_json_value(args.settings),
    )
    return _emit({"ok": True, "draft": draft}, args.json, f"human draft: {draft['id']} ({draft['platform']})")


def cmd_social_draft_list(args: argparse.Namespace) -> int:
    drafts = SocialStore(args.storage_dir).list_drafts(args.campaign)
    return _emit({"ok": True, "drafts": drafts}, args.json, f"social drafts: {len(drafts)}")


def cmd_social_approve(args: argparse.Namespace) -> int:
    result = SocialStore(args.storage_dir).approve(args.draft_id, review_note=args.note, ttl_hours=args.ttl_hours)
    return _emit(result | {"ok": True}, args.json, f"approved {args.draft_id}: {result['approval_token']}")


def cmd_social_publish(args: argparse.Namespace) -> int:
    result = publish_draft(
        SocialStore(args.storage_dir),
        args.draft_id,
        provider=args.provider,
        integration_id=args.integration,
        approval_token=args.approval,
        schedule_at=args.schedule_at,
        live=args.live,
    )
    if result.get("dry_run"):
        label = f"publication dry run: {args.draft_id} -> {args.provider}/{args.integration or '(integration required)'}"
    else:
        publication = result["publication"]
        label = f"publication {publication['status']}: {publication['id']}"
    return _emit(result, args.json, label)


def cmd_social_export(args: argparse.Namespace) -> int:
    result = export_campaign(SocialStore(args.storage_dir), args.campaign_id, args.output)
    return _emit(result, args.json, f"campaign export: {len(result['files'])} files")


def cmd_social_providers(args: argparse.Namespace) -> int:
    providers = provider_status(probe=args.probe)
    return _emit({"ok": True, "providers": providers}, args.json, f"social providers: {len(providers)}")


def cmd_social_postiz_integrations(args: argparse.Namespace) -> int:
    integrations = postiz_integrations()
    return _emit({"ok": True, "integrations": integrations}, args.json, f"Postiz integrations: {len(integrations)}")


def cmd_social_history(args: argparse.Namespace) -> int:
    publications = SocialStore(args.storage_dir).list_publications()
    return _emit({"ok": True, "publications": publications}, args.json, f"publication records: {len(publications)}")


def cmd_social_postiz_analytics(args: argparse.Namespace) -> int:
    analytics = postiz_analytics(args.integration, days=args.days)
    return _emit({"ok": True, "integration_id": args.integration, "days": args.days, "analytics": analytics}, args.json, "Postiz analytics loaded")


def cmd_social_maintain(args: argparse.Namespace) -> int:
    integrations = _parse_integration_map(args.integration)
    result = maintain_campaign(
        SocialStore(args.storage_dir),
        args.campaign_id,
        integrations=integrations,
        days=args.days,
        root=Path.cwd(),
        dry_run=args.dry_run,
    )
    if result.get("dry_run"):
        label = f"social maintenance contract: {result['policy']['model']} {result['policy']['effort_label']}"
    else:
        label = f"social maintenance report: {result['maintenance']['artifact_path']}"
    return _emit(result, args.json, label)


def _load_json_value(value: str) -> dict[str, Any]:
    raw = str(value or "{}").strip()
    if raw.startswith("@"):
        raw = Path(raw[1:]).expanduser().read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def _parse_integration_map(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        platform, separator, integration_id = str(value or "").partition("=")
        if not separator or not platform.strip() or not integration_id.strip():
            raise ValueError(f"Invalid integration mapping: {value!r}; expected platform=integration-id")
        result[platform.strip()] = integration_id.strip()
    return result


def _emit(payload: dict[str, Any], as_json: bool, message: str) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(message)
    return 0 if payload.get("ok", True) else 1
