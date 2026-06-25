from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_routines.py"


def load_routines():
    spec = importlib.util.spec_from_file_location("wechat_routines_for_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatRoutineTests(unittest.TestCase):
    def test_route_kind_selects_generated_video_routine(self) -> None:
        routines = load_routines()
        routine_id = routines.routine_id_for_route(
            {"route_kind": "generate_video", "project": "lalachan"},
            "write a RaraXia story and generate video",
        )

        self.assertEqual(routine_id, "generated_video")

    def test_route_kind_selects_story_script_routine(self) -> None:
        routines = load_routines()
        routine_id = routines.routine_id_for_route(
            {"route_kind": "story_or_script", "project": "lalachan"},
            "write a RaraXia and AyaChan story",
        )

        self.assertEqual(routine_id, "story_script_generation")

    def test_text_fallback_selects_story_before_visual_routines(self) -> None:
        routines = load_routines()
        routine_id = routines.routine_id_for_route({}, "generate a story about RaraXia and AyaChan")

        self.assertEqual(routine_id, "story_script_generation")

    def test_text_fallback_selects_labcanvas_cad_pcb(self) -> None:
        routines = load_routines()
        routine_id = routines.routine_id_for_route({}, "render this PCB in Blender and export Gerbers")

        self.assertEqual(routine_id, "labcanvas_cad_pcb")

    def test_contract_contains_stages_rules_and_artifact_policy(self) -> None:
        routines = load_routines()
        contract = routines.build_routine_contract(
            {"route_kind": "generate_image", "project": "labcanvas"},
            "make an editable figure grid",
            task_id="task-1",
            chat="懒人科研",
            source={"local_id": 12},
        )

        self.assertEqual(contract["id"], "editable_figure_image")
        self.assertTrue(contract["stages"])
        self.assertIn("artifact_delivery_gate", contract["required_gates"])
        self.assertIn("atomic", " ".join(contract["rules"]))
        self.assertTrue(contract["autonomy_contract"]["autonomous_completion_required"])
        self.assertEqual(contract["autonomy_contract"]["execution_center"], "wechat_task_worker.run_task_orchestrator")
        self.assertIn("WeChat is only the message box", " ".join(contract["autonomy_contract"]["cheat_sheet"]))

    def test_file_download_routine_requires_verified_artifact_delivery(self) -> None:
        routines = load_routines()
        contract = routines.build_routine_contract(
            {"route_kind": "file_download_or_save"},
            "send me the generated video",
            task_id="task-video",
            chat="🍓我的设备",
        )
        stage_ids = [stage["id"] for stage in contract["stages"]]

        self.assertEqual(contract["id"], "file_download_save")
        self.assertIn("artifact_delivery_gate", contract["required_gates"])
        self.assertIn("artifact_delivery_gate", stage_ids)
        self.assertIn("file-picker click", " ".join(contract["rules"]))
        self.assertIn("verified", contract["artifact_policy"])

    def test_file_intake_routine_is_lightweight_receipt(self) -> None:
        routines = load_routines()
        contract = routines.build_routine_contract(
            {"route_kind": "file_intake"},
            "bare PDF upload",
            task_id="task-file",
            chat="🍓我的设备",
        )
        stage_ids = [stage["id"] for stage in contract["stages"]]

        self.assertEqual(contract["id"], "file_intake")
        self.assertEqual(contract["default_effort"], "low")
        self.assertIn("metadata_receipt", stage_ids)
        self.assertIn("do not resend the uploaded file", contract["artifact_policy"])
        self.assertIn("Do not deep-read", " ".join(contract["rules"]))

    def test_video_publish_routine_requires_terminal_publish_verification(self) -> None:
        routines = load_routines()
        contract = routines.build_routine_contract(
            {"route_kind": "publish_video", "public_publish_allowed": True},
            "publish this exact video to sph youtube instagram",
            task_id="task-publish",
            chat="🍓我的设备",
        )
        stage_ids = [stage["id"] for stage in contract["stages"]]

        self.assertEqual(contract["id"], "video_publish_existing")
        self.assertIn("exact_video_resolution", contract["required_gates"])
        self.assertIn("public_publish_verified", contract["required_gates"])
        self.assertIn("public_publish_verified", stage_ids)
        self.assertIn("Never call queued/submitted/running jobs published", " ".join(contract["rules"]))

    def test_write_routine_contract_creates_json_and_markdown(self) -> None:
        routines = load_routines()
        task = {
            "id": "task-2",
            "chat": "懒人科研",
            "request": "summarize this paper",
            "route_decision": {"route_kind": "research_or_summary"},
            "source": {"local_id": 5},
        }

        with tempfile.TemporaryDirectory() as tmp:
            result = routines.write_routine_contract(task, Path(tmp))
            payload = json.loads(Path(result["json"]).read_text(encoding="utf-8"))
            markdown = Path(result["markdown"]).read_text(encoding="utf-8")
            cheat_sheet = Path(result["cheat_sheet"]).read_text(encoding="utf-8")

        self.assertEqual(payload["id"], "research_summary")
        self.assertIn("autonomy_contract", payload)
        self.assertIn("# WeChat Routine Contract", markdown)
        self.assertIn("research_summary", markdown)
        self.assertIn("mp.weixin", markdown)
        self.assertIn("Markdown/PDF", markdown)
        self.assertIn("# Agent Routine Cheat Sheet", cheat_sheet)
        self.assertIn("resume_exact_chat_worker_session", cheat_sheet)
        self.assertEqual(task["routine"]["id"], "research_summary")

    def test_routine_prompt_context_includes_autonomy_contract(self) -> None:
        routines = load_routines()
        task = {
            "id": "task-3",
            "chat": "懒人科研",
            "request": "Current coalesced request:\nmake a video and send it back",
            "route_decision": {"route_kind": "generate_video"},
        }

        context = routines.routine_prompt_context(task)

        self.assertIn("Autonomy rule", context)
        self.assertIn("autonomy_contract", context)
        self.assertIn("resume_exact_chat_worker_session", context)


if __name__ == "__main__":
    unittest.main()
