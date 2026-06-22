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

        self.assertEqual(payload["id"], "research_summary")
        self.assertIn("# WeChat Routine Contract", markdown)
        self.assertIn("research_summary", markdown)
        self.assertEqual(task["routine"]["id"], "research_summary")


if __name__ == "__main__":
    unittest.main()
