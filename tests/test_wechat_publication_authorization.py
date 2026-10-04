from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
sys.path.insert(0, str(SCRIPTS))

import wechat_chat_profiles as profiles
import wechat_direct_chatops as direct
import wechat_quote_reference as quotes
import wechat_task_worker as worker


class PublicationAuthorizationTests(unittest.TestCase):
    def row(self, text, local_type=1):
        return {"content": text, "local_type": local_type, "local_id": 2,
                "server_id": "source-2", "sender": "requester",
                "sender_display": "Member", "create_time": 1}

    def test_business_mention_does_not_start_consent_workflow(self):
        text = "@Colleague 客户可拍摄剪辑后发布，产品体验还可以如何优化？"
        row = self.row(text)
        self.assertFalse(direct.is_third_party_publish_permission_request(text))
        with mock.patch.object(direct, "find_pending_third_party_publish_task", return_value=None), \
                mock.patch.object(direct, "enqueue_third_party_publish_wait_task") as enqueue:
            result = direct.maybe_handle_third_party_publish_consent(
                {"include_recent_instruction_burst": False}, row, [row], focus_rows=[row],
            )
        self.assertIsNone(result)
        enqueue.assert_not_called()

    def test_no_video_does_not_create_automatic_consent_task(self):
        row = self.row("@Colleague can I publish this video?")
        with mock.patch.object(direct, "find_pending_third_party_publish_task", return_value=None), \
                mock.patch.object(direct, "source_reference_rows", return_value=[row]), \
                mock.patch.object(direct, "enqueue_third_party_publish_wait_task") as enqueue:
            result = direct.maybe_handle_third_party_publish_consent({}, row, [row], focus_rows=[row])
        self.assertIsNone(result)
        enqueue.assert_not_called()

    def test_agent_discussion_decision_is_not_overridden_by_permission_words(self):
        row = self.row("@Colleague can we publish videos as part of the proposed service?")
        video = self.row("<msg><videomsg md5='example' /></msg>", 43)
        video["local_id"] = 1
        with mock.patch.object(direct, "find_pending_third_party_publish_task", return_value=None), \
                mock.patch.object(direct, "source_reference_rows", return_value=[video, row]), \
                mock.patch.object(direct, "agent_route_decision", return_value={
                    "route_kind": "career_strategy", "public_publish_allowed": False,
                }) as router, \
                mock.patch.object(direct, "enqueue_third_party_publish_wait_task") as enqueue:
            result = direct.maybe_handle_third_party_publish_consent(
                {"agent_route_enabled": True}, row, [video, row], focus_rows=[row],
            )
        self.assertIsNone(result)
        router.assert_called_once()
        enqueue.assert_not_called()
        route = direct.enforce_route_safety(
            {"route_kind": "career_strategy", "public_publish_allowed": False},
            row["content"], {"route_kind": "publish_video"},
        )
        self.assertEqual(route["route_kind"], "career_strategy")
        self.assertFalse(route["public_publish_allowed"])

    def test_quotes_never_authorize_requester_override(self):
        pending = {"source": {"sender": "requester"}}
        text = "请做一个阶段规划。\n[quoted Assistant: 拍完后发布视频，系统已成熟。]"
        self.assertFalse(direct.requester_directly_authorizes_publish(pending, self.row(text), text))
        native = ("<msg><appmsg><type>57</type><title>请做一个阶段规划</title>"
                  "<refermsg><content>请发布视频</content></refermsg></appmsg></msg>")
        self.assertFalse(direct.has_public_publish_intent(native))
        self.assertFalse(direct.is_third_party_publish_permission_request(
            "请分析。\n[quoted Member: @Friend can I publish this video?]"))

    def test_quote_removal_preserves_later_coalesced_authorization(self):
        text = "Member: 分析一下。\n[quoted A: 内容 [nested] publish video]\nOwner: Please publish this video."
        self.assertEqual(quotes.without_quoted_evidence(text),
                         "Member: 分析一下。\n\nOwner: Please publish this video.")
        self.assertTrue(direct.has_public_publish_intent(text))
        self.assertFalse(direct.has_public_publish_intent("分析\n[quoted A: publish this video"))

    def test_disabled_chat_cannot_start_or_activate_consent(self):
        config = {"chat_name": "Company", "public_publish_enabled": False}
        row = self.row("@Colleague can I publish this video?")
        with mock.patch.object(direct, "find_pending_third_party_publish_task") as pending:
            self.assertIsNone(direct.maybe_handle_third_party_publish_consent(config, row, [row]))
        pending.assert_not_called()
        policy = direct.build_chat_response_policy(config)
        self.assertFalse(policy["public_publish_enabled"])
        self.assertNotIn("explicitly_authorized_video_publication", policy["capability_profile"]["capabilities"])
        self.assertTrue(direct.build_chat_response_policy({"chat_name": "Other"})["public_publish_enabled"])

    def test_permission_denial_survives_bad_router_output(self):
        config = {"chat_name": "Company", "public_publish_enabled": False}
        row = self.row("Please publish this video to YouTube.")
        fallback = direct.fallback_route_decision(config, row["content"], row, [row])
        route = direct.enforce_route_safety({
            "route_kind": "publish_video", "public_publish_allowed": True,
            "public_publish_intent": True, "external_action_allowed": True,
        }, row["content"], fallback)
        self.assertFalse(route["public_publish_allowed"])
        self.assertFalse(route["external_action_allowed"])
        self.assertFalse(route["public_publish_intent"])
        self.assertEqual(route["route_kind"], "other_worker")
        self.assertIn("Public video publication enabled: False", direct.build_agent_route_prompt(config, row, [row]))

    def test_strategy_context_never_borrows_private_dm_or_memo(self):
        with mock.patch.object(direct, "career_memory_snapshot", return_value="same-chat evidence") as memory, \
                mock.patch.object(direct, "local_project_surface") as inventory:
            context = direct.career_strategy_context_bundle({"chat_name": "Company"})
        memory.assert_called_once_with(["Company"])
        inventory.assert_not_called()
        self.assertIn("same-chat evidence", context)
        self.assertNotIn("LazyEdit/video publishing", context)
        with mock.patch.object(direct, "career_memory_snapshot") as memory:
            self.assertEqual(direct.career_strategy_context_bundle({}), "")
        memory.assert_not_called()

    def test_worker_rechecks_current_operator_policy_before_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "company.json"
            path.write_text(json.dumps({"chat_name": "Company", "public_publish_enabled": False}))
            task = {"chat": "Company", "source": {"config_id": path.name},
                    "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
                    "routine": {"id": "video_publish_existing"}, "request": "Please publish this video."}
            with mock.patch.object(worker, "PRIVATE", Path(temp)), \
                    mock.patch.object(worker, "enforce_current_task_route_safety"), \
                    mock.patch.object(worker, "prepare_worker_preflight") as preflight, \
                    mock.patch.object(worker, "run_worker_agent_session") as agent:
                self.assertFalse(worker.worker_public_publish_enabled(task))
                self.assertFalse(worker.should_deterministic_video_publish(task))
                self.assertFalse(worker.generated_video_public_publish_allowed(task))
                self.assertIsNone(worker.run_deterministic_lazyedit_publish(task, {}))
                self.assertEqual(worker.run_generated_video_lazyedit_command(
                    Path("unavailable.mp4"), task, {}, publish=True)["status"],
                    "publication_disabled_by_chat_operator")
                result = json.loads(worker.run_task_orchestrator(task, {}))
                self.assertTrue(result["no_reply"])
                preflight.assert_not_called()
                agent.assert_not_called()
                self.assertFalse(task["route_decision"]["public_publish_allowed"])

    def test_queued_denial_and_shared_profile_cannot_be_overridden(self):
        self.assertFalse(worker.worker_public_publish_enabled({
            "chat": "Company", "response_policy": {"public_publish_enabled": False},
        }))
        self.assertFalse(profiles.public_video_publication_enabled({"chat_name": "LabAgent"}))
        self.assertTrue(worker.worker_public_publish_enabled({"chat": "Other"}))


if __name__ == "__main__":
    unittest.main()
