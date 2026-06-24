from __future__ import annotations

from pathlib import Path
import unittest

from agenticapp import wechat_ops


class WeChatOpsHealthTests(unittest.TestCase):
    def test_direct_monitor_health_reports_stale_sources_not_ready(self) -> None:
        original_discover = wechat_ops.discover_direct_monitor_configs
        original_config_health = wechat_ops.direct_config_health
        original_backend = wechat_ops.external_backend_summary
        original_separation = wechat_ops.direct_config_separation_summary
        try:
            wechat_ops.discover_direct_monitor_configs = lambda: [Path("echo.local.json")]  # type: ignore[assignment]
            wechat_ops.direct_config_health = lambda _path: {  # type: ignore[assignment]
                "ok": False,
                "chat_name": "EchoMind",
                "caught_up": True,
                "ready": False,
                "source_stale": True,
                "db_stale": True,
            }
            wechat_ops.external_backend_summary = lambda: {"ok": True}  # type: ignore[assignment]
            wechat_ops.direct_config_separation_summary = lambda _paths: {"ok": True}  # type: ignore[assignment]

            payload = wechat_ops.direct_monitor_health()
        finally:
            wechat_ops.discover_direct_monitor_configs = original_discover  # type: ignore[assignment]
            wechat_ops.direct_config_health = original_config_health  # type: ignore[assignment]
            wechat_ops.external_backend_summary = original_backend  # type: ignore[assignment]
            wechat_ops.direct_config_separation_summary = original_separation  # type: ignore[assignment]

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["caught_up_groups"], 1)
        self.assertEqual(payload["ready_groups"], 0)
        self.assertEqual(payload["stale_source_groups"], 1)
        self.assertIn("ready also requires", payload["notes"][-1])


if __name__ == "__main__":
    unittest.main()
