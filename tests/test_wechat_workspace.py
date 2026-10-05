from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wechat_workspace as workspace
import wechat_agent_backend as backend
import wechat_codex_sessions as sessions
from tests.test_wechat_task_worker import load_worker


class WeChatWorkspaceTests(unittest.TestCase):
    def test_exact_scopes_cannot_collide_after_slug_normalization(self):
        paths = [workspace.chat_workspace(name) for name in (
            "LightMind", "lightmind", "a/b", "a-b", "LabAgent",
            "wecom:external:LabAgent", "../outside", "\u516c\u53f8",
        )]
        self.assertEqual(len(set(paths)), len(paths))
        self.assertTrue(all(path.parent == ROOT / "output/chat_workspaces" for path in paths))

    def test_workspace_is_private_and_rejects_symlink_redirects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = workspace.ensure_chat_workspace("company", root=root)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            other = root / "unrelated"
            other.mkdir()
            path.rmdir()
            path.symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                workspace.ensure_chat_workspace("company", root=root)

    def test_references_are_operator_owned_and_not_guessed(self):
        self.assertEqual(workspace.approved_reference_paths({}), [])
        self.assertEqual(workspace.approved_reference_paths({
            "workspace_read_paths": "/not/a/list",
            "assistant_context": {"reference_paths": "/also/not/a/list"},
        }), [])
        self.assertEqual(workspace.approved_reference_paths({
            "workspace_read_paths": ["/company/docs", "/company/docs"],
        }), ["/company/docs"])

    def test_backend_scopes_primary_and_fallback_without_model_change(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory)
            with (
                mock.patch.object(backend, "ensure_chat_workspace", return_value=local),
                mock.patch.object(backend, "quota_aware_codex_preference", return_value=("test-model", "low", None)),
                mock.patch.object(backend, "run_single_backend_attempt", side_effect=lambda prompt, **kw: (
                    calls.append((prompt, kw)) or {"ok": True, "message": "done", "backend": "aginti"}
                )),
            ):
                result = backend.run_agent_session(
                    "business question", backend="codex", chat_name="company",
                    role="worker", model="test-model", reasoning_effort="low",
                    sandbox="danger-full-access", timeout_seconds=30,
                    backend_config={"workspace_read_paths": ["/company/docs"]},
                    backend_prompts={"aginti": "same business question"},
                )
            self.assertTrue(result["ok"])
            prompt, call = calls[0]
            self.assertIn(str(local), prompt)
            self.assertIn("/company/docs", prompt)
            self.assertEqual(call["workdir"], local)
            self.assertEqual(call["attempt"]["sandbox"], "workspace-write")
            self.assertEqual(call["attempt"]["model"], "test-model")

    def test_readonly_route_stays_readonly(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(backend, "ensure_chat_workspace", return_value=Path(directory)),
            mock.patch.object(backend, "quota_aware_codex_preference", return_value=("test", "low", None)),
            mock.patch.object(backend, "run_single_backend_attempt", return_value={"ok": True, "message": "done", "backend": "aginti"}) as invoke,
        ):
            backend.run_agent_session(
                "chat", backend="codex", chat_name="company", role="route",
                model="test", reasoning_effort="low", sandbox="read-only",
                timeout_seconds=30,
            )
            self.assertEqual(invoke.call_args.kwargs["attempt"]["sandbox"], "read-only")

    def test_aginti_cannot_redirect_scoped_workspace_to_global_environment(self):
        path = workspace.chat_workspace("company")
        with mock.patch.dict(backend.os.environ, {"WECHAT_AGINTI_WORKSPACE": str(ROOT)}):
            self.assertEqual(backend.aginti_workdir_from_config({"workspace": str(ROOT)}, path), path)
        with mock.patch.object(backend, "run_aginti_session", return_value={"ok": True, "message": "done"}) as invoke:
            backend.run_single_backend_attempt(
                "task", attempt={"backend": "aginti", "sandbox": "workspace-write", "timeout_seconds": 30},
                primary_backend="codex", chat_name="company", role="worker",
                workdir=path, reuse=True, registry_path=sessions.DEFAULT_REGISTRY,
                backend_config={"aginti": {"workspace": str(ROOT), "sandbox_mode": "host", "allow_host_workspace": True}},
            )
        policy = invoke.call_args.kwargs["backend_config"]
        self.assertEqual(policy["workspace"], str(path))
        self.assertEqual(policy["sandbox_mode"], "docker-workspace")
        self.assertFalse(policy["allow_host_workspace"])

    def test_task_artifacts_are_scoped_but_recorded_legacy_paths_are_preserved(self):
        worker = load_worker()
        task = {"id": "test-1", "session_scope": "company"}
        self.assertEqual(worker.worker_artifact_dir(task), workspace.chat_workspace("company") / "tasks/test-1")
        task["artifact_dir"] = str(ROOT / "output/wechat_worker/legacy")
        self.assertEqual(worker.worker_artifact_dir(task), Path(task["artifact_dir"]))

    def test_worker_can_read_exact_preflight_source_without_granting_its_parent(self):
        worker = load_worker()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("exact source")
            config = worker.worker_backend_config({
                "workspace_read_paths": "/not/a/list",
                "agent_backend_config": {"workspace_read_paths": "/not/a/list"},
                "preflight": {"file_intake": {"agent_context_path": str(source)}},
            }, "codex")
        self.assertEqual(config["workspace_read_paths"], [str(source)])
        self.assertNotIn(directory, config["workspace_read_paths"])

    def test_fallback_does_not_mark_its_own_task_directory_readonly(self):
        path = workspace.chat_workspace("company")
        with mock.patch.object(backend, "run_aginti_session", return_value={"ok": True, "message": "done"}) as invoke:
            backend.run_single_backend_attempt(
                "task", attempt={"backend": "aginti", "sandbox": "workspace-write", "timeout_seconds": 30},
                primary_backend="codex", chat_name="company", role="worker",
                workdir=path, reuse=True, registry_path=sessions.DEFAULT_REGISTRY,
                backend_config={"workspace_read_paths": [str(path / "tasks/current")]},
            )
        self.assertNotIn(str(path / "tasks/current"), invoke.call_args.kwargs["backend_config"]["chat_read_paths"])

    def test_codex_cannot_inherit_account_writable_roots(self):
        path = workspace.chat_workspace("company")
        with (
            mock.patch.object(sessions, "resolve_codex_binary", return_value="/bin/codex"),
            mock.patch.object(sessions, "run_process_group", return_value=mock.Mock(returncode=0, stdout="", stderr="")) as invoke,
        ):
            sessions.run_codex_once(
                "chat", thread_id="", model="test", reasoning_effort="low",
                sandbox="workspace-write", timeout_seconds=10, workdir=path,
            )
        command = invoke.call_args.args[0]
        self.assertIn('default_permissions="labcanvas-chat"', command)
        self.assertNotIn("--sandbox", command)
        profile = next(item for item in command if item.startswith("permissions.labcanvas-chat="))
        self.assertIn(str(path), profile)
        self.assertIn('":root"="deny"', profile)
        self.assertIn('approval_policy="never"', command)

    def test_native_profile_contains_host_writes_and_reference_reads(self):
        binary = sessions.resolve_codex_binary()
        if not binary:
            self.skipTest("Codex native sandbox unavailable")
        interpreter = Path("/usr/bin/python3")
        if not interpreter.is_file():
            self.skipTest("Native sandbox probe requires its allowlisted system Python")
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            base = Path(directory)
            own = base / "group"
            own.mkdir()
            reference = base / "approved.txt"
            reference.write_text("approved")
            other = base / "other-chat.txt"
            other.write_text("private")
            outside = base / "outside.txt"
            script = f"""from pathlib import Path
import json
Path({str(own / 'owned.txt')!r}).write_text('owned')
result = {{'approved_read': Path({str(reference)!r}).read_text() == 'approved'}}
try:
    Path({str(other)!r}).read_text()
    result['other_read_denied'] = False
except OSError:
    result['other_read_denied'] = True
for value in [{str(reference)!r}, {str(other)!r}, {str(outside)!r}]:
    try:
        Path(value).write_text('wrong')
    except OSError:
        pass
print(json.dumps(result))
"""
            with workspace.read_reference_scope([str(reference)]):
                args = workspace.codex_workspace_permissions(own, "workspace-write", codex_binary=binary)
            result = subprocess.run(
                [binary, "sandbox", "-P", "labcanvas-chat", "-C", str(own),
                 *args, "--", str(interpreter), "-c", script],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(result.stdout)
            self.assertTrue(evidence["approved_read"])
            self.assertTrue(evidence["other_read_denied"])
            self.assertEqual((own / "owned.txt").read_text(), "owned")
            self.assertEqual(reference.read_text(), "approved")
            self.assertEqual(other.read_text(), "private")
            self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
