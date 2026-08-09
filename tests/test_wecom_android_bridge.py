from __future__ import annotations

from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_bridge.py"
)


def load_bridge():
    spec = importlib.util.spec_from_file_location("wecom_android_bridge_for_tests", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_worker():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_task_worker.py"
    spec = importlib.util.spec_from_file_location("wechat_task_worker_for_android_tests", path)
    assert spec and spec.loader
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ingest():
    path = ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_ingest.py"
    scripts_dir = str(path.parent)
    shared_dir = str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts")
    for directory in (scripts_dir, shared_dir):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location("wecom_ingest_for_android_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeComAndroidBridgeTests(unittest.TestCase):
    def test_bounds_and_chat_title_are_exact(self) -> None:
        bridge = load_bridge()

        self.assertEqual(bridge.bounds_center("[10,20][110,220]"), (60, 120))
        self.assertTrue(bridge.chat_title_matches("LabAgent(6)", "LabAgent"))
        self.assertTrue(bridge.chat_title_matches("AgentTest", "AgentTest"))
        self.assertFalse(bridge.chat_title_matches("LabAgent archive(6)", "LabAgent"))

    def test_sequence_delta_preserves_repeated_new_message(self) -> None:
        bridge = load_bridge()

        delta, overlap = bridge.sequence_delta(["a", "b"], ["a", "b", "b"])

        self.assertEqual(overlap, 2)
        self.assertEqual(delta, ["b"])

    def test_raw_android_screencap_round_trips_to_png(self) -> None:
        bridge = load_bridge()
        width, height = 4, 3
        rgba = bytes(
            value
            for pixel in range(width * height)
            for value in (pixel * 7 % 256, pixel * 11 % 256, pixel * 13 % 256, 255)
        )
        payload = bridge.struct.pack("<IIII", width, height, 1, 1) + rgba

        screenshot = bridge.parse_raw_screencap(payload)
        cropped = bridge.crop_raw_screenshot(screenshot, "[1,1][4,3]")
        png = bridge.encode_rgba_png(cropped)

        self.assertEqual((screenshot.width, screenshot.height), (4, 3))
        self.assertEqual((cropped.width, cropped.height), (3, 2))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_file_confirmation_requires_exact_chat_file_and_send(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node text="">
              <node text="发送给：" package="com.tencent.wework" />
              <node text="AgentTest" package="com.tencent.wework" />
              <node text="[文件] mobile-transport-test.pdf (607K)" package="com.tencent.wework" />
              <node text="发送" package="com.tencent.wework" clickable="true" bounds="[1,1][2,2]" />
            </node></hierarchy>
            """
        )

        self.assertTrue(
            bridge.validate_file_confirmation(root, "AgentTest", "mobile-transport-test.pdf")
        )
        self.assertFalse(
            bridge.validate_file_confirmation(root, "LabAgent", "mobile-transport-test.pdf")
        )
        self.assertFalse(bridge.validate_file_confirmation(root, "AgentTest", "other.pdf"))

    def test_file_confirmation_accepts_exact_chat_with_member_count(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node text="">
              <node text="发送给：" package="com.tencent.wework" />
              <node text="LabAgent(6)" package="com.tencent.wework" />
              <node text="[文件] report.pdf (227K)" package="com.tencent.wework" />
              <node text="发送" package="com.tencent.wework" clickable="true" bounds="[1,1][2,2]" />
            </node></hierarchy>
            """
        )

        self.assertTrue(bridge.validate_file_confirmation(root, "LabAgent", "report.pdf"))
        self.assertFalse(bridge.validate_file_confirmation(root, "Lab", "report.pdf"))

    def test_document_file_match_excludes_search_editor(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="report.pdf" package="com.google.android.documentsui"
                    class="android.widget.EditText"
                    resource-id="com.google.android.documentsui:id/search_src_text" />
              <node text="report.pdf" package="com.google.android.documentsui"
                    class="android.widget.TextView"
                    resource-id="android:id/title" />
            </node></hierarchy>
            """
        )

        matches = bridge.exact_document_file_nodes(root, "report.pdf")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].attrib["resource-id"], "android:id/title")

    def test_picker_filename_is_short_deterministic_and_keeps_extension(self) -> None:
        bridge = load_bridge()
        original = "2026-07-22-organoid-biomanufacturing-scifi-briefing.pdf"

        shortened = bridge.picker_safe_filename(original, "0123456789abcdef")

        self.assertLessEqual(len(shortened), 36)
        self.assertTrue(shortened.endswith("-01234567.pdf"))
        self.assertEqual(bridge.picker_safe_filename("short.pdf", "deadbeef"), "short.pdf")

    def test_file_card_match_accepts_middle_ellipsis_but_not_wrong_suffix(self) -> None:
        bridge = load_bridge()
        filename = "brain_organoid_vascular_integra-557240a2.pdf"

        self.assertTrue(
            bridge.filename_display_matches(
                "brain_organoid_vas\ncular_integra...2.pdf",
                filename,
            )
        )
        self.assertFalse(
            bridge.filename_display_matches(
                "brain_organoid_vas\ncular_integra...3.pdf",
                filename,
            )
        )

    def test_visible_file_card_match_is_limited_to_wecom_nodes(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="brain_organoid_vas...2.pdf" package="com.google.android.documentsui" />
              <node text="brain_organoid_vas...2.pdf" package="com.tencent.wework" />
            </node></hierarchy>
            """
        )

        self.assertTrue(
            bridge.visible_file_card_matches(
                root,
                "brain_organoid_vascular_integra-557240a2.pdf",
            )
        )

    def test_visible_file_recovery_accepts_legacy_long_filename(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="brain_organoid_vas\ncular_integra...2.pdf" package="com.tencent.wework" />
            </node></hierarchy>
            """
        )

        self.assertFalse(
            bridge.visible_file_card_matches(root, "brain_organoid_vas-557240a2.pdf")
        )
        self.assertTrue(
            bridge.visible_file_card_matches(
                root,
                "brain_organoid_vascular_integration_deep_report_2026-07-22.pdf",
            )
        )

    def test_delivery_status_reads_exact_task_component_without_gui(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "report.pdf"
            artifact.write_bytes(b"%PDF-1.4\n")
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            digest = bridge.sha256_file(artifact)
            value_hash = f"{digest}:{artifact.name}"
            key = runtime.component_key("task-1", "LabAgent", "file", value_hash)
            runtime.mark_component(
                key,
                task_id="task-1",
                chat="LabAgent",
                kind="file",
                value_hash=value_hash,
                status="sent",
            )

            status = runtime.delivery_status(
                "LabAgent", "", [artifact], task_id="task-1"
            )

        self.assertTrue(status["complete"])
        self.assertEqual(status["sent_files"], [str(artifact.resolve())])
        self.assertEqual(status["pending_files"], [])

    def test_delivery_status_preserves_verified_text_component_time(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            message = "Research complete."
            value_hash = bridge.text_component_value_hash(message, [])
            key = runtime.component_key(
                "task-text", "LabAgent", "text", value_hash
            )
            runtime.mark_component(
                key,
                task_id="task-text",
                chat="LabAgent",
                kind="text",
                value_hash=value_hash,
                status="sent",
            )
            expected_sent_at = runtime.component_record(key)["updated_at"]

            status = runtime.delivery_status(
                "LabAgent", message, [], task_id="task-text"
            )

        self.assertTrue(status["complete"])
        self.assertEqual(status["sent_messages"], [message])
        self.assertEqual(status["sent_message_times"], {message: expected_sent_at})

    def test_delivery_status_deduplicates_same_file_bytes_across_tasks(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first-name.pdf"
            second = root / "renamed-copy.pdf"
            first.write_bytes(b"%PDF-1.4\nsame bytes\n")
            second.write_bytes(first.read_bytes())
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            digest = bridge.sha256_file(first)
            value_hash = f"{digest}:{first.name}"
            key = runtime.component_key("task-old", "LabAgent", "file", value_hash)
            runtime.mark_component(
                key,
                task_id="task-old",
                chat="LabAgent",
                kind="file",
                value_hash=value_hash,
                status="sent",
            )

            status = runtime.delivery_status(
                "LabAgent", "", [second], task_id="task-new"
            )

        self.assertTrue(status["complete"])
        self.assertEqual(status["sent_files"], [str(second.resolve())])
        self.assertEqual(status["pending_files"], [])

    def test_send_file_skips_cross_task_duplicate_before_android_staging(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first-name.pdf"
            second = root / "renamed-copy.pdf"
            first.write_bytes(b"%PDF-1.4\nsame bytes\n")
            second.write_bytes(first.read_bytes())
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            digest = bridge.sha256_file(first)
            old_value = f"{digest}:{first.name}"
            old_key = runtime.component_key("task-old", "LabAgent", "file", old_value)
            runtime.mark_component(
                old_key,
                task_id="task-old",
                chat="LabAgent",
                kind="file",
                value_hash=old_value,
                status="sent",
            )
            runtime.stage_file = mock.Mock(side_effect=AssertionError("must not stage duplicate"))

            result = runtime.send_file_locked(
                "LabAgent", second, task_id="task-new"
            )
            new_key = runtime.component_key(
                "task-new", "LabAgent", "file", f"{digest}:{second.name}"
            )
            new_status = runtime.component_record(new_key)["status"]

        self.assertTrue(result["ok"])
        self.assertTrue(result["deduplicated"])
        self.assertEqual(new_status, "deduplicated")
        runtime.stage_file.assert_not_called()

    def test_send_file_force_resend_bypasses_cross_task_content_guard(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "report.pdf"
            artifact.write_bytes(b"%PDF-1.4\nsame bytes\n")
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            digest = bridge.sha256_file(artifact)
            value_hash = f"{digest}:{artifact.name}"
            old_key = runtime.component_key("task-old", "LabAgent", "file", value_hash)
            runtime.mark_component(
                old_key,
                task_id="task-old",
                chat="LabAgent",
                kind="file",
                value_hash=value_hash,
                status="sent",
            )
            runtime.stage_file = mock.Mock(side_effect=bridge.BridgeError("staging reached"))

            with self.assertRaisesRegex(bridge.BridgeError, "staging reached"):
                runtime.send_file_locked(
                    "LabAgent", artifact, task_id="task-new", force_resend=True
                )

        runtime.stage_file.assert_called_once_with(artifact)

    def test_batch_send_delivers_artifacts_before_completion_text(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "structure.png"
            artifact.write_bytes(b"png")
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            order: list[str] = []

            def send_file(*_args, **_kwargs):
                order.append("file")
                return {"sent_files": [str(artifact.resolve())]}

            def send_text(*_args, **_kwargs):
                order.append("text")
                return {"sent_messages": ["done"], "mentioned_users": []}

            with mock.patch.object(runtime, "serialized", return_value=nullcontext()), mock.patch.object(
                runtime, "send_file_locked", side_effect=send_file
            ), mock.patch.object(runtime, "send_text_resilient_locked", side_effect=send_text):
                result = runtime.send(
                    "LabAgent",
                    "done",
                    [artifact],
                    task_id="protein-task",
                )

        self.assertTrue(result["ok"])
        self.assertEqual(order, ["file", "text"])
        self.assertEqual(result["sent_files"], [str(artifact.resolve())])

    def test_open_chat_waits_through_transitional_hierarchy(self) -> None:
        bridge = load_bridge()
        chat_list = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent" resource-id="com.tencent.wework:id/iql"
                    package="com.tencent.wework" clickable="true" bounds="[0,0][100,100]" />
            </node></hierarchy>
            """
        )
        loading = ET.fromstring('<hierarchy><node package="com.tencent.wework" /></hierarchy>')
        opened = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            with mock.patch.object(runtime, "launch_wecom"), mock.patch.object(
                runtime, "dump_hierarchy", side_effect=[chat_list, loading, opened]
            ), mock.patch.object(runtime, "tap_node") as tap, mock.patch.object(
                runtime, "current_package", return_value=runtime.package
            ), mock.patch.object(bridge.time, "sleep"):
                result = runtime.open_chat("LabAgent")

        tap.assert_called_once()
        self.assertEqual(bridge.visible_chat_title(result), "LabAgent(6)")

    def test_launch_wecom_trusts_focused_activity_when_hierarchy_is_stale(self) -> None:
        bridge = load_bridge()
        stale = ET.fromstring('<hierarchy><node package="android" /></hierarchy>')
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.prepare_device = mock.Mock()
            runtime.dump_hierarchy = mock.Mock(return_value=stale)
            runtime.current_package = mock.Mock(return_value=runtime.package)
            runtime.adb_shell = mock.Mock()

            runtime.launch_wecom()

        runtime.adb_shell.assert_not_called()

    def test_status_uses_focused_activity_when_hierarchy_is_unreadable(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.run = mock.Mock(
                return_value=subprocess.CompletedProcess([], 0, stdout="test\tdevice\n", stderr="")
            )
            runtime.serialized = mock.Mock(return_value=nullcontext())
            runtime.dump_hierarchy = mock.Mock(
                side_effect=bridge.BridgeError("temporary UIAutomator failure")
            )
            runtime.current_package = mock.Mock(return_value=runtime.package)

            result = runtime.status()

        self.assertTrue(result["wecom_foreground"])
        self.assertEqual(result["surface_state"], "wecom_other")

    def test_running_service_status_returns_persistent_relay_snapshot(self) -> None:
        bridge = load_bridge()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "ok": True,
                        "transport": "wecom_android",
                        "started_at": "2026-08-09T12:48:47",
                        "last_poll_success_at": "2026-08-09T13:04:00",
                    }
                ).encode("utf-8")

        with mock.patch.object(bridge.urlrequest, "urlopen", return_value=Response()) as urlopen:
            result = bridge.running_service_status(
                {"local_api_port": 19581, "local_api_token": "secret"}
            )

        self.assertEqual(result["started_at"], "2026-08-09T12:48:47")
        self.assertEqual(result["last_poll_success_at"], "2026-08-09T13:04:00")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:19581/v1/status")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def test_running_service_status_falls_back_when_service_is_offline(self) -> None:
        bridge = load_bridge()
        with mock.patch.object(
            bridge.urlrequest,
            "urlopen",
            side_effect=bridge.urlerror.URLError("offline"),
        ):
            result = bridge.running_service_status(
                {"local_api_port": 19581, "local_api_token": "secret"}
            )

        self.assertIsNone(result)

    def test_anr_recovery_chooses_wait_without_closing_wecom(self) -> None:
        bridge = load_bridge()
        anr = ET.fromstring(
            """
            <hierarchy><node>
              <node text="企业微信没有响应" package="android" />
              <node text="关闭应用" package="android" clickable="true"
                    bounds="[0,0][100,100]" />
              <node text="等待" package="android" clickable="true"
                    bounds="[0,100][100,200]" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.tap_node = mock.Mock()
            with mock.patch.object(bridge.time, "sleep"):
                recovered = runtime.dismiss_anr_dialog(anr)

        self.assertTrue(recovered)
        runtime.tap_node.assert_called_once()
        tapped = runtime.tap_node.call_args.args[1]
        self.assertEqual(tapped.attrib["text"], "等待")
        self.assertEqual(runtime.poll_health_snapshot()["last_recovery_action"], "anr_wait")

    def test_open_chat_list_backs_out_of_internal_article(self) -> None:
        bridge = load_bridge()
        article = ET.fromstring(
            """
            <hierarchy><node package="com.tencent.wework">
              <node text="Kimi K3: second only to Fable 5"
                    package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        chat_list = ET.fromstring(
            """
            <hierarchy><node>
              <node text="消息" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
              <node text="LabAgent" resource-id="com.tencent.wework:id/iql"
                    package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.launch_wecom = mock.Mock()
            runtime.dump_hierarchy = mock.Mock(side_effect=[article, chat_list])
            runtime.press_back = mock.Mock()

            result = runtime.open_chat_list()

        self.assertIs(result, chat_list)
        runtime.press_back.assert_called_once_with()

    def test_open_chat_list_restarts_app_once_after_bounded_navigation(self) -> None:
        bridge = load_bridge()
        stuck = ET.fromstring(
            '<hierarchy><node package="com.tencent.wework" text="stuck" /></hierarchy>'
        )
        chat_list = ET.fromstring(
            """
            <hierarchy><node>
              <node text="消息" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
              <node text="LabAgent" resource-id="com.tencent.wework:id/iql"
                    package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.launch_wecom = mock.Mock()
            runtime.dump_hierarchy = mock.Mock(side_effect=[*[stuck] * 8, chat_list])
            runtime.press_back = mock.Mock()
            runtime.restart_wecom_preserving_session = mock.Mock(return_value=stuck)

            result = runtime.open_chat_list()

        self.assertIs(result, chat_list)
        self.assertEqual(runtime.press_back.call_count, 8)
        runtime.restart_wecom_preserving_session.assert_called_once_with(
            reason="open_chat_list"
        )

    def test_poll_health_fails_after_repeated_surface_errors(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.record_poll_failure("WeCom chat list is not visible")
            runtime.record_poll_failure("WeCom chat list is not visible")

            health = runtime.poll_health_snapshot()

        self.assertFalse(health["poll_healthy"])
        self.assertEqual(health["consecutive_poll_failures"], 2)
        self.assertIn("chat list", health["last_poll_error"])

    def test_poll_health_allows_bounded_active_reconciliation(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime._poll_health.update(
                {
                    "last_poll_attempt_at": (
                        bridge.datetime.now() - bridge.timedelta(seconds=300)
                    ).isoformat(timespec="seconds"),
                    "poll_in_progress": True,
                }
            )

            health = runtime.poll_health_snapshot()

        self.assertTrue(health["poll_healthy"])
        self.assertFalse(health["poll_stale"])
        self.assertEqual(health["poll_stale_after_seconds"], 900)

    def test_poll_health_stales_wedged_active_reconciliation(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime._poll_health.update(
                {
                    "last_poll_attempt_at": (
                        bridge.datetime.now() - bridge.timedelta(seconds=1200)
                    ).isoformat(timespec="seconds"),
                    "poll_in_progress": True,
                }
            )

            health = runtime.poll_health_snapshot()

        self.assertFalse(health["poll_healthy"])
        self.assertTrue(health["poll_stale"])
        self.assertEqual(health["poll_stale_after_seconds"], 900)

    def test_poll_health_keeps_short_idle_watchdog(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime._poll_health.update(
                {
                    "last_poll_attempt_at": (
                        bridge.datetime.now() - bridge.timedelta(seconds=300)
                    ).isoformat(timespec="seconds"),
                    "poll_in_progress": False,
                }
            )

            health = runtime.poll_health_snapshot()

        self.assertFalse(health["poll_healthy"])
        self.assertTrue(health["poll_stale"])
        self.assertEqual(health["poll_stale_after_seconds"], 180)

    def test_surface_failure_matching_is_case_insensitive(self) -> None:
        bridge = load_bridge()

        error = bridge.AndroidBridge.surface_failure_text(
            "BridgeError: WeCom changed chat during send"
        )

        self.assertIn("changed chat", error)

    def test_surface_recovery_is_cooled_down_after_failure(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                    "surface_recovery_cooldown_seconds": 300,
                }
            )
            runtime.recover_transport_surface = mock.Mock(
                side_effect=bridge.BridgeError("WeCom did not reach the foreground")
            )
            runtime.serialized = mock.Mock(return_value=nullcontext())

            first = runtime.recover_transport_surface_bounded(reason="poll_exception")
            second = runtime.recover_transport_surface_bounded(reason="poll_exception")
            health = runtime.poll_health_snapshot()

        self.assertFalse(first["ok"])
        self.assertIn("did not reach the foreground", first["error"])
        self.assertEqual(second["skipped"], "cooldown")
        self.assertGreater(second["retry_after_seconds"], 0)
        runtime.recover_transport_surface.assert_called_once_with(reason="poll_exception")
        self.assertTrue(health["last_recovery_attempt_at"])
        self.assertTrue(health["last_recovery_failure_at"])
        self.assertIn("did not reach the foreground", health["last_recovery_error"])

    def test_normalize_chat_surface_dismisses_stale_attachment_choice(self) -> None:
        bridge = load_bridge()
        stale = ET.fromstring(
            """
            <hierarchy><node>
              <node text="从本地文件选择" package="com.tencent.wework" />
              <node text="从微盘选择" package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        composer = ET.fromstring(
            """
            <hierarchy><node>
              <node text="" resource-id="com.tencent.wework:id/j28"
                    package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.current_package = mock.Mock(return_value=bridge.PACKAGE)
            runtime.open_chat = mock.Mock(side_effect=[stale, composer])
            runtime.press_back = mock.Mock()

            result = runtime.normalize_chat_surface("LabAgent")

        self.assertIs(result, composer)
        runtime.press_back.assert_called_once_with()

    def test_normalize_chat_surface_restores_text_composer_from_voice_mode(self) -> None:
        bridge = load_bridge()
        voice_mode = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
              <node text="按住 说话" resource-id="com.tencent.wework:id/j26"
                    package="com.tencent.wework" />
              <node text="" resource-id="com.tencent.wework:id/hvp"
                    package="com.tencent.wework" clickable="true" bounds="[0,0][100,100]" />
            </node></hierarchy>
            """
        )
        composer = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
              <node text="" resource-id="com.tencent.wework:id/j28"
                    package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.current_package = mock.Mock(return_value=bridge.PACKAGE)
            runtime.open_chat = mock.Mock(return_value=voice_mode)
            runtime.dump_hierarchy = mock.Mock(return_value=composer)
            runtime.tap_node = mock.Mock()
            runtime.press_back = mock.Mock()

            with mock.patch.object(bridge.time, "sleep"):
                result = runtime.normalize_chat_surface("LabAgent")

        self.assertIs(result, composer)
        runtime.tap_node.assert_called_once()
        runtime.press_back.assert_not_called()

    def test_open_file_action_retries_after_first_tap_only_hides_keyboard(self) -> None:
        bridge = load_bridge()
        composer = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
              <node text="" resource-id="com.tencent.wework:id/j1v"
                    package="com.tencent.wework" clickable="true" bounds="[0,0][100,100]" />
            </node></hierarchy>
            """
        )
        menu = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i"
                    package="com.tencent.wework" />
              <node text="文件" package="com.tencent.wework" clickable="true"
                    bounds="[0,0][100,100]" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.ensure_chat_identity = mock.Mock(side_effect=[composer, menu])
            runtime.tap_node = mock.Mock()

            with mock.patch.object(bridge.time, "sleep"):
                found_menu, action = runtime.open_file_action(
                    "LabAgent",
                    composer,
                    attempts=2,
                    polls_per_attempt=1,
                )

        self.assertIs(found_menu, menu)
        self.assertEqual(action.attrib.get("text"), "文件")
        self.assertEqual(runtime.tap_node.call_count, 2)

    def test_send_text_normalizes_chat_surface_before_composing(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="" resource-id="com.tencent.wework:id/j28" package="com.tencent.wework" />
              <node text="发送" resource-id="com.tencent.wework:id/j24" package="com.tencent.wework" clickable="true" />
              <node text="正在处理" resource-id="com.tencent.wework:id/j1l" package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.normalize_chat_surface = mock.Mock(return_value=root)
            runtime.open_chat = mock.Mock(side_effect=AssertionError("open_chat should not bypass normalization"))
            runtime.tap_node = mock.Mock()
            runtime.paste_text = mock.Mock()
            runtime.wait_for_composer_message = mock.Mock(return_value=root)
            runtime.ensure_chat_identity = mock.Mock(return_value=root)
            with mock.patch.object(bridge.time, "sleep"):
                result = runtime.send_text_locked(
                    "LabAgent", "正在处理", task_id="task-normalize"
                )

        self.assertTrue(result["ok"])
        runtime.normalize_chat_surface.assert_called_once_with("LabAgent")
        runtime.open_chat.assert_not_called()

    def test_incomplete_native_mention_draft_is_structural_not_human_text(self) -> None:
        bridge = load_bridge()

        self.assertTrue(bridge.incomplete_native_mention_draft("\ufff37881300683907109\ufff0@"))
        self.assertTrue(
            bridge.incomplete_native_mention_draft(
                "\ufff37881300683907109\ufff0 \ufff312345\ufff0＠"
            )
        )
        self.assertFalse(bridge.incomplete_native_mention_draft("@sunnyyty please review"))
        self.assertFalse(
            bridge.incomplete_native_mention_draft(
                "\ufff37881300683907109\ufff0 this is a human-authored draft"
            )
        )

    def test_native_mentions_remove_only_matching_plain_leading_copies(self) -> None:
        bridge = load_bridge()

        self.assertEqual(
            bridge.strip_redundant_leading_mentions(
                "@陈苗 这是正文。", ["陈苗@微信"]
            ),
            "这是正文。",
        )
        self.assertEqual(
            bridge.strip_redundant_leading_mentions(
                "＠陈苗＠微信：这是正文。", ["陈苗@微信"]
            ),
            "这是正文。",
        )
        self.assertEqual(
            bridge.strip_redundant_leading_mentions(
                "@陈苗 @megamonster 请一起看。", ["陈苗@微信", "megamonster@微信"]
            ),
            "请一起看。",
        )
        self.assertEqual(
            bridge.strip_redundant_leading_mentions(
                "请和 @陈苗 一起看。", ["陈苗@微信"]
            ),
            "请和 @陈苗 一起看。",
        )
        self.assertEqual(
            bridge.strip_redundant_leading_mentions("@陈苗 这是正文。", []),
            "@陈苗 这是正文。",
        )

    def test_send_reports_requested_text_but_composes_without_duplicate_mention(
        self,
    ) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "android.lock"
            runtime.send_text_resilient_locked = mock.Mock(
                return_value={
                    "ok": True,
                    "sent_messages": ["这是正文。"],
                    "mentioned_users": ["陈苗@微信"],
                }
            )

            result = runtime.send(
                "LabAgent",
                "@陈苗 这是正文。",
                [],
                task_id="task-no-double-at",
                mentions=["陈苗@微信"],
            )

        runtime.send_text_resilient_locked.assert_called_once_with(
            "LabAgent",
            "这是正文。",
            task_id="task-no-double-at",
            mentions=["陈苗@微信"],
        )
        self.assertEqual(result["sent_messages"], ["@陈苗 这是正文。"])
        self.assertEqual(result["mentioned_users"], ["陈苗@微信"])

    def test_recovers_ledger_owned_draft_and_marks_it_abandoned(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            key = runtime.component_key("old-task", "LabAgent", "text", "old-hash")
            runtime.mark_component(
                key,
                task_id="old-task",
                chat="LabAgent",
                kind="text",
                value_hash="old-hash",
                status="composing",
                details={"draft_owner": "wecom_android_bridge"},
            )
            with mock.patch.object(runtime, "clear_automation_draft", return_value=True) as clear:
                recovered = runtime.recover_stale_automation_draft(
                    "LabAgent", "a complete prior automation draft"
                )

            record = runtime.component_record(key)

        self.assertTrue(recovered)
        clear.assert_called_once_with("LabAgent")
        self.assertEqual(record["status"], "abandoned")
        self.assertEqual(record["details"]["abandoned_reason"], "recovered_owned_draft")

    def test_recovers_legacy_native_mention_residue_without_ledger_marker(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            with mock.patch.object(runtime, "clear_automation_draft", return_value=True) as clear:
                recovered = runtime.recover_stale_automation_draft(
                    "LabAgent", "\ufff37881300683907109\ufff0@"
                )

        self.assertTrue(recovered)
        clear.assert_called_once_with("LabAgent")

    def test_preserves_unowned_human_draft(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            with mock.patch.object(runtime, "clear_automation_draft", return_value=True) as clear:
                recovered = runtime.recover_stale_automation_draft(
                    "LabAgent", "human draft: do not overwrite"
                )

        self.assertFalse(recovered)
        clear.assert_not_called()

    def test_serialized_lock_has_bounded_busy_failure(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            with mock.patch.object(
                bridge.fcntl, "flock", side_effect=BlockingIOError
            ), mock.patch.object(bridge.time, "monotonic", side_effect=[0.0, 1.0]):
                with self.assertRaisesRegex(bridge.BridgeError, "WECOM_ANDROID_BUSY"):
                    with runtime.serialized(timeout_seconds=0.1):
                        self.fail("busy lock must not be entered")

    def test_parse_messages_distinguishes_inbound_and_own_rows(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="sunnyyty" package="com.tencent.wework" />
            <node text="＠微信" package="com.tencent.wework" />
            <node text="请帮我查论文" resource-id="com.tencent.wework:id/j1l" package="com.tencent.wework" />
          </node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="报告已发送" resource-id="com.tencent.wework:id/j1l" package="com.tencent.wework" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "serial": "test",
                "target_groups": ["LabAgent"],
                "state_db": str(Path(tmp) / "state.sqlite"),
                "staging_dir": str(Path(tmp) / "staging"),
            }
            runtime = bridge.AndroidBridge(config)
            records = runtime.parse_messages(ET.fromstring(xml))

        self.assertEqual(records[0]["direction"], "inbound")
        self.assertEqual(records[0]["sender"], "sunnyyty")
        self.assertEqual(records[0]["mention_name"], "sunnyyty@微信")
        self.assertEqual(records[0]["body"], "请帮我查论文")
        self.assertEqual(records[0]["quote_text"], "")
        self.assertEqual(records[1]["direction"], "outbound")

    def test_build_event_batch_keeps_forwarded_card_and_follow_up_together(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            records = [
                {
                    "fingerprint": "card",
                    "direction": "inbound",
                    "sender": "陈苗",
                    "sender_identity_confidence": "visible_row_label",
                    "body": "公众号文章卡片\n<title>高光谱成像技术用于厚度测量</title>",
                    "source_kind": "wechat_article_card",
                    "source_title": "高光谱成像技术用于厚度测量",
                },
                {
                    "fingerprint": "follow-up",
                    "direction": "inbound",
                    "sender": "陈苗",
                    "sender_identity_confidence": "visible_row_label",
                    "body": "这个能用在生物和类器官里面吗",
                    "source_kind": "text",
                },
            ]
            event = runtime.build_event_batch("LabAgent", records)

        self.assertEqual(event["msgtype"], "wechat_article_card")
        self.assertEqual(event["source_metadata"]["kind"], "combined_forward")
        self.assertEqual(event["source_metadata"]["message_count"], 2)
        self.assertIn("高光谱成像技术用于厚度测量", event["text"])
        self.assertIn("这个能用在生物和类器官里面吗", event["text"])
        other = {**records[-1], "fingerprint": "other", "sender": "sunnyyty"}
        self.assertEqual(
            bridge.coalesce_sender_records([*records, other]),
            [records, [other]],
        )
        consecutive_text = [
            {
                "fingerprint": "first-text",
                "direction": "inbound",
                "sender": "sunnyyty",
                "body": "先看血管类器官",
                "source_kind": "text",
            },
            {
                "fingerprint": "second-text",
                "direction": "inbound",
                "sender": "sunnyyty",
                "body": "然后聚焦血管化肿瘤",
                "source_kind": "text",
            },
        ]
        self.assertEqual(
            bridge.coalesce_sender_records(consecutive_text),
            [consecutive_text],
        )

    def test_snapshot_moves_to_live_tail_before_parsing(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "android.lock"
            latest = ET.fromstring(
                '<hierarchy><node text="LabAgent(6)" /></hierarchy>'
            )
            runtime.open_chat = mock.Mock(return_value=latest)
            runtime.move_chat_to_live_tail = mock.Mock(return_value=latest)
            runtime.parse_messages = mock.Mock(return_value=[])

            result = runtime.snapshot("LabAgent")

        self.assertTrue(result["ok"])
        runtime.move_chat_to_live_tail.assert_called_once_with("LabAgent", latest)
        runtime.parse_messages.assert_called_once_with(latest)

    def test_move_chat_to_live_tail_swipes_up_toward_newer_rows(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            root = ET.fromstring(
                """
                <hierarchy>
                  <node text="LabAgent(6)"
                        resource-id="com.tencent.wework:id/n5i"
                        package="com.tencent.wework" />
                  <node resource-id="com.tencent.wework:id/eyy" />
                  <node resource-id="com.tencent.wework:id/j28" />
                </hierarchy>
                """
            )
            runtime.adb_shell = mock.Mock(return_value="")
            runtime.dump_hierarchy = mock.Mock(return_value=root)

            runtime.move_chat_to_live_tail("LabAgent", root, max_swipes=1)

        runtime.adb_shell.assert_called_once_with(
            "input", "swipe", "520", "1600", "520", "400", "280"
        )

    def test_history_scan_swipes_down_toward_older_rows(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            root = ET.fromstring('<hierarchy><node text="LabAgent(6)" /></hierarchy>')
            runtime.adb_shell = mock.Mock(return_value="")
            runtime.dump_hierarchy = mock.Mock(return_value=root)
            runtime.parse_messages = mock.Mock(return_value=[])

            runtime.scan_older_message_records("LabAgent", [], max_pages=1)

        runtime.adb_shell.assert_called_once_with(
            "input", "swipe", "520", "350", "520", "1450", "500"
        )

    def test_parse_messages_recovers_merged_chat_history_with_all_senders(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy"
                class="android.widget.RelativeLayout"
                package="com.tencent.wework" clickable="true"
                bounds="[0,1200][1080,1800]">
            <node resource-id="com.tencent.wework:id/ja3"
                  class="android.widget.ImageView"
                  package="com.tencent.wework" bounds="[28,1210][133,1315]" />
            <node text="陈苗" class="android.widget.TextView"
                  package="com.tencent.wework" bounds="[164,1205][230,1250]" />
            <node text="＠微信" class="android.widget.TextView"
                  package="com.tencent.wework" bounds="[236,1205][335,1250]" />
            <node text="Chat History for sunnyyty的聊天记录"
                  resource-id="com.tencent.wework:id/jb2"
                  class="android.widget.TextView"
                  package="com.tencent.wework" bounds="[197,1300][810,1400]" />
            <node text="sunnyyty: 找个高光谱和血管成像结合的&#10;sunnyyty: 我想聚焦血管&#10;sunnyyty: 我们现在有血管类器官&#10;sunnyyty: 有血管化肿瘤"
                  resource-id="com.tencent.wework:id/jb1"
                  class="android.widget.TextView"
                  package="com.tencent.wework" bounds="[197,1410][793,1700]" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            record = runtime.parse_messages(ET.fromstring(xml))[0]
            event = runtime.build_event("LabAgent", record)

        self.assertEqual(record["sender"], "陈苗")
        self.assertEqual(record["source_kind"], "merged_chat_history")
        self.assertIn("Chat History for sunnyyty", record["body"])
        self.assertIn("sunnyyty: 我们现在有血管类器官", record["body"])
        self.assertIn("sunnyyty: 有血管化肿瘤", event["text"])
        self.assertEqual(event["msgtype"], "merged_chat_history")

    def test_parse_messages_recovers_native_gongzhonghao_article_card(self) -> None:
        bridge = load_bridge()
        title = "第一次，我们看到了高自由度灵巧手的另一种可能。"
        xml = f"""
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework"
                clickable="true" bounds="[0,272][1080,849]">
            <node resource-id="com.tencent.wework:id/ja3" package="com.tencent.wework"
                  bounds="[28,379][133,484]" />
            <node text="陈苗" class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[164,373][230,418]" />
            <node text="＠微信" class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[236,373][335,418]" />
            <node text="{title}" resource-id="com.tencent.wework:id/mww"
                  class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[202,460][805,586]" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            record = runtime.parse_messages(ET.fromstring(xml))[0]
            event = runtime.build_event("LabAgent", record)

        self.assertEqual(record["direction"], "inbound")
        self.assertEqual(record["sender"], "陈苗")
        self.assertEqual(record["source_kind"], "wechat_article_card")
        self.assertEqual(record["source_title"], title)
        self.assertEqual(record["body"], f"公众号文章卡片\n<title>{title}</title>")
        self.assertEqual(event["msgtype"], "wechat_article_card")
        self.assertEqual(event["source_metadata"]["title"], title)

    def test_parse_messages_materializes_native_inbound_image_event(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework"
                clickable="true" bounds="[0,20][120,190]">
            <node resource-id="com.tencent.wework:id/ja3" package="com.tencent.wework"
                  class="android.widget.ImageView" bounds="[2,24][14,36]" />
            <node text="陈苗" class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[18,24][42,34]" />
            <node text="＠微信" class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[44,24][66,34]" />
            <node resource-id="com.tencent.wework:id/kfb" package="com.tencent.wework"
                  class="android.widget.ImageView" clickable="true" bounds="[18,40][100,170]" />
          </node>
        </node></hierarchy>
        """
        width, height = 120, 200
        rgba = bytearray(b"\xff\xff\xff\xff" * width * height)
        for y in range(40, 170):
            for x in range(18, 100):
                offset = (y * width + x) * 4
                rgba[offset : offset + 4] = bytes((x * 2 % 256, y % 256, (x + y) % 256, 255))
        screenshot = bridge.RawScreenshot(width, height, bytes(rgba))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            record = runtime.parse_messages(
                ET.fromstring(xml), screenshot=screenshot
            )[0]
            image = root / "staging" / "inbound-media" / "source.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(bridge.encode_rgba_png(screenshot))
            record.update(
                {
                    "attachment_path": str(image),
                    "attachment_filename": image.name,
                    "attachment_size_bytes": str(image.stat().st_size),
                    "attachment_sha256": bridge.sha256_file(image),
                    "attachment_width": str(width),
                    "attachment_height": str(height),
                    "attachment_capture_kind": "wecom_android_native_full_view",
                }
            )
            event = runtime.build_event("LabAgent", record)

        self.assertEqual(record["direction"], "inbound")
        self.assertEqual(record["sender"], "陈苗")
        self.assertEqual(record["source_kind"], "image")
        self.assertEqual(record["body"], "[图片]")
        self.assertTrue(record["image_preview_sha256"])
        self.assertTrue(record["image_visual_id"])
        self.assertEqual(event["msgtype"], "image")
        self.assertEqual(event["attachments"][0]["path"], str(image))
        self.assertEqual(
            event["attachments"][0]["capture_kind"],
            "wecom_android_native_full_view",
        )

    def test_visible_image_preview_is_persisted_with_exact_visual_identity(self) -> None:
        bridge = load_bridge()
        width, height = 80, 80
        rgba = bytes((20, 40, 60, 255)) * width * height
        screenshot = bridge.RawScreenshot(width, height, rgba)
        bounds = "[10,12][70,68]"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            record = {
                "fingerprint": "exact-image-preview",
                "direction": "inbound",
                "sender": "陈苗",
                "body": "[图片]",
                "source_kind": bridge.IMAGE_KIND,
                "image_bounds": bounds,
                "image_visual_id": bridge.screenshot_region_visual_id(
                    screenshot, bounds
                ),
            }

            preserved = runtime.persist_visible_image_preview(
                "LabAgent", record, screenshot
            )
            preview = Path(preserved["exact_preview_path"])

            self.assertTrue(preview.is_file())
            self.assertEqual(
                preserved["exact_preview_sha256"], bridge.sha256_file(preview)
            )
            self.assertEqual(preserved["exact_preview_width"], "60")
            self.assertEqual(preserved["exact_preview_height"], "56")

    def test_image_materialization_uses_exact_saved_preview_if_bubble_scrolled_away(self) -> None:
        bridge = load_bridge()
        width, height = 80, 80
        screenshot = bridge.RawScreenshot(
            width,
            height,
            bytes((20, 40, 60, 255)) * width * height,
        )
        bounds = "[10,12][70,68]"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            record = runtime.persist_visible_image_preview(
                "LabAgent",
                {
                    "fingerprint": "exact-image-fallback",
                    "direction": "inbound",
                    "sender": "陈苗",
                    "body": "[图片]",
                    "source_kind": bridge.IMAGE_KIND,
                    "image_bounds": bounds,
                    "image_visual_id": bridge.screenshot_region_visual_id(
                        screenshot, bounds
                    ),
                },
                screenshot,
            )
            with mock.patch.object(
                runtime,
                "find_image_node_for_record",
                side_effect=bridge.BridgeError("image scrolled away"),
            ):
                materialized = runtime.materialize_image_record(
                    "LabAgent", record
                )

            self.assertEqual(
                materialized["attachment_path"], record["exact_preview_path"]
            )
            self.assertEqual(
                materialized["attachment_capture_kind"],
                "wecom_android_exact_visible_image_preview_fallback",
            )

    def test_find_image_node_scans_recent_history_by_visual_identity(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root_path / "state.sqlite"),
                    "staging_dir": str(root_path / "staging"),
                    "inbound_image_search_pages": 2,
                }
            )
            root = ET.fromstring(
                '<hierarchy><node text="LabAgent" '
                'resource-id="com.tencent.wework:id/n5i" '
                'package="com.tencent.wework" /></hierarchy>'
            )
            node = ET.fromstring(
                '<node class="android.widget.ImageView" '
                'package="com.tencent.wework" bounds="[10,20][30,40]" />'
            )
            screenshot = bridge.RawScreenshot(1, 1, b"\x00\x00\x00\xff")
            record = {
                "source_kind": "image",
                "sender": "陈苗",
                "image_bounds": "[164,1552][552,1770]",
                "image_visual_id": "exact-visual-id",
            }
            with mock.patch.object(
                runtime, "open_chat", return_value=root
            ), mock.patch.object(
                runtime, "move_chat_to_live_tail", return_value=root
            ), mock.patch.object(
                runtime, "capture_raw_screenshot", return_value=screenshot
            ), mock.patch.object(
                runtime,
                "image_node_for_record",
                side_effect=[
                    bridge.BridgeError("not in live viewport"),
                    node,
                ],
            ) as locate, mock.patch.object(
                runtime, "adb_shell", return_value=""
            ) as adb_shell, mock.patch.object(
                runtime, "dump_hierarchy", return_value=root
            ):
                found_root, found_screenshot, found_node = (
                    runtime.find_image_node_for_record("LabAgent", record)
                )

        self.assertIs(found_root, root)
        self.assertIs(found_screenshot, screenshot)
        self.assertIs(found_node, node)
        self.assertEqual(locate.call_count, 2)
        self.assertEqual(locate.call_args_list[1].args[2]["image_bounds"], "")
        adb_shell.assert_called_once_with(
            "input", "swipe", "520", "350", "520", "1450", "500"
        )

    def test_parse_messages_recovers_native_inbound_document_event(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework"
                clickable="true" bounds="[0,1049][1080,1402]">
            <node resource-id="com.tencent.wework:id/ja3" package="com.tencent.wework"
                  class="android.widget.ImageView" bounds="[28,1070][133,1175]" />
            <node text="陈苗" class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[164,1049][230,1094]" />
            <node text="＠微信" class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[236,1049][335,1094]" />
            <node text="s44460-026-00087&#10;-3.pdf"
                  resource-id="com.tencent.wework:id/j2k"
                  class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[202,1131][623,1248]" />
            <node text="5.7M" resource-id="com.tencent.wework:id/j2g"
                  class="android.widget.TextView" package="com.tencent.wework"
                  bounds="[202,1259][282,1308]" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            record = runtime.parse_messages(ET.fromstring(xml))[0]
            document = root / "staging" / "s44460-026-00087-3.pdf"
            document.parent.mkdir(parents=True, exist_ok=True)
            document.write_bytes(b"%PDF-1.4\nexact paper")
            record.update(
                {
                    "attachment_path": str(document),
                    "attachment_filename": document.name,
                    "attachment_size_bytes": str(document.stat().st_size),
                    "attachment_sha256": bridge.sha256_file(document),
                    "attachment_capture_kind": "wecom_android_native_document_card",
                }
            )
            event = runtime.build_event("LabAgent", record)

        self.assertEqual(record["direction"], "inbound")
        self.assertEqual(record["sender"], "陈苗")
        self.assertEqual(record["source_kind"], "document")
        self.assertEqual(record["document_filename"], "s44460-026-00087-3.pdf")
        self.assertEqual(record["document_size_text"], "5.7M")
        self.assertEqual(record["body"], "[文件] s44460-026-00087-3.pdf (5.7M)")
        self.assertEqual(event["msgtype"], "document")
        self.assertEqual(event["attachments"][0]["path"], str(document))
        self.assertEqual(
            event["attachments"][0]["capture_kind"],
            "wecom_android_native_document_card",
        )

    def test_native_document_display_size_accepts_rounded_card_value(self) -> None:
        bridge = load_bridge()

        self.assertTrue(bridge.display_size_matches(5_948_623, "5.7M"))
        self.assertFalse(bridge.display_size_matches(2_000_000, "5.7M"))

    def test_article_card_fallback_still_routes_to_research_worker(self) -> None:
        ingest = load_ingest()

        route = ingest.fallback_route(
            {"msgtype": "wechat_article_card", "attachments": []},
            "公众号文章卡片\n<title>Exact title</title>",
        )

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["route_kind"], "research_or_summary")

    def test_bounded_history_scan_recovers_hidden_card_once(self) -> None:
        bridge = load_bridge()
        current = {
            "fingerprint": "current",
            "direction": "outbound",
            "sender": "",
            "body": "long result",
        }
        article = {
            "fingerprint": "article",
            "direction": "inbound",
            "sender": "member",
            "body": "公众号文章卡片",
        }
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            chat_root = ET.fromstring(
                '<hierarchy><node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i" '
                'package="com.tencent.wework" /></hierarchy>'
            )
            with mock.patch.object(runtime, "adb_shell"), mock.patch.object(
                runtime, "dump_hierarchy", side_effect=[chat_root, chat_root, chat_root]
            ), mock.patch.object(
                runtime, "parse_messages", side_effect=[[article], [article], []]
            ):
                records = runtime.scan_older_message_records(
                    "LabAgent",
                    [current],
                    max_pages=3,
                )

        self.assertEqual(records, [article])

    def test_history_scan_merges_long_bubble_when_sender_label_enters_view(self) -> None:
        bridge = load_bridge()
        body = "让芯片从减法制造转向可编程生长。" * 12
        unlabeled = {
            "fingerprint": "long-unlabeled",
            "direction": "outbound",
            "sender": "",
            "body": body,
            "quote_text": "",
            "source_kind": "text",
        }
        labeled = {
            "fingerprint": "long-labeled",
            "direction": "inbound",
            "sender": "陈苗",
            "body": body,
            "quote_text": "",
            "source_kind": "text",
        }
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            chat_root = ET.fromstring(
                '<hierarchy><node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i" '
                'package="com.tencent.wework" /></hierarchy>'
            )
            with mock.patch.object(runtime, "adb_shell"), mock.patch.object(
                runtime, "dump_hierarchy", side_effect=[chat_root, chat_root]
            ), mock.patch.object(
                runtime, "parse_messages", side_effect=[[unlabeled], [labeled]]
            ), mock.patch.object(runtime, "capture_raw_screenshot", side_effect=RuntimeError):
                records = runtime.scan_older_message_records(
                    "LabAgent", [], max_pages=2
                )

        self.assertEqual(records, [labeled])

    def test_parse_messages_keeps_adjacent_authors_on_their_own_rows(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="megamonster" class="android.widget.TextView" bounds="[90,100][300,130]" package="com.tencent.wework" />
            <node text="思想上还不够高级" resource-id="com.tencent.wework:id/j1l"
                  class="android.widget.TextView" bounds="[90,140][850,200]" package="com.tencent.wework" />
          </node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="sunnyyty" class="android.widget.TextView" bounds="[90,220][300,250]" package="com.tencent.wework" />
            <node text="这个需要改进的地方是字太多" resource-id="com.tencent.wework:id/j1l"
                  class="android.widget.TextView" bounds="[90,260][850,320]" package="com.tencent.wework" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            records = runtime.parse_messages(ET.fromstring(xml))

        self.assertEqual(
            [(row["sender"], row["body"]) for row in records],
            [
                ("megamonster", "思想上还不够高级"),
                ("sunnyyty", "这个需要改进的地方是字太多"),
            ],
        )
        self.assertTrue(all(row["sender_identity_confidence"] == "visible_row_label" for row in records))

    def test_ambiguous_row_stays_unattributed_and_never_mentions_a_guess(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node resource-id="com.tencent.wework:id/ja3" bounds="[20,100][70,150]" package="com.tencent.wework" />
            <node text="person-a" class="android.widget.TextView" bounds="[90,100][220,125]" package="com.tencent.wework" />
            <node text="person-b" class="android.widget.TextView" bounds="[240,100][370,125]" package="com.tencent.wework" />
            <node text="需要进一步分析" resource-id="com.tencent.wework:id/j1l"
                  class="android.widget.TextView" bounds="[90,140][850,200]" package="com.tencent.wework" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            record = runtime.parse_messages(ET.fromstring(xml))[0]
            event = runtime.build_event("LabAgent", record)

        self.assertEqual(record["direction"], "inbound")
        self.assertEqual(record["sender"], "")
        self.assertEqual(record["sender_identity_confidence"], "unattributed_row")
        self.assertEqual(event["sender_mention"], "")
        self.assertNotEqual(event["sender_userid"], "android-member:unknown")

    def test_parse_messages_preserves_quote_preview_in_agent_event(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="megamonster" package="com.tencent.wework" />
            <node text="＠微信" package="com.tencent.wework" />
            <node text="Prof Ma" resource-id="com.tencent.wework:id/quote_author"
                  class="android.widget.TextView" package="com.tencent.wework" />
            <node text="脑类器官排斥血管类器官细胞浸润，如何解决？"
                  resource-id="com.tencent.wework:id/quote_content"
                  class="android.widget.TextView" package="com.tencent.wework" />
            <node text="解释清楚这段内容是什么意思。"
                  resource-id="com.tencent.wework:id/j1l"
                  class="android.widget.TextView" package="com.tencent.wework" />
            <node text="07:15" resource-id="com.tencent.wework:id/time"
                  class="android.widget.TextView" package="com.tencent.wework" />
            <node text="已读" resource-id="com.tencent.wework:id/read"
                  class="android.widget.TextView" package="com.tencent.wework" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            record = runtime.parse_messages(ET.fromstring(xml))[0]
            event = runtime.build_event("LabAgent", record)

        self.assertEqual(
            record["quote_text"],
            "Prof Ma\n脑类器官排斥血管类器官细胞浸润，如何解决？",
        )
        self.assertEqual(event["quote_text"], record["quote_text"])

    def test_parse_messages_recovers_collapsed_quote_from_content_description(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="陈苗" package="com.tencent.wework" />
            <node resource-id="com.tencent.wework:id/reply_preview"
                  content-desc="引用：请比较事件相机和高光谱的优势"
                  class="android.view.View" package="com.tencent.wework" />
            <node text="请提出更直接的生物学测量方法"
                  resource-id="com.tencent.wework:id/j1l"
                  class="android.widget.TextView" package="com.tencent.wework" />
          </node>
        </node></hierarchy>
        """
        runtime = bridge.AndroidBridge(
            {
                "serial": "test",
                "target_groups": ["LabAgent"],
                "state_db": str(Path(tempfile.mkdtemp()) / "state.sqlite"),
            }
        )
        record = runtime.parse_messages(ET.fromstring(xml))[0]

        self.assertIn("请比较事件相机和高光谱的优势", record["quote_text"])
        self.assertEqual(record["body"], "请提出更直接的生物学测量方法")
        event = runtime.build_event("LabAgent", record)
        self.assertIn("请比较事件相机和高光谱的优势", event["quote_text"])

    def test_native_mention_contract_is_exact_and_non_broadcast(self) -> None:
        bridge = load_bridge()
        token = "@\ufff31688857361779939\ufff0"

        self.assertEqual(bridge.validate_mentions(["sunnyyty", "sunnyyty"]), ["sunnyyty"])
        self.assertEqual(bridge.mention_token_count(token + " 请查论文"), 1)
        self.assertEqual(bridge.mention_token_count("\ufff31688857361779939\ufff0 请查论文"), 1)
        self.assertTrue(
            bridge.composer_matches_message(token + " 请查论文", "请查论文", mention_count=1)
        )
        self.assertFalse(
            bridge.composer_matches_message(token + " 其他内容", "请查论文", mention_count=1)
        )
        placeholder = ET.fromstring('<node text="发消息或按住..." />')
        self.assertEqual(bridge.composer_text(placeholder), "")
        with self.assertRaises(bridge.BridgeError):
            bridge.validate_mentions(["所有人"])

    def test_resilient_text_send_drops_secondary_mention_before_primary(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            with mock.patch.object(
                runtime,
                "send_text_locked",
                side_effect=[
                    bridge.BridgeError("expected one exact WeCom member named '陈苗', found 2"),
                    {
                        "ok": True,
                        "sent_messages": ["正在处理"],
                        "sent_files": [],
                        "mentioned_users": ["megamonster@微信"],
                    },
                ],
            ) as sender:
                result = runtime.send_text_resilient_locked(
                    "LabAgent",
                    "正在处理",
                    task_id="task-1",
                    mentions=["megamonster@微信", "陈苗"],
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mentioned_users"], ["megamonster@微信"])
        self.assertEqual(sender.call_args_list[0].kwargs["mentions"], ["megamonster@微信", "陈苗"])
        self.assertEqual(sender.call_args_list[1].kwargs["mentions"], ["megamonster@微信"])

    def test_resilient_text_send_delivers_plain_text_when_primary_mention_breaks(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            with mock.patch.object(
                runtime,
                "send_text_locked",
                side_effect=[
                    bridge.BridgeError("text and native mentions were not reproduced exactly in the WeCom composer"),
                    {
                        "ok": True,
                        "sent_messages": ["完整结果已完成"],
                        "sent_files": [],
                        "mentioned_users": [],
                    },
                ],
            ) as sender:
                result = runtime.send_text_resilient_locked(
                    "LabAgent",
                    "完整结果已完成",
                    task_id="task-2",
                    mentions=["megamonster@微信"],
                )
                requested_hash = bridge.text_component_value_hash(
                    "完整结果已完成", ["megamonster@微信"]
                )
                record = runtime.component_record(
                    runtime.component_key("task-2", "LabAgent", "text", requested_hash)
                )

        self.assertTrue(result["ok"])
        self.assertEqual(sender.call_args_list[1].kwargs["mentions"], [])
        self.assertEqual(record["status"], "sent")
        self.assertTrue(record["details"]["mention_fallback"])

    def test_exact_mention_rows_preserve_visible_case_and_spelling(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="sunnyyty@微信" resource-id="com.tencent.wework:id/ic1" package="com.tencent.wework" />
              <node text="Sunnyyty" resource-id="com.tencent.wework:id/ic1" package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )

            matches = runtime.exact_mention_rows(root, "sunnyyty")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].attrib["text"], "sunnyyty@微信")

    def test_ingest_preserves_sender_name_as_reply_mention(self) -> None:
        ingest = load_ingest()
        event = {
            "chat_type": "group",
            "sender_display": "sunnyyty",
            "sender_mention": "sunnyyty@微信",
        }

        self.assertEqual(ingest.event_reply_mentions(event), ["sunnyyty@微信"])
        self.assertEqual(
            ingest.event_reply_mentions({"chat_type": "single", "sender_display": "sunnyyty"}),
            [],
        )

    def test_mobile_ingress_sends_prompt_ack_with_source_mention(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            records = [
                {"fingerprint": "old", "direction": "outbound", "sender": "", "body": "old"},
                {
                    "fingerprint": "new",
                    "direction": "inbound",
                    "sender": "sunnyyty",
                    "mention_name": "sunnyyty@微信",
                    "body": "请帮我查论文",
                },
            ]
            with mock.patch.object(runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")), mock.patch.object(
                runtime, "parse_messages", return_value=records
            ), mock.patch.object(runtime, "load_snapshot", return_value=["old"]), mock.patch.object(
                runtime, "save_snapshot"
            ) as save_snapshot, mock.patch.object(
                runtime,
                "invoke_ingest",
                return_value={
                    "queued": True,
                    "ack": "我会查证后回复。",
                    "reply_mentions": ["sunnyyty@微信", "陈苗"],
                },
            ), mock.patch.object(
                runtime,
                "send_text_locked",
                return_value={"sent_messages": ["我会查证后回复。"]},
            ) as send_text:
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["replied"], 1)
        save_snapshot.assert_called_once_with("LabAgent", ["old", "new"])
        send_text.assert_called_once()
        self.assertEqual(send_text.call_args.kwargs["mentions"], ["sunnyyty@微信", "陈苗"])

    def test_snapshot_materializes_image_before_wecom_ingest(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            runtime.lock_path = root / "bridge.lock"
            old = {
                "fingerprint": "old",
                "direction": "outbound",
                "sender": "",
                "body": "old",
            }
            image_record = {
                "fingerprint": "new-image",
                "direction": "inbound",
                "sender": "陈苗",
                "mention_name": "陈苗@微信",
                "sender_identity_confidence": "visible_row_label",
                "body": "[图片]",
                "source_kind": "image",
                "image_bounds": "[18,40][100,170]",
                "image_visual_id": "visual-image-id",
            }
            runtime.save_snapshot("LabAgent", ["old"])
            runtime.mark_observed_message("LabAgent", old, "seeded")
            image = root / "staging" / "inbound-media" / "source.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"\x89PNG\r\n\x1a\nsource")
            materialized = {
                **image_record,
                "attachment_path": str(image),
                "attachment_filename": image.name,
                "attachment_size_bytes": str(image.stat().st_size),
                "attachment_sha256": bridge.sha256_file(image),
                "attachment_capture_kind": "wecom_android_native_full_view",
            }
            captured_events = []

            def ingest(event):
                captured_events.append(event)
                return {"queued": True, "ack": ""}

            with mock.patch.object(
                runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(
                runtime, "parse_messages", return_value=[old, image_record]
            ), mock.patch.object(
                runtime,
                "capture_raw_screenshot",
                return_value=bridge.RawScreenshot(1, 1, b"\x00\x00\x00\xff"),
            ), mock.patch.object(
                runtime, "materialize_image_record", return_value=materialized
            ) as materialize, mock.patch.object(
                runtime, "invoke_ingest", side_effect=ingest
            ):
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["processed"], 1)
        materialize.assert_called_once()
        self.assertEqual(captured_events[0]["msgtype"], "image")
        self.assertEqual(captured_events[0]["attachments"][0]["path"], str(image))

    def test_snapshot_materializes_document_before_wecom_ingest(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "staging_dir": str(root / "staging"),
                }
            )
            runtime.lock_path = root / "bridge.lock"
            old = {
                "fingerprint": "old",
                "direction": "outbound",
                "sender": "",
                "body": "old",
            }
            document_record = {
                "fingerprint": "new-document",
                "direction": "inbound",
                "sender": "陈苗",
                "mention_name": "陈苗@微信",
                "sender_identity_confidence": "visible_row_label",
                "body": "[文件] exact-paper.pdf (5.7M)",
                "source_kind": "document",
                "document_filename": "exact-paper.pdf",
                "document_size_text": "5.7M",
                "document_bounds": "[202,1131][623,1248]",
            }
            runtime.save_snapshot("LabAgent", ["old"])
            runtime.mark_observed_message("LabAgent", old, "seeded")
            document = root / "staging" / "inbound-media" / "exact-paper.pdf"
            document.parent.mkdir(parents=True)
            document.write_bytes(b"%PDF-1.4\nsource")
            materialized = {
                **document_record,
                "attachment_path": str(document),
                "attachment_filename": document.name,
                "attachment_size_bytes": str(document.stat().st_size),
                "attachment_sha256": bridge.sha256_file(document),
                "attachment_capture_kind": "wecom_android_native_document_card",
            }
            captured_events = []

            def ingest(event):
                captured_events.append(event)
                return {"queued": True, "ack": ""}

            with mock.patch.object(
                runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(
                runtime, "parse_messages", return_value=[old, document_record]
            ), mock.patch.object(
                runtime,
                "materialize_document_record",
                return_value=materialized,
            ) as materialize, mock.patch.object(
                runtime, "invoke_ingest", side_effect=ingest
            ):
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["processed"], 1)
        materialize.assert_called_once()
        self.assertEqual(captured_events[0]["msgtype"], "document")
        self.assertEqual(captured_events[0]["attachments"][0]["path"], str(document))

    def test_snapshot_releases_gui_lock_while_ingest_runs(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            runtime.save_snapshot("LabAgent", ["old"])
            runtime.mark_observed_message(
                "LabAgent",
                {"fingerprint": "old", "direction": "outbound", "body": "old"},
                "seeded",
            )
            lock_active = False

            @bridge.contextmanager
            def tracked_serialized(*, timeout_seconds=None):
                nonlocal lock_active
                self.assertFalse(lock_active)
                lock_active = True
                try:
                    yield
                finally:
                    lock_active = False

            def ingest_without_gui_lock(_event):
                self.assertFalse(lock_active)
                return {"queued": True, "ack": "收到。"}

            records = [
                {"fingerprint": "old", "direction": "outbound", "sender": "", "body": "old"},
                {
                    "fingerprint": "new",
                    "direction": "inbound",
                    "sender": "sunnyyty",
                    "mention_name": "sunnyyty@微信",
                    "body": "请查这个结构。",
                },
            ]
            with mock.patch.object(runtime, "serialized", side_effect=tracked_serialized), mock.patch.object(
                runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(runtime, "parse_messages", return_value=records), mock.patch.object(
                runtime, "invoke_ingest", side_effect=ingest_without_gui_lock
            ), mock.patch.object(
                runtime, "send_text_resilient_locked", return_value={"sent_messages": ["收到。"]}
            ):
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["replied"], 1)

    def test_read_only_snapshot_does_not_consume_pending_inbound(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "history_db": str(Path(tmp) / "history.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            old = {"fingerprint": "old", "direction": "outbound", "sender": "", "body": "old"}
            new = {
                "fingerprint": "new",
                "direction": "inbound",
                "sender": "sunnyyty",
                "mention_name": "sunnyyty@微信",
                "body": "请按 CNS 顶刊风格调整图。",
            }
            runtime.save_snapshot("LabAgent", ["old"])
            runtime.mark_observed_message("LabAgent", old, "seeded")
            with mock.patch.object(runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")), mock.patch.object(
                runtime, "parse_messages", return_value=[old, new]
            ), mock.patch.object(
                runtime, "invoke_ingest", return_value={"queued": True, "ack": "会按这个标准调整。"}
            ) as ingest, mock.patch.object(
                runtime, "send_text_locked", return_value={"sent_messages": ["会按这个标准调整。"]}
            ):
                inspected = runtime.snapshot("LabAgent", enqueue=False)
                processed = runtime.snapshot("LabAgent", enqueue=True)

        self.assertEqual(inspected["pending"], 1)
        self.assertEqual(inspected["processed"], 0)
        self.assertEqual(processed["processed"], 1)
        ingest.assert_called_once()

    def test_viewport_change_without_overlap_ingests_unseen_message(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "history_db": str(Path(tmp) / "history.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            runtime.save_snapshot("LabAgent", ["old-viewport"])
            runtime.seed_observed_fingerprints("LabAgent", ["old-viewport"])
            new = {
                "fingerprint": "new-viewport",
                "direction": "inbound",
                "sender": "sunnyyty",
                "mention_name": "sunnyyty@微信",
                "body": "不要漏掉和上一条重叠的指导。",
            }
            with mock.patch.object(runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")), mock.patch.object(
                runtime, "parse_messages", return_value=[new]
            ), mock.patch.object(
                runtime, "invoke_ingest", return_value={"queued": True, "ack": "收到。"}
            ) as ingest, mock.patch.object(
                runtime, "send_text_locked", return_value={"sent_messages": ["收到。"]}
            ):
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertTrue(result["viewport_changed_without_overlap"])
        self.assertEqual(result["processed"], 1)
        ingest.assert_called_once()

    def test_pending_message_remains_actionable_after_it_scrolls_offscreen(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "history_db": str(Path(tmp) / "history.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            pending = {
                "fingerprint": "pending-sunnyyty",
                "direction": "inbound",
                "sender": "sunnyyty",
                "mention_name": "sunnyyty@微信",
                "body": "要学习 CNS 顶刊风格绘图",
                "quote_text": "",
            }
            latest = {
                "fingerprint": "latest-outbound",
                "direction": "outbound",
                "sender": "",
                "body": "newer result",
            }
            runtime.save_snapshot("LabAgent", [pending["fingerprint"]])
            runtime.mark_observed_message("LabAgent", pending, "pending")
            with mock.patch.object(runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")), mock.patch.object(
                runtime, "parse_messages", return_value=[latest]
            ), mock.patch.object(
                runtime,
                "invoke_ingest",
                return_value={"queued": True, "ack": "收到。"},
            ) as ingest, mock.patch.object(
                runtime, "send_text_locked", return_value={"sent_messages": ["收到。"]}
            ):
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(ingest.call_args.args[0]["text"], pending["body"])

    def test_failed_image_capture_is_backed_off_without_losing_the_pending_row(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            record = {
                "fingerprint": "image-that-scrolled-away",
                "direction": "inbound",
                "sender": "sunnyyty",
                "body": "[图片]",
                "source_kind": bridge.IMAGE_KIND,
            }
            runtime.mark_observed_message("LabAgent", record, "pending")
            runtime.defer_observed_message(
                "LabAgent", record["fingerprint"], "exact bubble not visible"
            )

            self.assertEqual(runtime.pending_observed_records("LabAgent"), [])
            with sqlite3.connect(runtime.state_db) as conn:
                conn.execute(
                    "UPDATE observed_messages SET retry_after = '' "
                    "WHERE chat = 'LabAgent' AND fingerprint = ?",
                    (record["fingerprint"],),
                )
            self.assertEqual(
                runtime.pending_observed_records("LabAgent")[0]["fingerprint"],
                record["fingerprint"],
            )

    def test_legacy_pending_fingerprint_recovers_unprocessed_history_payload(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            history = Path(tmp) / "history.sqlite"
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "account_id": "external-gui",
                    "target_groups": ["LabAgent"],
                    "state_db": str(state),
                    "history_db": str(history),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            sender = "sunnyyty"
            body = "@陈喵瞄秒妙 要学习CNS顶刊风格绘图"
            fingerprint = bridge.short_hash(f"inbound\0{sender}\0{body}\0", 64)
            canonical_chat = (
                "wecom:external-gui:group:"
                + bridge.short_hash("gui:LabAgent", 12)
            )
            with sqlite3.connect(state) as conn:
                conn.execute(
                    "INSERT INTO observed_messages("
                    "chat,fingerprint,direction,status,record_json,updated_at"
                    ") VALUES (?,?,?,?,?,?)",
                    ("LabAgent", fingerprint, "inbound", "pending", "{}", "2026-07-22T00:00:00"),
                )
            with sqlite3.connect(history) as conn:
                conn.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, message_id TEXT, chat TEXT, "
                    "direction TEXT, sender TEXT, sender_display TEXT, body TEXT, create_time INTEGER, "
                    "created_at TEXT, processed_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO messages(message_id,chat,direction,sender,sender_display,body,"
                    "create_time,created_at,processed_at) VALUES (?,?,?,?,?,?,?,?,NULL)",
                    ("android:stable", canonical_chat, "inbound", "member", sender, body, 0, "2026-07-22T00:00:00"),
                )

            recovered = runtime.pending_observed_records("LabAgent")

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["body"], body)
        self.assertEqual(recovered[0]["sender"], sender)

    def test_android_event_id_is_stable_for_pending_ingress_retry(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            record = {
                "fingerprint": "exact-visible-message",
                "direction": "inbound",
                "sender": "sunnyyty",
                "body": "请调整图。",
            }

            first = runtime.build_event("LabAgent", record)
            second = runtime.build_event("LabAgent", record)

        self.assertEqual(first["message_id"], second["message_id"])

    def test_composer_waits_for_exact_accessibility_refresh(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            stale = ET.fromstring(
                '<hierarchy><node text="partial" resource-id="com.tencent.wework:id/j28" '
                'package="com.tencent.wework" /></hierarchy>'
            )
            exact = ET.fromstring(
                '<hierarchy><node text="完整消息" resource-id="com.tencent.wework:id/j28" '
                'package="com.tencent.wework" /></hierarchy>'
            )
            with mock.patch.object(runtime, "ensure_chat_identity", side_effect=[stale, exact]), mock.patch.object(
                bridge.time, "sleep"
            ):
                result = runtime.wait_for_composer_message("LabAgent", "完整消息", timeout=1)

        self.assertIs(result, exact)

    def test_config_is_private_and_redacts_token(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "android.local.json"
            result = bridge.initialize_config(
                path,
                ["LabAgent", "AgentTest"],
                serial="device-1",
                force=True,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertNotIn("local_api_token", result)
            self.assertTrue(payload["local_api_token"])
            self.assertEqual(payload["reconcile_seconds"], 20.0)
            self.assertEqual(payload["history_scan_seconds"], 180.0)
            self.assertEqual(payload["history_scan_pages"], 3)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_poll_cycle_reconciles_all_chats_without_unread_badges(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent", "AgentTest"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                    "reconcile_seconds": 20,
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            runtime._next_reconcile_at = 0.0
            with mock.patch.object(runtime, "load_snapshot", return_value=["old"]), mock.patch.object(
                runtime, "open_chat_list", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(runtime, "unread_target_chats", return_value=[]), mock.patch.object(
                runtime,
                "snapshot",
                side_effect=lambda chat, enqueue, history_pages=0: {
                    "ok": True,
                    "chat": chat,
                    "processed": 0,
                },
            ) as snapshot:
                result = runtime.poll_cycle()

        self.assertTrue(result["ok"])
        self.assertTrue(result["reconciliation"])
        self.assertEqual(result["unread_chats"], [])
        self.assertEqual(result["due_chats"], ["LabAgent", "AgentTest"])
        self.assertEqual(
            [call.args[0] for call in snapshot.call_args_list],
            ["LabAgent", "AgentTest"],
        )

    def test_poll_cycle_uses_unread_only_between_reconciliations(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent", "AgentTest"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            runtime._next_reconcile_at = time.monotonic() + 300
            runtime._next_history_scan_at = time.monotonic() + 300
            with mock.patch.object(runtime, "load_snapshot", return_value=["old"]), mock.patch.object(
                runtime, "open_chat_list", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(
                runtime, "unread_target_chats", return_value=["AgentTest"]
            ), mock.patch.object(
                runtime,
                "snapshot",
                return_value={"ok": True, "chat": "AgentTest", "processed": 1},
            ) as snapshot:
                result = runtime.poll_cycle()

        self.assertTrue(result["ok"])
        self.assertFalse(result["reconciliation"])
        self.assertEqual(result["due_chats"], ["AgentTest"])
        snapshot.assert_called_once_with("AgentTest", enqueue=True, history_pages=0)

    def test_one_chat_failure_does_not_block_other_reconciliation(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent", "AgentTest"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            with mock.patch.object(runtime, "load_snapshot", return_value=None), mock.patch.object(
                runtime, "open_chat_list", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(
                runtime,
                "snapshot",
                side_effect=[RuntimeError("first chat unavailable"), {"ok": True, "processed": 1}],
            ) as snapshot:
                result = runtime.poll_cycle()

        self.assertFalse(result["ok"])
        self.assertEqual(snapshot.call_count, 2)
        self.assertIn("first chat unavailable", result["results"][0]["error"])
        self.assertEqual(result["processed"], 1)

    def test_worker_prefers_healthy_mobile_send_endpoint(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "preferred_for_gui_send": True,
                        "local_api_port": 19581,
                        "local_api_token": "private-token",
                    }
                ),
                encoding="utf-8",
            )
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {"ok": True, "device_authorized": True}
            ).encode("utf-8")
            with mock.patch.object(worker, "ROOT", root), mock.patch.object(
                worker.urllib.request, "urlopen", return_value=response
            ):
                endpoint = worker.ready_wecom_android_transport()

        self.assertEqual(endpoint, ("http://127.0.0.1:19581", "private-token"))

    def test_worker_mentions_exact_group_sender_only_on_android(self) -> None:
        worker = load_worker()
        task = {
            "source": {
                "wecom_chat_type": "group",
                "sender_display": "sunnyyty",
                "reply_mentions": ["sunnyyty"],
                "local_type": "text",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"local_api_port": 19581}), encoding="utf-8")
            with mock.patch.object(worker, "ROOT", root):
                android = worker.wecom_native_reply_mentions(task, "http://127.0.0.1:19581")
                desktop = worker.wecom_native_reply_mentions(task, "http://127.0.0.1:19580")

        self.assertEqual(android, ["sunnyyty"])
        self.assertEqual(desktop, [])

    def test_worker_delivery_payload_carries_native_reply_mention(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-mention-1",
            "chat": "wecom:test:group:one",
            "source": {
                "transport": "wecom",
                "wecom_transport_channel": "wecom_android",
                "chat": "wecom:test:group:one",
                "wecom_chat_id": "gui:LabAgent",
                "wecom_chat_type": "group",
                "sender_display": "sunnyyty",
                "reply_mentions": ["sunnyyty"],
                "local_type": "text",
            },
        }
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "ok": True,
                "sent_messages": ["完成。"],
                "sent_files": [],
                "mentioned_users": ["sunnyyty"],
                "errors": [],
            }
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"local_api_port": 19581}), encoding="utf-8")
            with mock.patch.object(worker, "ROOT", root), mock.patch.object(
                worker, "wecom_transport_settings", return_value=("http://127.0.0.1:19581", "token")
            ), mock.patch.object(worker.urllib.request, "urlopen", return_value=response) as urlopen:
                worker.send_result_once_wecom(
                    {"message": "完成。", "confirmation": "", "files": []},
                    "wecom:test:group:one",
                    task,
                )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["chat_id"], "gui:LabAgent")
        self.assertEqual(payload["mentions"], ["sunnyyty"])
        self.assertEqual(task["wecom_delivery"]["mentioned_users"], ["sunnyyty"])

    def test_setup_prevents_host_automount_password_dialog(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_setup.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("org.gnome.desktop.media-handling automount false", source)
        self.assertIn("org.gnome.desktop.media-handling automount-open false", source)

        bridge_source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('"accelerometer_rotation", "0"', bridge_source)
        self.assertIn('"user_rotation", "0"', bridge_source)


if __name__ == "__main__":
    unittest.main()
