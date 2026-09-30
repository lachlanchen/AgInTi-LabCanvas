from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from agenticapp import codex_accounts


class CodexAccountPoolTests(unittest.TestCase):
    def test_discovery_reads_existing_profiles_without_creating_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("company", "lab"):
                profile = root / name
                profile.mkdir()
                (profile / "profile.conf").write_text(f"name={name}\n", encoding="utf-8")
            (root / "not-a-profile").mkdir()

            accounts = codex_accounts.discover_agentshell_accounts(
                root,
                allowlist=["lab", "missing", "company"],
            )

            self.assertEqual(accounts, ["lab", "company"])
            self.assertFalse((root / "missing").exists())

    def test_candidates_prefer_weekly_quota_and_exclude_exhausted_profiles(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profiles"
            root.mkdir()
            for name in ("company", "lab", "personal"):
                profile = root / name
                profile.mkdir()
                (profile / "profile.conf").write_text(f"name={name}\n", encoding="utf-8")
            cache = Path(tmp) / "pool.json"
            cache.write_text(
                json.dumps(
                    {
                        "accounts": {
                            "company": {
                                "ok": True,
                                "codex_available": False,
                                "weekly_quota_available": False,
                                "remaining_percent": 0,
                                "observed_at_epoch": now,
                            },
                            "lab": {
                                "ok": True,
                                "codex_available": True,
                                "weekly_quota_available": True,
                                "remaining_percent": 80,
                                "observed_at_epoch": now,
                            },
                            "personal": {
                                "ok": True,
                                "codex_available": True,
                                "weekly_quota_available": False,
                                "remaining_percent": 0,
                                "credits": {"has_credits": True, "balance": "5000"},
                                "observed_at_epoch": now,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"LABCANVAS_CODEX_ACCOUNT_POOL_ENABLED": "1"}, clear=False):
                selected = codex_accounts.codex_account_candidates(
                    cache_path=cache,
                    profile_root=root,
                )

        self.assertEqual(selected, ["lab", "personal"])

    def test_agentshell_command_keeps_account_before_codex_arguments(self) -> None:
        with mock.patch.object(codex_accounts, "resolve_agent_codex_binary", return_value="/usr/bin/agent-codex"):
            command = codex_accounts.agentshell_codex_command("lab", ["--search", "exec"])
        self.assertEqual(command, ["/usr/bin/agent-codex", "--account", "lab", "--search", "exec"])

    def test_reserve_requires_fresh_entitlement_and_exhausted_regular_pool(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profiles"
            profile = root / "company"
            profile.mkdir(parents=True)
            (profile / "profile.conf").touch()
            cache = Path(tmp) / "pool.json"
            base = {
                "ok": True, "codex_available": False, "remaining_percent": 0,
                "observed_at_epoch": now,
                "reserve": {"available": True, "model": "gpt-5.6-luna",
                            "remaining_percent": 70, "window": {"resets_at": now + 3600}},
            }
            cases = [
                (base, True), ({**base, "remaining_percent": 10}, False),
                ({**base, "observed_at_epoch": now - 1000}, False),
                ({**base, "reserve": {}}, False),
                ({**base, "reserve": {**base["reserve"], "available": False}}, False),
                ({**base, "remaining_percent": 10, "runtime_unavailable_until": now + 600,
                  "runtime_unavailable_reason": "runtime_quota_rejection"}, True),
                ({**base, "reserve_runtime_unavailable_until": now + 600}, False),
            ]
            for status, expected in cases:
                with self.subTest(status=status):
                    cache.write_text(json.dumps({"accounts": {"company": status}}))
                    selected = codex_accounts.codex_reserve_candidates(
                        cache_path=cache, profile_root=root,
                    )
                    self.assertEqual(bool(selected), expected)
                    if selected:
                        self.assertEqual(selected[0]["model"], "gpt-5.6-luna")

    def test_reserve_is_evaluated_after_regular_attempts_and_preserves_order(self) -> None:
        reserve = {"account": "company", "model": "gpt-5.6-luna", "quota_pool": "reserve"}
        with mock.patch.object(codex_accounts, "codex_reserve_candidates", return_value=[reserve]) as lookup:
            attempts = codex_accounts.codex_account_attempts(["lab", "company"], "gpt-6-astra")
            self.assertEqual(next(attempts)["account"], "lab")
            self.assertEqual(next(attempts)["model"], "gpt-6-astra")
            lookup.assert_not_called()
            self.assertEqual(next(attempts), reserve)
            self.assertEqual(list(attempts), [])

    def test_reserve_rejection_does_not_disable_regular_quota(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "pool.json"
            cache.write_text(json.dumps({"accounts": {"lab": {"codex_available": True}}}))
            codex_accounts.mark_codex_account_runtime_unavailable("lab", cache_path=cache, quota_pool="reserve")
            state = codex_accounts.load_account_pool_cache(cache)["accounts"]["lab"]
            self.assertTrue(state["codex_available"])
            self.assertGreater(state["reserve_runtime_unavailable_until"], time.time())

    def test_runtime_quota_rejection_temporarily_removes_account(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profiles"
            root.mkdir()
            for name in ("lab", "personal"):
                profile = root / name
                profile.mkdir()
                (profile / "profile.conf").write_text(f"name={name}\n", encoding="utf-8")
            cache = Path(tmp) / "pool.json"
            cache.write_text(
                json.dumps(
                    {
                        "accounts": {
                            name: {
                                "ok": True,
                                "codex_available": True,
                                "weekly_quota_available": True,
                                "remaining_percent": 50,
                                "observed_at_epoch": now,
                            }
                            for name in ("lab", "personal")
                        }
                    }
                ),
                encoding="utf-8",
            )
            codex_accounts.mark_codex_account_runtime_unavailable(
                "lab", cache_path=cache, ttl_seconds=600
            )
            selected = codex_accounts.codex_account_candidates(
                cache_path=cache,
                profile_root=root,
            )

        self.assertEqual(selected, ["personal"])


if __name__ == "__main__":
    unittest.main()
