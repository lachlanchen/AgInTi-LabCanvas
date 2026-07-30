from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agenticapp import books_ops
from agenticapp import cli


class BooksOpsTests(unittest.TestCase):
    def test_cli_registers_books_and_polyglot_commands(self) -> None:
        parser = cli.build_parser()

        search = parser.parse_args(
            [
                "books",
                "search",
                "Pride and Prejudice",
                "--language",
                "eng",
                "--title-term",
                "Pride and Prejudice",
                "--json",
            ]
        )
        progress = parser.parse_args(
            [
                "books",
                "polyglot",
                "progress",
                "--project",
                "austen-en-zh-ja",
                "--json",
            ]
        )

        self.assertEqual(search.books_command, "search")
        self.assertEqual(search.language, "eng")
        self.assertEqual(progress.polyglot_command, "progress")
        self.assertEqual(progress.project, "austen-en-zh-ja")

    def test_search_dry_run_builds_guarded_metadata_command_without_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = (
                root
                / "tools"
                / "book_search"
                / "libgen_browser_context_search.py"
            )
            script.parent.mkdir(parents=True)
            script.write_text("# fixture\n", encoding="utf-8")
            args = argparse.Namespace(
                books_root=str(root),
                queries=["Pride and Prejudice", "Jane Austen"],
                cdp_url="http://127.0.0.1:9344",
                language="eng",
                title_term=["Pride and Prejudice"],
                author_term=["Jane Austen"],
                limit=12,
                top=4,
                no_start_browser=False,
                dry_run=True,
                json=True,
            )
            with mock.patch.object(
                books_ops,
                "ensure_books_browser",
            ) as ensure_browser, mock.patch("builtins.print"):
                returncode = books_ops.cmd_books_search(args)
            command = books_ops.build_search_command(args)

        self.assertEqual(returncode, 0)
        ensure_browser.assert_not_called()
        self.assertIn("--cdp-url", command)
        self.assertIn("--language", command)
        self.assertIn("--title-term", command)
        self.assertIn("--author-term", command)
        self.assertEqual(command[-2:], ["Pride and Prejudice", "Jane Austen"])
        self.assertNotIn("download", command)

    def test_polyglot_commands_delegate_to_existing_studio_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            launcher = root / "studio" / "pocketpolyglot"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")
            create = argparse.Namespace(
                polyglot_root=str(root),
                polyglot_command="create",
                title="Classical Chinese Reader",
                book_id="reader-1",
                workflow="lingualeaf",
                source_language="zh-Hant",
                primary_language="zh-Hant",
                target=["en", "ja", "zh-Hans"],
            )
            run = argparse.Namespace(
                polyglot_root=str(root),
                polyglot_command="run",
                project="reader-1",
                capability="build-all",
                param=["color=true", "bw=true"],
            )

            create_command = books_ops.build_polyglot_command(create)
            run_command = books_ops.build_polyglot_command(run)

        self.assertEqual(create_command[0], str(launcher))
        self.assertEqual(create_command[1:3], ["project", "create"])
        self.assertEqual(create_command.count("--target"), 3)
        self.assertEqual(run_command[1:4], ["run", "reader-1", "build-all"])
        self.assertEqual(run_command.count("--param"), 2)

    def test_status_reports_both_sibling_control_planes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            books = parent / "Books"
            polyglot = parent / "ZhJpBook"
            search_script = (
                books
                / "tools"
                / "book_search"
                / "libgen_browser_context_search.py"
            )
            browser_bridge = (
                books
                / "tools"
                / "aginti_browser_bridge"
                / "run-agentic-browser-vdesktop.sh"
            )
            launcher = polyglot / "studio" / "pocketpolyglot"
            for path in (search_script, browser_bridge, launcher):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# fixture\n", encoding="utf-8")
            args = argparse.Namespace(
                books_root=str(books),
                polyglot_root=str(polyglot),
                cdp_url="http://127.0.0.1:9344",
                json=True,
            )
            with mock.patch.object(
                books_ops,
                "cdp_ready",
                return_value=True,
            ), mock.patch.object(
                books_ops,
                "tmux_session_ready",
                return_value=True,
            ), mock.patch("builtins.print") as printer:
                returncode = books_ops.cmd_books_status(args)

        self.assertEqual(returncode, 0)
        payload = printer.call_args.args[0]
        self.assertIn('"search_script": true', payload)
        self.assertIn('"cli": true', payload)


if __name__ == "__main__":
    unittest.main()
