from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib import error, request


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOOKS_ROOT = PACKAGE_ROOT.parent / "Books"
DEFAULT_POLYGLOT_ROOT = PACKAGE_ROOT.parent / "ZhJpBook"
DEFAULT_CDP_URL = "http://127.0.0.1:9344"


def add_books_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "books",
        aliases=["book"],
        help="Search book sources and operate the sibling PocketPolyglot Studio.",
    )
    commands = parser.add_subparsers(dest="books_command", required=True)

    status = commands.add_parser(
        "status",
        help="Inspect the Books, AgenticBrowser, and PocketPolyglot runtimes.",
    )
    add_books_root_argument(status)
    add_polyglot_root_argument(status)
    status.add_argument("--cdp-url", default=default_cdp_url())
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_books_status)

    search = commands.add_parser(
        "search",
        help="Search exact book candidates through the existing guarded browser.",
    )
    add_books_root_argument(search)
    search.add_argument("queries", nargs="+")
    search.add_argument("--cdp-url", default=default_cdp_url())
    search.add_argument("--language", default="")
    search.add_argument("--title-term", action="append", default=[])
    search.add_argument("--author-term", action="append", default=[])
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--top", type=int, default=10)
    search.add_argument(
        "--no-start-browser",
        action="store_true",
        help="Fail instead of starting/reusing the canonical AgenticBrowser desktop.",
    )
    search.add_argument("--dry-run", action="store_true")
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_books_search)

    polyglot = commands.add_parser(
        "polyglot",
        help="Delegate multilingual-book work to the sibling PocketPolyglot Studio.",
    )
    polyglot_commands = polyglot.add_subparsers(
        dest="polyglot_command",
        required=True,
    )
    polyglot_common = argparse.ArgumentParser(add_help=False)
    add_polyglot_root_argument(polyglot_common)
    polyglot_common.add_argument("--json", action="store_true")

    for action in ("doctor", "discover", "projects", "browser-status"):
        command = polyglot_commands.add_parser(action, parents=[polyglot_common])
        command.set_defaults(func=cmd_books_polyglot)

    create = polyglot_commands.add_parser(
        "create",
        parents=[polyglot_common],
        help="Create one durable PocketPolyglot project.",
    )
    create.add_argument("title")
    create.add_argument("--book-id", default="")
    create.add_argument(
        "--workflow",
        choices=["lingualeaf", "pocket_exact", "pocket_polished", "custom"],
        default="lingualeaf",
    )
    create.add_argument("--source-language", default="en")
    create.add_argument("--primary-language", default="en")
    create.add_argument("--target", action="append", default=[])
    create.add_argument("--dry-run", action="store_true")
    create.set_defaults(func=cmd_books_polyglot)

    source = polyglot_commands.add_parser(
        "source-add",
        parents=[polyglot_common],
        help="Register one exact local source with a PocketPolyglot project.",
    )
    source.add_argument("project")
    source.add_argument("path")
    source.add_argument("--role", default="primary")
    source.add_argument("--language", default="")
    source.add_argument("--dry-run", action="store_true")
    source.set_defaults(func=cmd_books_polyglot)

    run = polyglot_commands.add_parser(
        "run",
        parents=[polyglot_common],
        help="Launch one durable PocketPolyglot capability job.",
    )
    run.add_argument("project")
    run.add_argument("capability")
    run.add_argument("--param", action="append", default=[])
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_books_polyglot)

    status_command = polyglot_commands.add_parser(
        "status",
        parents=[polyglot_common],
        help="Read one job or list current PocketPolyglot jobs.",
    )
    status_command.add_argument("job", nargs="?")
    status_command.add_argument("--project", default="")
    status_command.set_defaults(func=cmd_books_polyglot)

    logs = polyglot_commands.add_parser(
        "logs",
        parents=[polyglot_common],
        help="Read the bounded tail of one PocketPolyglot job log.",
    )
    logs.add_argument("job")
    logs.add_argument("--lines", type=int, default=100)
    logs.set_defaults(func=cmd_books_polyglot)

    chat = polyglot_commands.add_parser(
        "chat",
        parents=[polyglot_common],
        help="Send one project-scoped turn to PocketPolyglot Studio.",
    )
    chat.add_argument("project")
    chat.add_argument("message", nargs="+")
    chat.add_argument(
        "--profile",
        choices=["auto", "fast", "balanced", "deep", "ultra"],
        default="auto",
    )
    chat.add_argument("--read-only", action="store_true")
    chat.add_argument("--dry-run", action="store_true")
    chat.add_argument("--timeout", type=float, default=7200.0)
    chat.set_defaults(func=cmd_books_polyglot)

    progress = polyglot_commands.add_parser(
        "progress",
        parents=[polyglot_common],
        help="Inspect durable job progress through the existing Studio browser.",
    )
    progress.add_argument("--project", default="")
    progress.set_defaults(func=cmd_books_polyglot)


def add_books_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--books-root", default=str(DEFAULT_BOOKS_ROOT))


def add_polyglot_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--polyglot-root", default=str(DEFAULT_POLYGLOT_ROOT))


def default_cdp_url() -> str:
    explicit = str(os.environ.get("LABCANVAS_BOOKS_CDP_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    port = str(os.environ.get("AGENTIC_VDESKTOP_BROWSER_PORT") or "").strip()
    if port.isdigit():
        return f"http://127.0.0.1:{port}"
    return DEFAULT_CDP_URL


def books_root(args: argparse.Namespace) -> Path:
    return Path(args.books_root).expanduser().resolve()


def polyglot_root(args: argparse.Namespace) -> Path:
    return Path(args.polyglot_root).expanduser().resolve()


def cdp_ready(cdp_url: str, timeout: float = 2.0) -> bool:
    try:
        with request.urlopen(
            f"{cdp_url.rstrip('/')}/json/version",
            timeout=timeout,
        ) as response:
            payload = json.load(response)
    except (OSError, error.URLError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and bool(payload.get("Browser"))


def tmux_session_ready(session: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def cmd_books_status(args: argparse.Namespace) -> int:
    books = books_root(args)
    polyglot = polyglot_root(args)
    search_script = books / "tools" / "book_search" / "libgen_browser_context_search.py"
    browser_bridge = (
        books
        / "tools"
        / "aginti_browser_bridge"
        / "run-agentic-browser-vdesktop.sh"
    )
    polyglot_cli = polyglot / "studio" / "pocketpolyglot"
    result = {
        "ok": search_script.is_file() and polyglot_cli.is_file(),
        "books": {
            "root": str(books),
            "search_script": search_script.is_file(),
            "browser_bridge": browser_bridge.is_file(),
            "cdp_url": str(args.cdp_url).rstrip("/"),
            "cdp_ready": cdp_ready(str(args.cdp_url)),
            "tmux": tmux_session_ready("agentic-browser-vdesktop"),
        },
        "polyglot": {
            "root": str(polyglot),
            "cli": polyglot_cli.is_file(),
            "studio_tmux": tmux_session_ready("pocketpolyglot-studio"),
            "browser_tmux": tmux_session_ready("pocketpolyglot-studio-browser"),
        },
    }
    emit_result(result, bool(args.json))
    return 0 if result["ok"] else 1


def build_search_command(args: argparse.Namespace) -> list[str]:
    script = (
        books_root(args)
        / "tools"
        / "book_search"
        / "libgen_browser_context_search.py"
    )
    if not script.is_file():
        raise ValueError(f"Book search tool is missing: {script}")
    command = [
        sys.executable,
        str(script),
        "--cdp-url",
        str(args.cdp_url).rstrip("/"),
        "--limit",
        str(max(1, int(args.limit))),
        "--top",
        str(max(1, int(args.top))),
        "--json",
    ]
    if args.language:
        command.extend(["--language", str(args.language)])
    for value in args.title_term:
        command.extend(["--title-term", str(value)])
    for value in args.author_term:
        command.extend(["--author-term", str(value)])
    command.extend(str(query) for query in args.queries)
    return command


def ensure_books_browser(
    books: Path,
    cdp_url: str,
    *,
    start_allowed: bool,
    timeout: float = 40.0,
) -> dict[str, Any]:
    if cdp_ready(cdp_url):
        return {"ok": True, "reused": True, "cdp_url": cdp_url}
    if not start_allowed:
        return {
            "ok": False,
            "reused": False,
            "cdp_url": cdp_url,
            "error": "AgenticBrowser CDP is not ready and auto-start is disabled.",
        }
    bridge = (
        books
        / "tools"
        / "aginti_browser_bridge"
        / "run-agentic-browser-vdesktop.sh"
    )
    if not bridge.is_file():
        return {
            "ok": False,
            "reused": False,
            "cdp_url": cdp_url,
            "error": f"AgenticBrowser bridge is missing: {bridge}",
        }
    process = subprocess.run(
        [str(bridge), "start"],
        cwd=books,
        capture_output=True,
        text=True,
        timeout=max(5.0, timeout),
        check=False,
    )
    deadline = time.monotonic() + max(2.0, timeout)
    while time.monotonic() < deadline:
        if cdp_ready(cdp_url):
            return {
                "ok": True,
                "reused": False,
                "cdp_url": cdp_url,
                "start_returncode": process.returncode,
            }
        time.sleep(0.5)
    return {
        "ok": False,
        "reused": False,
        "cdp_url": cdp_url,
        "start_returncode": process.returncode,
        "error": (process.stderr or process.stdout or "AgenticBrowser did not become ready.")[
            -500:
        ],
    }


def cmd_books_search(args: argparse.Namespace) -> int:
    command = build_search_command(args)
    if args.dry_run:
        emit_result(
            {
                "ok": True,
                "dry_run": True,
                "command": command,
                "policy": "search/detail candidates only; no mirror download",
            },
            bool(args.json),
        )
        return 0
    browser = ensure_books_browser(
        books_root(args),
        str(args.cdp_url).rstrip("/"),
        start_allowed=not bool(args.no_start_browser),
    )
    if not browser["ok"]:
        emit_result({"ok": False, "browser": browser}, bool(args.json))
        return 1
    process = subprocess.run(
        command,
        cwd=books_root(args),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    payload: dict[str, Any] = {}
    if process.stdout.strip():
        try:
            decoded = json.loads(process.stdout)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            payload = {}
    for result in payload.get("results", []):
        if isinstance(result, dict) and isinstance(result.get("books"), list):
            result["books"] = sorted(
                result["books"],
                key=lambda item: int(item.get("score") or 0),
                reverse=True,
            )[: max(1, int(args.top))]
    result = {
        "ok": process.returncode == 0 and bool(payload),
        "browser": browser,
        "policy": "search/detail candidates only; no mirror download",
        "results": payload.get("results", []),
        "closed_ad_targets": payload.get("closed_ad_targets", 0),
        "error": process.stderr.strip()[-1000:] if process.returncode else "",
    }
    emit_result(result, bool(args.json))
    return 0 if result["ok"] else 1


def build_polyglot_command(args: argparse.Namespace) -> list[str]:
    root = polyglot_root(args)
    launcher = root / "studio" / "pocketpolyglot"
    if not launcher.is_file():
        raise ValueError(f"PocketPolyglot CLI is missing: {launcher}")
    action = str(args.polyglot_command)
    command = [str(launcher)]
    if action in {"doctor", "discover"}:
        command.append(action)
    elif action == "projects":
        command.extend(["project", "list"])
    elif action == "browser-status":
        command.extend(["browser", "status"])
    elif action == "create":
        command.extend(
            [
                "project",
                "create",
                str(args.title),
                "--workflow",
                str(args.workflow),
                "--source-language",
                str(args.source_language),
                "--primary-language",
                str(args.primary_language),
            ]
        )
        if args.book_id:
            command.extend(["--book-id", str(args.book_id)])
        for target in args.target:
            command.extend(["--target", str(target)])
    elif action == "source-add":
        command.extend(
            [
                "source",
                "add",
                str(args.project),
                str(Path(args.path).expanduser().resolve()),
                "--role",
                str(args.role),
            ]
        )
        if args.language:
            command.extend(["--language", str(args.language)])
    elif action == "run":
        command.extend(["run", str(args.project), str(args.capability)])
        for parameter in args.param:
            command.extend(["--param", str(parameter)])
    elif action == "status":
        command.append("status")
        if args.job:
            command.append(str(args.job))
        if args.project:
            command.extend(["--project", str(args.project)])
    elif action == "logs":
        command.extend(["logs", str(args.job), "--lines", str(max(1, args.lines))])
    elif action == "chat":
        command.extend(
            [
                "chat",
                str(args.project),
                *[str(item) for item in args.message],
                "--profile",
                str(args.profile),
            ]
        )
        if args.read_only:
            command.append("--read-only")
    elif action == "progress":
        command.extend(["browser", "progress"])
        if args.project:
            command.extend(["--project", str(args.project)])
    else:
        raise ValueError(f"Unsupported PocketPolyglot action: {action}")
    return command


def cmd_books_polyglot(args: argparse.Namespace) -> int:
    command = build_polyglot_command(args)
    if bool(getattr(args, "dry_run", False)):
        emit_result(
            {
                "ok": True,
                "dry_run": True,
                "command": command,
                "cwd": str(polyglot_root(args)),
            },
            bool(args.json),
        )
        return 0
    process = subprocess.run(
        command,
        cwd=polyglot_root(args),
        capture_output=True,
        text=True,
        timeout=float(getattr(args, "timeout", 600.0)),
        check=False,
    )
    parsed: Any = None
    if process.stdout.strip().startswith(("{", "[")):
        try:
            parsed = json.loads(process.stdout)
        except json.JSONDecodeError:
            parsed = None
    result = {
        "ok": process.returncode == 0,
        "action": str(args.polyglot_command),
        "returncode": process.returncode,
        "data": parsed,
        "output": "" if parsed is not None else process.stdout.strip(),
        "error": process.stderr.strip()[-2000:] if process.returncode else "",
    }
    emit_result(result, bool(args.json))
    return 0 if result["ok"] else 1


def emit_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if result.get("dry_run"):
        print(" ".join(str(item) for item in result.get("command", [])))
        return
    if "results" in result:
        for query in result.get("results", []):
            print(f"{query.get('query')}:")
            for book in query.get("books", []):
                authors = ", ".join(book.get("author") or [])
                print(
                    f"- {book.get('title') or ''} | {authors} | "
                    f"{book.get('language') or ''} | {book.get('fileExtension') or ''} | "
                    f"{book.get('url') or ''}"
                )
        if result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
        return
    if "books" in result and "polyglot" in result:
        print(
            "Books search: "
            f"{'ready' if result['books']['search_script'] else 'missing'}; "
            f"browser {'ready' if result['books']['cdp_ready'] else 'stopped'}"
        )
        print(
            "PocketPolyglot: "
            f"{'ready' if result['polyglot']['cli'] else 'missing'}; "
            f"studio {'running' if result['polyglot']['studio_tmux'] else 'stopped'}"
        )
        return
    output = str(result.get("output") or "")
    if output:
        print(output)
    elif result.get("data") is not None:
        print(json.dumps(result["data"], ensure_ascii=False, indent=2))
    elif result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
