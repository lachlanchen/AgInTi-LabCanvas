import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agenticapp.workspace_agent import (
    _aginti_machine_command,
    _parse_aginti_machine_result,
    AgentTaskStore,
    build_agent_prompt,
    cancel_agent_task,
    capability_catalog,
    create_agent_task,
    backend_should_fallback,
    model_unavailable_result,
    run_aginti_turn,
    run_agent_task,
    run_backend_turn,
    run_codex_turn,
    select_agent_policy,
    selected_routine_contracts,
    selected_packaged_knowledge,
    workspace_artifact_name_is_generic,
)
from agenticapp.artifacts import artifact_kind_for_path, content_type_for_path
from agenticapp.backends import load_model_policy


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceAgentTests(unittest.TestCase):
    def test_codex_model_unavailable_classifier_matches_real_cli_errors(self):
        unsupported = {
            "stderr_tail": (
                "The 'auto-code-review' model is not supported when using Codex "
                "with a ChatGPT account."
            )
        }
        unavailable = {
            "stderr_tail": "Your project does not have access to model gpt-5.6-sol."
        }

        for result in (unsupported, unavailable):
            with self.subTest(result=result):
                self.assertTrue(model_unavailable_result(result))
                self.assertTrue(backend_should_fallback(result))

    def test_codex_access_error_falls_back_to_aginti(self):
        codex_error = {
            "ok": False,
            "backend": "codex",
            "returncode": 1,
            "stderr_tail": "Your project does not have access to model gpt-5.6-sol.",
        }
        aginti_success = {
            "ok": True,
            "backend": "aginti",
            "returncode": 0,
            "message": "completed",
        }

        with (
            patch("agenticapp.workspace_agent.run_codex_turn", return_value=codex_error),
            patch("agenticapp.workspace_agent.run_aginti_turn", return_value=aginti_success),
        ):
            result = run_backend_turn(
                "Complete the task",
                policy={"backend": "codex", "fallback_to_aginti": True},
                conversation_id="fallback-test",
                task_dir=Path("/tmp/fallback-test"),
                storage_dir=Path("/tmp/fallback-test-storage"),
                root=ROOT,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "aginti")
        self.assertEqual([item["backend"] for item in result["attempts"]], ["codex", "aginti"])

    def test_aginti_unresolved_dsml_tool_call_is_not_accepted_as_success(self):
        parsed = _parse_aginti_machine_result(
            {
                "ok": True,
                "returncode": 0,
                "message": json.dumps(
                    {
                        "ok": True,
                        "sessionId": "tool-session",
                        "result": (
                            '<｜｜DSML｜｜tool_calls>\n'
                            '<｜｜DSML｜｜invoke name="read_file">\n'
                            '<｜｜DSML｜｜parameter name="file">README.md'
                            '</｜｜DSML｜｜parameter>\n'
                            '</｜｜DSML｜｜invoke>\n'
                            '</｜｜DSML｜｜tool_calls>'
                        ),
                    }
                ),
            },
            fallback_session_id="fallback-session",
        )

        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["message"], "")
        self.assertEqual(parsed["reason"], "unresolved_tool_protocol")

    def test_aginti_stopped_machine_result_is_not_accepted_as_success(self):
        parsed = _parse_aginti_machine_result(
            {
                "ok": True,
                "returncode": 0,
                "message": json.dumps(
                    {
                        "ok": True,
                        "sessionId": "stopped-session",
                        "result": "I stopped safely instead of claiming completion.",
                        "stopped": True,
                        "failed": False,
                        "reason": "tool_contract_violation",
                    }
                ),
            },
            fallback_session_id="fallback-session",
        )

        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["message"], "")
        self.assertTrue(parsed["stopped"])
        self.assertEqual(parsed["reason"], "tool_contract_violation")

    def test_shared_model_policy_uses_low_chat_medium_task_and_sol_fallback(self):
        policy = load_model_policy(ROOT / "configs" / "model-policy.json")
        self.assertEqual(policy["primary_backend"], "aginti")
        self.assertEqual(policy["aginti"]["provider_chain"], ["deepseek", "localllm"])
        self.assertEqual(
            policy["aginti"]["provider_models_by_effort"]["localllm"]["medium"],
            "localllm-deep",
        )
        self.assertEqual(policy["chat"], {"model": "auto-code-review", "reasoning_effort": "low"})
        self.assertEqual(policy["task"], {"model": "auto-code-review", "reasoning_effort": "medium"})
        self.assertEqual(policy["fallback"]["chat"]["model"], "gpt-5.6-sol")
        self.assertEqual(policy["fallback"]["task"]["model"], "gpt-5.6-sol")
        self.assertEqual(policy["high"], {"model": "gpt-5.6-sol", "reasoning_effort": "high"})
        self.assertEqual(policy["xhigh"], {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"})

    def test_dynamic_policy_uses_auto_review_and_medium_for_tool_work(self):
        policy = select_agent_policy("Design and render a clean KiCad PCB and CAD holder")

        self.assertEqual(policy["backend"], "aginti")
        self.assertEqual(policy["model"], "provider-default")
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

    def test_plan_prompt_scopes_evidence_and_does_not_require_result_file(self):
        prompt = build_agent_prompt(
            "Identify the existing LazyEdit routine without changing files.",
            root=ROOT,
            task_dir=ROOT / "output" / "test-plan",
            policy={
                "backend": "aginti",
                "model": "provider-default",
                "reasoning_effort": "low",
                "mode": "plan",
            },
            conversation_id="plan-contract",
        )

        self.assertIn('AGINTI_EVIDENCE_SCOPE_JSON: {"mode":"plan-response"', prompt)
        self.assertIn("Do not create `agent-result.json`", prompt)
        self.assertNotIn("At the end, write", prompt)

    def test_protein_structure_work_uses_auto_review_medium(self):
        policy = select_agent_policy("Use AlphaFold to predict COL1A1 and assess inhibitor evidence")

        self.assertEqual(policy["backend"], "aginti")
        self.assertEqual(policy["model"], "provider-default")
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
                "musia-music",
                "books-search",
                "pocketpolyglot-books",
                "integration-feedback",
            }.issubset(ids)
        )

    def test_presentation_work_uses_sol_xhigh(self):
        with patch.dict(
            "os.environ",
            {"LABCANVAS_AGENT_STANDARD_MODEL": "legacy-standard-model"},
        ):
            policy = select_agent_policy("Create a polished PowerPoint presentation with editable slides")

        self.assertEqual(policy["model"], "provider-default")
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
        self.assertIn(
            f'"artifact_root":"{ROOT / "output" / "webapp" / "agent" / "test"}"',
            prompt,
        )

    def test_packaged_knowledge_is_selected_by_domain(self):
        short = selected_packaged_knowledge("Reply with the current status")
        cad = selected_packaged_knowledge("Design a Shapr3D C-mount holder")
        protein = selected_packaged_knowledge("Use AlphaFold for this protein structure")
        music = selected_packaged_knowledge("Generate a Musia song and then make an MV")
        books = selected_packaged_knowledge(
            "Continue this PocketPolyglot quadrilingual book and report progress"
        )

        self.assertNotIn("## KiCad and PCB", short)
        self.assertNotIn("## CAD and Shapr3D-Compatible Design", short)
        self.assertIn("## CAD and Shapr3D-Compatible Design", cad)
        self.assertIn("## Protein Structure and AlphaFold", protein)
        self.assertIn("## Music and Music Video", music)
        self.assertIn("## Books and PocketPolyglot", books)
        self.assertIn("one durable PocketPolyglot project per book", books)
        self.assertLess(len(short), len(cad))

    def test_routine_registry_progressively_discloses_existing_entrypoints(self):
        request = (
            "Generate a LALACHAN Xiaoyunque video, create music with Musia, then publish the final video "
            "through LazyEdit to YouTube and Instagram."
        )
        contracts = selected_routine_contracts(request, ROOT)
        ids = {item["id"] for item in contracts}
        policy = select_agent_policy(request, backend="aginti")
        prompt = build_agent_prompt(
            request,
            root=ROOT,
            task_dir=ROOT / "output" / "webapp" / "agent" / "routine-test",
            policy=policy,
            conversation_id="routine-test",
        )

        self.assertTrue({"lalachan-video", "musia-music", "lazyedit-video-publish"}.issubset(ids))
        self.assertIn("watch_thread_dom_download.py", prompt)
        self.assertIn("labcanvas music submit", prompt)
        self.assertIn("lazyedit_publish.py", prompt)
        self.assertIn("Invoke a matched ready routine", prompt)

    def test_dictated_phone_schedule_message_request_selects_wechat_health_routine(self):
        request = (
            "i was checking phone and schedulr tell me which daily things delivered "
            "and can msg from me and other people reach agent"
        )

        contracts = selected_routine_contracts(request, ROOT)

        self.assertEqual([item["id"] for item in contracts], ["wechat-chatops"])
        self.assertEqual(
            contracts[0]["commands"][0],
            "PYTHONPATH=src python -m agenticapp wechat health --compact --json",
        )
        self.assertIn("Do not inspect raw chat text", contracts[0]["guidance"])

    def test_phone_holder_does_not_select_wechat_transport(self):
        contracts = selected_routine_contracts(
            "Design a printable phone holder in CAD and export STEP",
            ROOT,
        )

        self.assertNotIn("wechat-chatops", {item["id"] for item in contracts})

    def test_wechat_health_prompt_discloses_authoritative_read_only_shortcut(self):
        request = (
            "check mobile msg and schedulr for labcanvas agent, do not send anything"
        )
        prompt = build_agent_prompt(
            request,
            root=ROOT,
            task_dir=ROOT / "output" / "webapp" / "agent" / "wechat-health-test",
            policy=select_agent_policy(request, backend="aginti"),
            conversation_id="wechat-health-test",
        )

        self.assertIn("`wechat-chatops` ready=true", prompt)
        self.assertIn("agenticapp wechat health --compact --json", prompt)
        self.assertIn("Do not inspect raw chat text or private message ledgers", prompt)

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
        self.assertEqual(Path(stored["artifacts"][0]["path"]).name, "design.step")
        response_name = Path(stored["response_artifact"]["path"]).name
        self.assertTrue(response_name.endswith("-test-step-response.md"))
        self.assertNotEqual(response_name, "response.md")
        self.assertNotIn(task_id, response_name)

    def test_task_runner_replaces_generic_artifact_name_with_declared_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            source = root / "report.pdf"
            source.write_bytes(b"%PDF-1.4\norganoid evidence")
            created = create_agent_task(
                {
                    "message": "Create an organoid imaging evidence review.",
                    "conversation_id": "meaningful-artifact-name",
                },
                storage,
                root=root,
                launch=False,
            )
            task_id = created["task"]["id"]

            def fake_runner(_prompt, **kwargs):
                (kwargs["task_dir"] / "agent-result.json").write_text(
                    json.dumps(
                        {
                            "reply": "The review is ready.",
                            "artifacts": [
                                {
                                    "path": str(source),
                                    "title": "Organoid imaging evidence review",
                                    "kind": "file",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return {"ok": True, "backend": "aginti", "returncode": 0, "message": "done"}

            result = run_agent_task(task_id, storage, root=root, backend_runner=fake_runner)
            stored = AgentTaskStore(storage).read(task_id)

        self.assertTrue(result["ok"])
        artifact_name = Path(stored["artifacts"][0]["path"]).name
        self.assertEqual(artifact_name, "organoid-imaging-evidence-review.pdf")
        self.assertNotRegex(artifact_name, r"-[0-9a-f]{8}\.pdf$")
        self.assertNotIn(task_id, stored["artifacts"][0]["preview"])

    def test_task_runner_uses_request_for_generic_name_and_hides_local_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            source = root / "report-final.pdf"
            source.write_bytes(b"%PDF-1.4\norganoid evidence")
            created = create_agent_task(
                {
                    "message": "Create an organoid imaging evidence review.",
                    "conversation_id": "meaningful-artifact-request",
                },
                storage,
                root=root,
                launch=False,
            )
            task_id = created["task"]["id"]

            def fake_runner(_prompt, **kwargs):
                (kwargs["task_dir"] / "agent-result.json").write_text(
                    json.dumps(
                        {
                            "reply": f"Completed the report at {source}.",
                            "artifacts": [{"path": str(source), "kind": "file"}],
                        }
                    ),
                    encoding="utf-8",
                )
                return {"ok": True, "backend": "aginti", "returncode": 0, "message": "done"}

            result = run_agent_task(task_id, storage, root=root, backend_runner=fake_runner)
            stored = AgentTaskStore(storage).read(task_id)

        self.assertTrue(result["ok"])
        artifact = stored["artifacts"][0]
        self.assertEqual(Path(artifact["path"]).name, "organoid-imaging-evidence-review.pdf")
        self.assertEqual(artifact["title"], "organoid-imaging-evidence-review.pdf")
        self.assertNotIn(str(root), stored["reply"])
        self.assertEqual(
            stored["reply"],
            "Completed the report at organoid-imaging-evidence-review.pdf.",
        )

    def test_task_runner_ignores_generic_declared_title_and_uses_exact_content_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            source = root / "result.txt"
            source.write_text(
                "AgInTi scoped artifact routing is working.", encoding="utf-8"
            )
            message = (
                "Create one plain-text artifact. Use the generic source filename result.txt. "
                "Its exact content must be: AgInTi scoped artifact routing is working. "
                "Verify the file before finishing."
            )
            created = create_agent_task(
                {
                    "message": message,
                    "conversation_id": "generic-title-fallback",
                },
                storage,
                root=root,
                launch=False,
            )
            task_id = created["task"]["id"]

            def fake_runner(_prompt, **kwargs):
                (kwargs["task_dir"] / "agent-result.json").write_text(
                    json.dumps(
                        {
                            "reply": "Created result.txt with the confirmed content.",
                            "artifacts": [
                                {
                                    "path": str(source),
                                    "title": "Delivery confirmation",
                                    "kind": "text",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return {
                    "ok": True,
                    "backend": "aginti",
                    "returncode": 0,
                    "message": "done",
                }

            result = run_agent_task(
                task_id, storage, root=root, backend_runner=fake_runner
            )
            stored = AgentTaskStore(storage).read(task_id)

        self.assertTrue(result["ok"])
        artifact_name = Path(stored["artifacts"][0]["path"]).name
        self.assertEqual(
            artifact_name, "aginti-scoped-artifact-routing-is-working.txt"
        )
        self.assertEqual(stored["artifacts"][0]["title"], artifact_name)
        self.assertNotEqual(artifact_name, "txt.txt")
        self.assertEqual(
            stored["reply"],
            "Created aginti-scoped-artifact-routing-is-working.txt with the confirmed content.",
        )

    def test_generic_artifact_detection_covers_versions_and_non_english_placeholders(self):
        for filename in (
            "file-v2.txt",
            "data-final.csv",
            "delivery-confirmation.txt",
            "final-report-v3.pdf",
            "报告.pdf",
            "結果.docx",
            "レポート.pdf",
        ):
            with self.subTest(filename=filename):
                self.assertTrue(workspace_artifact_name_is_generic(filename))
        self.assertFalse(
            workspace_artifact_name_is_generic("organoid-review-delivery.pdf")
        )

    def test_task_runner_accepts_artifact_from_allowlisted_sibling_routine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "AgenticApp"
            root.mkdir()
            storage = root / "output" / "webapp"
            source = Path(tmp) / "Musia" / "output" / "reviewed-song.mp3"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"ID3\x04\x00\x00")
            created = create_agent_task(
                {"message": "Return the reviewed Musia song", "conversation_id": "music-test", "backend": "aginti"},
                storage,
                root=root,
                launch=False,
            )
            task_id = created["task"]["id"]

            def fake_runner(_prompt, **kwargs):
                (kwargs["task_dir"] / "agent-result.json").write_text(
                    json.dumps(
                        {
                            "reply": "The reviewed song is ready.",
                            "artifacts": [{"path": str(source), "title": "Reviewed song", "kind": "audio"}],
                            "actions": ["verified sibling routine artifact"],
                            "needs_confirmation": False,
                        }
                    ),
                    encoding="utf-8",
                )
                return {"ok": True, "backend": "aginti", "returncode": 0, "message": "done"}

            result = run_agent_task(task_id, storage, root=root, backend_runner=fake_runner)
            stored = AgentTaskStore(storage).read(task_id)

        self.assertTrue(result["ok"])
        self.assertEqual(len(stored["artifacts"]), 1)
        self.assertTrue(stored["artifacts"][0]["path"].endswith(".mp3"))

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
                session_id = command[command.index("--session-id") + 1]
                return {
                    "ok": True,
                    "backend": "aginti",
                    "returncode": 0,
                    "message": json.dumps(
                        {
                            "ok": True,
                            "sessionId": session_id,
                            "result": "done",
                            "failed": False,
                        }
                    ),
                }

            with (
                patch("agenticapp.workspace_agent.aginti_supports_stdin_run", return_value=True),
                patch("agenticapp.workspace_agent._communicate_process", side_effect=fake_process),
            ):
                result = run_aginti_turn(
                    "Inspect the CAD design",
                    policy={"timeout_seconds": 30},
                    conversation_id="cad-chat",
                    task_dir=storage / "agent" / "tasks" / "test",
                    storage_dir=storage,
                    root=root,
                    pid_callback=None,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(captured["command"][0:2], ["aginti", "run"])
        self.assertIn("--session-id", captured["command"])
        self.assertIn("--stdin", captured["command"])
        self.assertIn("--json", captured["command"])
        self.assertEqual(captured["command"][captured["command"].index("--provider") + 1], "deepseek")
        self.assertEqual(captured["cwd"], root)
        self.assertEqual(captured["input_text"], "Inspect the CAD design")
        self.assertEqual(result["invocation"], "machine-run")

    def test_aginti_provider_fallback_continues_the_same_fresh_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "output" / "webapp"
            commands = []
            inputs = []

            def fake_process(command, **kwargs):
                commands.append(command)
                inputs.append(kwargs["input_text"])
                if len(commands) == 1:
                    return {
                        "ok": False,
                        "backend": "aginti",
                        "returncode": 1,
                        "message": json.dumps(
                            {"ok": False, "sessionId": command[command.index("--session-id") + 1], "reason": "API key required"}
                        ),
                        "stderr_tail": "",
                    }
                return {
                    "ok": True,
                    "backend": "aginti",
                    "returncode": 0,
                    "message": json.dumps(
                        {"ok": True, "sessionId": command[2], "result": "local fallback completed"}
                    ),
                    "stderr_tail": "",
                }

            settings_path = storage / "settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps({"aginti": {"provider_chain": ["deepseek", "localllm"]}}),
                encoding="utf-8",
            )
            with (
                patch("agenticapp.workspace_agent.aginti_supports_stdin_run", return_value=True),
                patch("agenticapp.workspace_agent._communicate_process", side_effect=fake_process),
            ):
                result = run_aginti_turn(
                    "Continue one exact task",
                    policy={"timeout_seconds": 30, "reasoning_effort": "medium"},
                    conversation_id="fallback-chat",
                    task_dir=storage / "agent" / "tasks" / "fallback",
                    storage_dir=storage,
                    root=root,
                    pid_callback=None,
                )

        session_id = commands[0][commands[0].index("--session-id") + 1]
        self.assertEqual(commands[0][0:2], ["aginti", "run"])
        self.assertEqual(commands[1][0:3], ["aginti", "resume", session_id])
        self.assertEqual(commands[0][commands[0].index("--provider") + 1], "deepseek")
        self.assertEqual(commands[1][commands[1].index("--provider") + 1], "localllm")
        self.assertEqual(commands[0][commands[0].index("--model") + 1], "deepseek-v4-flash")
        self.assertEqual(commands[1][commands[1].index("--model") + 1], "localllm-deep")
        self.assertEqual(inputs[0], "Continue one exact task")
        self.assertIn("Provider handoff", inputs[1])
        self.assertNotIn("Continue one exact task", inputs[1])
        self.assertTrue(result["ok"])
        self.assertFalse(result["resumed"])
        self.assertTrue(result["fallback_continued_same_session"])

    def test_aginti_machine_command_replaces_managed_transport_args(self):
        command = _aginti_machine_command(
            ["aginti", "run", "--session-id", "stale", "--stdin", "--json", "--provider", "openai"],
            previous_id="live-session",
            new_session_id="",
            provider="localllm",
        )

        self.assertEqual(command[0:3], ["aginti", "resume", "live-session"])
        self.assertEqual(command.count("resume"), 1)
        self.assertNotIn("stale", command)
        self.assertEqual(command[command.index("--provider") + 1], "localllm")

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
                    conversation_id="legacy-chat",
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
