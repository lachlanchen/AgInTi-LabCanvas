from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
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


class WeChatOpsApprovalTests(unittest.TestCase):
    def test_approve_story_confirmation_promotes_to_generated_video_and_preserves_story(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            story_path = Path(tmp) / "story.md"
            task = {
                "id": "task-story",
                "chat": "懒人科研",
                "status": "waiting_confirmation",
                "request": "Current coalesced request:\nWrite a LALACHAN story first.",
                "route_decision": {
                    "route_kind": "story_or_script",
                    "project": "lalachan",
                    "worker_needed": True,
                    "public_publish_allowed": False,
                },
                "routine": {"id": "story_script_generation"},
                "story_confirmation_required": True,
                "generation_blocked_until_story_confirmed": True,
                "result": {
                    "message": "A clean approved story about Uma Gumi and konnyaku.",
                    "files": [str(story_path)],
                    "confirmation": "这个故事可以用来生成 30s 视频吗？",
                },
            }
            queue.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")

            updated = wechat_ops.update_waiting_task(
                queue,
                "task-story",
                decision="approve",
                note="story ok generate video now",
            )

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["route_decision"]["route_kind"], "generate_video")
        self.assertEqual(updated["routine"]["id"], "generated_video")
        self.assertFalse(updated["story_confirmation_required"])
        self.assertFalse(updated["generation_blocked_until_story_confirmed"])
        self.assertEqual(updated["story_confirmation_result"]["message"], "A clean approved story about Uma Gumi and konnyaku.")
        self.assertEqual(updated["approved_story_files"], [str(story_path)])
        self.assertEqual(updated["stage_transition"]["from"], "story_script_generation")
        self.assertEqual(updated["stage_transition"]["to"], "generated_video")
        self.assertNotIn("result", updated)

    def test_approve_story_confirmation_negative_note_does_not_promote_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            task = {
                "id": "task-story",
                "chat": "懒人科研",
                "status": "waiting_confirmation",
                "request": "Current coalesced request:\nWrite a LALACHAN story first.",
                "route_decision": {"route_kind": "story_or_script", "project": "lalachan"},
                "routine": {"id": "story_script_generation"},
                "story_confirmation_required": True,
                "result": {
                    "message": "Draft story.",
                    "files": [],
                    "confirmation": "这个故事可以用来生成 30s 视频吗？",
                },
            }
            queue.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")

            updated = wechat_ops.update_waiting_task(
                queue,
                "task-story",
                decision="approve",
                note="story ok but do not generate video yet",
            )

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["route_decision"]["route_kind"], "story_or_script")
        self.assertEqual(updated["routine"]["id"], "story_script_generation")
        self.assertIn("result", updated)


class WeChatOpsUserScriptTests(unittest.TestCase):
    def test_install_user_scripts_writes_after_reboot_stack_launcher(self) -> None:
        original_home = os.environ.get("HOME")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HOME"] = tmp
            try:
                args = argparse.Namespace(json=True)
                with redirect_stdout(io.StringIO()) as stdout:
                    rc = wechat_ops.cmd_install_user_scripts(args)
            finally:
                if original_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = original_home

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            installed = payload["installed"]
            reboot_wrapper = Path(tmp) / "scripts" / "create-labcanvas-wechat-after-reboot.sh"
            stack_wrapper = Path(tmp) / "scripts" / "create-labcanvas-wechat-stack.sh"
            self.assertIn(str(reboot_wrapper), installed)
            self.assertTrue(reboot_wrapper.exists())
            self.assertTrue(stack_wrapper.exists())

            reboot_text = reboot_wrapper.read_text(encoding="utf-8")
            stack_text = stack_wrapper.read_text(encoding="utf-8")
            self.assertIn("wechat stack \"$ACTION\"", reboot_text)
            self.assertIn("WECHAT_CAREER_AGENT_EFFORT=${WECHAT_CAREER_AGENT_EFFORT:-xhigh}", reboot_text)
            self.assertIn("wechat career-agent status", reboot_text)
            self.assertIn("--career-session \"$WECHAT_CAREER_SESSION\"", stack_text)


if __name__ == "__main__":
    unittest.main()
