from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agenticapp.cli import main
from agenticapp.social_content import (
    SocialContentError,
    SocialStore,
    _provider_configured,
    _run_json_command,
    content_fingerprint,
    discover_project,
    export_campaign,
    generate_campaign_drafts,
    import_human_draft,
    maintain_campaign,
    publish_draft,
)


class SocialContentTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        repo = root / "PocketPolyglot"
        (repo / "studio" / "docs" / "images").mkdir(parents=True)
        (repo / "assets" / "edition-comparisons").mkdir(parents=True)
        (repo / "studio" / "docs" / "images" / "queue.png").write_bytes(b"png")
        (repo / "assets" / "edition-comparisons" / "comparison.png").write_bytes(b"png")
        (repo / "README.md").write_text(
            "# PocketPolyglot\n\n"
            "Generate pocket-size interlinear books with ruby, pinyin, grammar color, and line alignment.\n\n"
            "Website: https://learn.lazying.art\n",
            encoding="utf-8",
        )
        (repo / "CITATION.cff").write_text(
            'title: "PocketPolyglot"\nurl: "https://learn.lazying.art"\n',
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "Initial project"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:lachlanchen/PocketPolyglot.git"],
            check=True,
        )
        return repo

    def create_campaign(self, root: Path, *, platforms: list[dict[str, str]] | None = None) -> tuple[SocialStore, dict, Path]:
        repo = self.make_project(root)
        store = SocialStore(root / "state")
        store.upsert_project(discover_project(repo, project_id="pocketpolyglot"))
        campaign = store.create_campaign(
            project_id="pocketpolyglot",
            name="introduction",
            objective="Introduce the usable open-source Studio and request concrete feedback.",
            audience="language learners and publishing developers",
            platforms=platforms
            or [
                {"platform": "x", "target": ""},
                {"platform": "reddit", "target": "r/languagelearning"},
                {"platform": "hackernews", "target": ""},
            ],
            model="gpt-5.6-sol",
            effort="ultra",
        )
        return store, campaign, repo

    def test_discover_project_reads_source_evidence_and_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_project(Path(tmp))
            profile = discover_project(repo, project_id="pocketpolyglot")

        self.assertEqual(profile["id"], "pocketpolyglot")
        self.assertEqual(profile["name"], "PocketPolyglot")
        self.assertEqual(profile["repo_url"], "https://github.com/lachlanchen/PocketPolyglot")
        self.assertIn("ruby", profile["summary"])
        self.assertIn("studio/docs/images/queue.png", profile["media_candidates"])
        self.assertTrue(profile["head"])

    def test_generate_campaign_uses_ultra_policy_and_enforces_hn_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, repo = self.create_campaign(root)
            captured = {}

            def fake_agent(prompt, context):
                captured["prompt"] = prompt
                captured["policy"] = context["policy"]
                return json.dumps(
                    {
                        "strategy": "Show the runnable workflow with source-backed examples.",
                        "warnings": [],
                        "drafts": [
                            {
                                "platform": "x",
                                "target": "",
                                "title": "",
                                "body": "PocketPolyglot turns aligned text into readable interlinear pocket books. Code and demo: https://learn.lazying.art",
                                "media": ["studio/docs/images/queue.png"],
                                "settings": {},
                                "metadata": {"alt_text": "PocketPolyglot Studio queue"},
                                "rationale": "Compact product and implementation proof.",
                            },
                            {
                                "platform": "reddit",
                                "target": "r/languagelearning",
                                "title": "I built an open-source interlinear pocket-book workflow",
                                "body": "I am looking for feedback on ruby, pinyin, and line-aligned reading layouts.",
                                "media": ["assets/edition-comparisons/comparison.png"],
                                "settings": {},
                                "metadata": {"needs_rules_review": True},
                                "rationale": "Asks learners for concrete layout feedback.",
                            },
                            {
                                "platform": "hackernews",
                                "target": "",
                                "title": "Show HN: generated title must be removed",
                                "body": "Generated submission text must also be removed.",
                                "media": [],
                                "settings": {},
                                "metadata": {"author_worksheet": {"facts": ["Local Studio with SQLite jobs"]}},
                                "rationale": "Technical worksheet only.",
                            },
                        ],
                    }
                )

            result = generate_campaign_drafts(store, campaign["id"], root=root, agent_runner=fake_agent)
            hn = next(item for item in result["drafts"] if item["platform"] == "hackernews")
            x_draft = next(item for item in result["drafts"] if item["platform"] == "x")

        self.assertTrue(result["ok"])
        self.assertEqual(captured["policy"]["model"], "gpt-5.6-sol")
        self.assertEqual(captured["policy"]["reasoning_effort"], "medium")
        self.assertIn("valid JSON only", captured["prompt"])
        self.assertEqual(hn["title"], "")
        self.assertEqual(hn["body"], "")
        self.assertFalse(hn["human_authored"])
        self.assertEqual(hn["status"], "author_worksheet")
        self.assertEqual(x_draft["media"], [str(repo / "studio" / "docs" / "images" / "queue.png")])

    def test_edit_invalidates_exact_content_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "x", "target": ""}])
            draft = import_human_draft(
                store,
                campaign_id=campaign["id"],
                platform="x",
                target="",
                title="",
                body="First reviewed copy",
            )
            approved = store.approve(draft["id"], review_note="Reviewed")
            changed = import_human_draft(
                store,
                campaign_id=campaign["id"],
                platform="x",
                target="",
                title="",
                body="Changed copy",
            )

            with self.assertRaisesRegex(SocialContentError, "does not match"):
                store.verify_approval(changed["id"], approved["approval_token"])

    def test_publication_metadata_is_part_of_content_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "x", "target": ""}])
            first = store.upsert_draft(
                campaign["id"],
                {
                    "platform": "x",
                    "body": "Reviewed copy",
                    "metadata": {"thread": ["Reviewed follow-up"]},
                },
            )
            second = {**first, "metadata": {"thread": ["Changed follow-up"]}}

        self.assertNotEqual(first["content_hash"], content_fingerprint(second))

    def test_over_limit_draft_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "x", "target": ""}])
            draft = import_human_draft(
                store,
                campaign_id=campaign["id"],
                platform="x",
                target="",
                title="",
                body="x" * 281,
            )

            with self.assertRaisesRegex(SocialContentError, "conservative limit is 280"):
                store.approve(draft["id"])

    def test_postiz_publication_requires_live_and_consumes_token_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(
                root,
                platforms=[{"platform": "reddit", "target": "r/languagelearning"}],
            )
            draft = import_human_draft(
                store,
                campaign_id=campaign["id"],
                platform="reddit",
                target="r/languagelearning",
                title="A source-grounded project introduction",
                body="I built this and would value feedback on the reading layout.",
            )
            draft = store.upsert_draft(
                campaign["id"],
                {
                    **draft,
                    "metadata": {"thread": ["Implementation details are in the repository."]},
                    "origin": "human",
                    "human_authored": True,
                },
            )
            approved = store.approve(draft["id"])
            calls = []

            preview = publish_draft(
                store,
                draft["id"],
                provider="postiz",
                integration_id="reddit-123",
                approval_token="",
                live=False,
            )

            def fake_command(command, **kwargs):
                calls.append((command, kwargs))
                return {"returncode": 0, "stdout": '{"id":"post-42"}', "stderr": "", "json": {"id": "post-42"}}

            scheduled = publish_draft(
                store,
                draft["id"],
                provider="postiz",
                integration_id="reddit-123",
                approval_token=approved["approval_token"],
                schedule_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                live=True,
                command_runner=fake_command,
            )

        self.assertTrue(preview["dry_run"])
        self.assertEqual(len(calls), 1)
        self.assertIn("posts:create", calls[0][0])
        self.assertIn('"subreddit":"languagelearning"', " ".join(calls[0][0]))
        self.assertIn("Implementation details are in the repository.", calls[0][0])
        self.assertEqual(scheduled["publication"]["external_id"], "post-42")
        self.assertEqual(scheduled["publication"]["status"], "scheduled")

    def test_hackernews_agent_worksheet_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "hackernews", "target": ""}])
            worksheet = store.upsert_draft(
                campaign["id"],
                {
                    "platform": "hackernews",
                    "target": "",
                    "title": "",
                    "body": "",
                    "status": "author_worksheet",
                    "metadata": {"author_worksheet": {"facts": ["verified"]}},
                },
            )
            with self.assertRaisesRegex(SocialContentError, "human-authored"):
                store.approve(worksheet["id"])

    def test_platform_length_contract_marks_overlong_copy_for_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "bluesky", "target": ""}])

            def fake_agent(prompt, context):
                return json.dumps(
                    {
                        "strategy": "test",
                        "warnings": [],
                        "drafts": [
                            {
                                "platform": "bluesky",
                                "target": "",
                                "title": "",
                                "body": "x" * 301,
                                "media": [],
                                "settings": {},
                                "metadata": {},
                                "rationale": "test",
                            }
                        ],
                    }
                )

            result = generate_campaign_drafts(store, campaign["id"], root=root, agent_runner=fake_agent)

        self.assertEqual(result["drafts"][0]["status"], "needs_revision")
        self.assertTrue(any("conservative limit is 300" in item for item in result["warnings"]))

    def test_maintenance_reads_analytics_and_writes_agent_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "x", "target": ""}])
            import_human_draft(
                store,
                campaign_id=campaign["id"],
                platform="x",
                target="",
                title="",
                body="A reviewed project update.",
            )

            def fake_analytics(command, **kwargs):
                return {"returncode": 0, "stdout": "analytics", "stderr": "", "json": {"views": 120, "clicks": 8}}

            def fake_agent(prompt, context):
                self.assertIn('"views": 120', prompt)
                return json.dumps(
                    {
                        "summary": "The first post has measurable reach but limited evidence.",
                        "observations": [{"evidence": "120 views", "meaning": "small initial sample"}],
                        "next_actions": [{"priority": 1, "action": "Document the sample workflow", "reason": "improve proof", "requires_human": False}],
                        "content_gaps": ["No end-to-end sample timing"],
                        "stop_doing": ["Do not increase frequency from one small sample"],
                        "followup_campaign_briefs": [],
                    }
                )

            result = maintain_campaign(
                store,
                campaign["id"],
                integrations={"x": "twitter-123"},
                days=30,
                root=root,
                agent_runner=fake_agent,
                analytics_runner=fake_analytics,
            )
            artifact_exists = Path(result["maintenance"]["artifact_path"]).is_file()

        self.assertTrue(result["ok"])
        self.assertEqual(result["analytics"][0]["payload"]["views"], 120)
        self.assertTrue(artifact_exists)

    def test_export_writes_reviewable_manifest_and_hn_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store, campaign, _ = self.create_campaign(root, platforms=[{"platform": "hackernews", "target": ""}])
            store.upsert_draft(
                campaign["id"],
                {
                    "platform": "hackernews",
                    "target": "",
                    "status": "author_worksheet",
                    "metadata": {"author_worksheet": {"facts": ["SQLite-backed local Studio"]}},
                },
            )
            result = export_campaign(store, campaign["id"], root / "review")
            markdown = next(Path(item) for item in result["files"] if item.endswith(".md"))
            text = markdown.read_text(encoding="utf-8")

        self.assertIn("not submission copy", text)
        self.assertIn("SQLite-backed local Studio", text)

    def test_social_cli_initializes_and_lists_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["social", "providers", "--storage-dir", tmp, "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertTrue(any(item["id"] == "postiz" for item in payload["providers"]))
        self.assertTrue(any(item["id"] == "x-mcp" for item in payload["providers"]))

    def test_provider_command_parser_accepts_banner_before_json(self):
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": 'Connected integrations:\n[{"id":"twitter-1"}]\n', "stderr": ""},
        )()
        with patch("agenticapp.social_content.subprocess.run", return_value=completed):
            result = _run_json_command(["postiz", "integrations:list"], timeout=30, check=True)

        self.assertEqual(result["json"], [{"id": "twitter-1"}])

    def test_postiz_oauth_readiness_uses_provider_managed_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            credentials = home / ".postiz" / "credentials.json"
            credentials.parent.mkdir()
            credentials.write_text('{"accessToken":"private"}\n', encoding="utf-8")
            with patch("agenticapp.social_content.Path.home", return_value=home):
                with patch.dict("agenticapp.social_content.os.environ", {}, clear=True):
                    configured = _provider_configured("postiz")

        self.assertTrue(configured)


if __name__ == "__main__":
    unittest.main()
