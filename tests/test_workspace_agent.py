import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agenticapp.workspace_agent import (
    AgentTaskStore,
    build_agent_prompt,
    cancel_agent_task,
    capability_catalog,
    create_agent_task,
    run_aginti_turn,
    run_agent_task,
    run_codex_turn,
    select_agent_policy,
    selected_packaged_knowledge,
)
from agenticapp.artifacts import artifact_kind_for_path, content_type_for_path
from agenticapp.backends import load_model_policy


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceAgentTests(unittest.TestCase):
    def test_shared_model_policy_uses_low_chat_medium_task_and_sol_fallback(self):
        policy = load_model_policy(ROOT / "configs" / "model-policy.json")
        self.assertEqual(policy["chat"], {"model": "auto-code-review", "reasoning_effort": "low"})
        self.assertEqual(policy["task"], {"model": "auto-code-review", "reasoning_effort": "medium"})
        self.assertEqual(policy["fallback"]["chat"]["model"], "gpt-5.6-sol")
        self.assertEqual(policy["fallback"]["task"]["model"], "gpt-5.6-sol")
        self.assertEqual(policy["high"], {"model": "gpt-5.6-sol", "reasoning_effort": "high"})
        self.assertEqual(policy["xhigh"], {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"})

    def test_dynamic_policy_uses_auto_review_and_medium_for_tool_work(self):
        policy = select_agent_policy("Design and render a clean KiCad PCB and CAD holder")

        self.assertEqual(policy["model"], "auto-code-review")
        self.assertEqual(policy["reasoning_effort"], "medium")
        self.assertEqual(policy["sandbox"], "danger-full-access")

    def test_ultra_aliases_xhigh_and_plan_is_read_only(self):
        policy = select_agent_policy(
            "Reconstruct the exact Shapr3D design",
            model="sol",
            effort="ultra",
            mode="plan",
        )

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "xhigh")
        self.assertEqual(policy["effort_label"], "xhigh")
        self.assertEqual(policy["sandbox"], "read-only")

    def test_protein_structure_work_uses_auto_review_medium(self):
        policy = select_agent_policy("Use AlphaFold to predict COL1A1 and assess inhibitor evidence")

        self.assertEqual(policy["model"], "auto-code-review")
        self.assertEqual(policy["reasoning_effort"], "medium")
        self.assertEqual(policy["effort_label"], "medium")

    def test_capability_catalog_covers_integrated_lab_tools(self):
        ids = {item["id"] for item in capability_catalog(ROOT)}

        self.assertTrue(
            {
                "cad-shapr3d",
                "kicad-pcb",
                "blender-3d",
                "tex-paper",
                "wechat-chatops",
                "labview-control",
                "protein-structure",
                "presentations",
            }.issubset(ids)
        )

    def test_presentation_work_uses_sol_xhigh(self):
        with patch.dict(
            "os.environ",
            {"LABCANVAS_AGENT_STANDARD_MODEL": "legacy-standard-model"},
        ):
            policy = select_agent_policy("Create a polished PowerPoint presentation with editable slides")

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "xhigh")
        self.assertEqual(policy["timeout_seconds"], 10800)
        knowledge = selected_packaged_knowledge("Create an editable PPTX presentation")
        self.assertIn("## Presentations", knowledge)
        self.assertIn("Never generate a complete slide", knowledge)

    def test_engineering_artifacts_have_canvas_types(self):
        self.assertEqual(artifact_kind_for_path("holder.step"), "model")
        self.assertEqual(artifact_kind_for_path("print.3mf"), "model")
        self.assertEqual(content_type_for_path("report.pdf"), "application/pdf")
        self.assertEqual(
            content_type_for_path("deck.pptx"),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        self.assertEqual(content_type_for_path("board.kicad_pro"), "application/json; charset=utf-8")

    def test_prompt_packages_cad_evidence_and_artifact_contract(self):
        policy = select_agent_policy("Design a sensor holder")
        prompt = build_agent_prompt(
            "Design a sensor holder",
            root=ROOT,
            task_dir=ROOT / "output" / "webapp" / "agent" / "test",
            policy=policy,
            conversation_id="test",
        )

        self.assertIn("Shapr3D", prompt)
        self.assertIn("openhi-print-fit-and-thread-reference.md", prompt)
        self.assertIn("KiCad", prompt)
        self.assertIn("LabVIEW", prompt)
        self.assertIn("agent-result.json", prompt)

    def test_packaged_knowledge_is_selected_by_domain(self):
        short = selected_packaged_knowledge("Reply with the current status")
        cad = selected_packaged_knowledge("Design a Shapr3D C-mount holder")
        protein = selected_packaged_knowledge("Use AlphaFold for this protein structure")

        self.assertNotIn("## KiCad and PCB", short)
        self.assertNotIn("## CAD and Shapr3D-Compatible Design", short)
        self.assertIn("## CAD and Shapr3D-Compatible Design", cad)
        self.assertIn("## Protein Structure and AlphaFold", protein)
        self.assertLess(len(short), len(cad))

    def test_task_runner_registers_declared_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            source = root / "design.step"
            source.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            created = create_agent_task(
                {
                    "message": "Create a test STEP",
                    "conversation_id": "unit-test",
                    "model": "gpt-5.6-sol",
                    "effort": "low",
                },
                storage,
                root=root,
                launch=False,
            )
            task_id = created["task"]["id"]

            def fake_runner(prompt, **kwargs):
                task_dir = kwargs["task_dir"]
                (task_dir / "agent-result.json").write_text(
                    json.dumps(
                        {
                            "reply": "Created and checked the STEP.",
                            "artifacts": [{"path": str(source), "title": "Test STEP", "kind": "model"}],
                            "actions": ["validated STEP"],
                            "needs_confirmation": False,
                        }
                    ),
                    encoding="utf-8",
                )
                return {"ok": True, "backend": "codex", "returncode": 0, "message": "done"}

            result = run_agent_task(task_id, storage, root=root, backend_runner=fake_runner)
            stored = AgentTaskStore(storage).read(task_id)

        self.assertTrue(result["ok"])
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["actions"], ["validated STEP"])
        self.assertEqual(len(stored["artifacts"]), 1)
        self.assertTrue(stored["artifacts"][0]["path"].endswith(".step"))

    def test_codex_sessions_remain_isolated_by_conversation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            calls = []

            def fake_codex_process(prompt, **kwargs):
                calls.append((prompt, kwargs["thread_id"]))
                thread_id = kwargs["thread_id"] or f"thread-{prompt}"
                return {"ok": True, "backend": "codex", "returncode": 0, "message": "done", "thread_id": thread_id}

            with (
                patch("agenticapp.workspace_agent.resolve_codex_binary", return_value="/bin/true"),
                patch("agenticapp.workspace_agent._run_codex_process", side_effect=fake_codex_process),
            ):
                for conversation, prompt in (("cad", "cad"), ("pcb", "pcb"), ("cad", "cad-followup")):
                    run_codex_turn(
                        prompt,
                        policy={"model": "gpt-5.6-sol", "reasoning_effort": "low"},
                        conversation_id=conversation,
                        task_dir=storage / "agent" / "tasks" / prompt,
                        storage_dir=storage,
                        root=root,
                        pid_callback=None,
                    )

            registry = json.loads((storage / "agent" / "sessions" / "sessions.json").read_text(encoding="utf-8"))

        self.assertEqual(calls, [("cad", ""), ("pcb", ""), ("cad-followup", "thread-cad")])
        self.assertEqual(registry["cad"]["thread_id"], "thread-cad")
        self.assertEqual(registry["pcb"]["thread_id"], "thread-pcb")
        self.assertEqual(registry["cad"]["turn_count"], 2)

    def test_cancel_terminates_process_groups_and_clears_pids(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "output" / "webapp"
            created = create_agent_task(
                {"message": "Render a test holder", "conversation_id": "cancel-test"},
                storage,
                root=tmp,
                launch=False,
            )
            task_id = created["task"]["id"]
            AgentTaskStore(storage).update(task_id, status="running", agent_pid=12345, worker_pid=12346)

            with patch("agenticapp.workspace_agent.os.killpg") as killpg:
                result = cancel_agent_task(task_id, storage)
            stored = AgentTaskStore(storage).read(task_id)

        self.assertTrue(result["ok"])
        self.assertEqual(stored["status"], "canceled")
        self.assertEqual(stored["agent_pid"], 0)
        self.assertEqual(stored["worker_pid"], 0)
        self.assertEqual([call.args[0] for call in killpg.call_args_list], [12345, 12346])

    def test_aginti_fallback_uses_noninteractive_run_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            captured = {}

            def fake_process(command, **kwargs):
                captured["command"] = command
                captured["cwd"] = kwargs["cwd"]
                captured["input_text"] = kwargs["input_text"]
                return {"ok": True, "backend": "aginti", "returncode": 0, "message": "done"}

            with (
                patch("agenticapp.workspace_agent.aginti_supports_stdin_run", return_value=True),
                patch("agenticapp.workspace_agent._communicate_process", side_effect=fake_process),
            ):
                result = run_aginti_turn(
                    "Inspect the CAD design",
                    policy={"timeout_seconds": 30},
                    task_dir=storage / "agent" / "tasks" / "test",
                    storage_dir=storage,
                    root=root,
                    pid_callback=None,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(captured["command"], ["aginti", "run", "--stdin"])
        self.assertEqual(captured["cwd"], root)
        self.assertEqual(captured["input_text"], "Inspect the CAD design")
        self.assertEqual(result["invocation"], "stdin-run")

    def test_aginti_legacy_fallback_uses_private_prompt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            task_dir = storage / "agent" / "tasks" / "legacy"
            captured = {}

            def fake_process(command, **kwargs):
                captured["command"] = command
                captured["input_text"] = kwargs["input_text"]
                return {"ok": True, "backend": "aginti", "returncode": 0, "message": "done"}

            with (
                patch("agenticapp.workspace_agent.aginti_supports_stdin_run", return_value=False),
                patch("agenticapp.workspace_agent._communicate_process", side_effect=fake_process),
            ):
                result = run_aginti_turn(
                    "Inspect the private CAD task",
                    policy={"timeout_seconds": 30},
                    task_dir=task_dir,
                    storage_dir=storage,
                    root=root,
                    pid_callback=None,
                )

            prompt_path = task_dir / "aginti-prompt.md"
            command_text = captured["command"][-1]
            prompt_text = prompt_path.read_text(encoding="utf-8")

        self.assertEqual(captured["input_text"], "")
        self.assertIn("aginti-prompt.md", command_text)
        self.assertNotIn("private CAD task", command_text)
        self.assertEqual(prompt_text, "Inspect the private CAD task")
        self.assertEqual(result["invocation"], "prompt-file")


if __name__ == "__main__":
    unittest.main()
