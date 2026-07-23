from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / "scripts"
    / "codex_quota_status.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "codex_quota_status_for_tests",
        MODULE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CodexQuotaStatusTests(unittest.TestCase):
    def sample_response(
        self,
        *,
        codex_used: int = 97,
        has_credits: bool = False,
        credit_balance: str = "0",
    ) -> dict:
        return {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": codex_used,
                    "windowDurationMins": 10080,
                    "resetsAt": 1785258202,
                },
                "credits": {
                    "hasCredits": has_credits,
                    "unlimited": False,
                    "balance": credit_balance,
                },
                "planType": "pro",
            },
            "rateLimitsByLimitId": {
                "codex_bengalfox": {
                    "limitId": "codex_bengalfox",
                    "limitName": "GPT-5.3-Codex-Spark",
                    "primary": {
                        "usedPercent": 0,
                        "windowDurationMins": 10080,
                    },
                },
                "codex": {
                    "limitId": "codex",
                    "primary": {
                        "usedPercent": codex_used,
                        "windowDurationMins": 10080,
                        "resetsAt": 1785258202,
                    },
                    "credits": {
                        "hasCredits": has_credits,
                        "unlimited": False,
                        "balance": credit_balance,
                    },
                    "planType": "pro",
                },
            },
        }

    def test_normalizes_normal_codex_bucket_and_ignores_spark_bucket(self) -> None:
        module = load_module()

        status = module.normalize_rate_limit_response(
            self.sample_response(),
            threshold_percent=5,
            observed_at=100,
        )

        self.assertTrue(status["warning"])
        self.assertEqual(status["remaining_percent"], 3)
        self.assertEqual(status["window"]["window_duration_mins"], 10080)
        self.assertEqual(status["limit_id"], "codex")
        self.assertTrue(status["codex_available"])

    def test_threshold_is_strictly_below_five_percent(self) -> None:
        module = load_module()

        status = module.normalize_rate_limit_response(
            self.sample_response(codex_used=95),
            threshold_percent=5,
        )

        self.assertFalse(status["warning"])

    def test_warning_matches_request_language_and_includes_reset(self) -> None:
        module = load_module()
        status = module.normalize_rate_limit_response(self.sample_response())

        chinese = module.format_warning(status, request_text="请继续这个任务")
        english = module.format_warning(status, request_text="Continue this task")

        self.assertIn("仅剩 3%", chinese)
        self.assertIn("2026-07-29", chinese)
        self.assertIn("3% remaining", english)

    def test_purchased_credits_keep_codex_available_after_weekly_exhaustion(self) -> None:
        module = load_module()
        status = module.normalize_rate_limit_response(
            self.sample_response(
                codex_used=100,
                has_credits=True,
                credit_balance="5000.0000000000",
            )
        )

        self.assertTrue(status["warning"])
        self.assertFalse(status["weekly_quota_available"])
        self.assertTrue(status["credits_available"])
        self.assertTrue(status["codex_available"])
        self.assertIn("已购额度余额 5000", module.format_warning(status, request_text="继续"))
        self.assertIn("Codex 会继续执行", module.format_warning(status, request_text="继续"))

    def test_fresh_cache_avoids_another_app_server_probe(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "quota.json"
            status = module.normalize_rate_limit_response(
                self.sample_response(),
                observed_at=module.now_epoch(),
            )
            cache.write_text(json.dumps(status), encoding="utf-8")
            with mock.patch.object(module, "probe_status") as probe:
                loaded = module.current_status(
                    cache_path=cache,
                    max_age_seconds=180,
                    threshold_percent=2,
                )

        self.assertEqual(loaded["remaining_percent"], 3)
        self.assertFalse(loaded["warning"])
        probe.assert_not_called()

    def test_resolves_codex_from_nvm_when_service_path_is_minimal(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".nvm" / "versions" / "node" / "v22.0.0" / "bin" / "codex"
            codex.parent.mkdir(parents=True)
            codex.write_text("#!/bin/sh\n", encoding="utf-8")
            codex.chmod(0o755)
            with mock.patch.object(module.shutil, "which", return_value=None), mock.patch.dict(
                os.environ,
                {"CODEX_BIN": ""},
                clear=False,
            ):
                resolved = module.resolve_codex_bin(home=home)

        self.assertEqual(resolved, str(codex.resolve()))


if __name__ == "__main__":
    unittest.main()
