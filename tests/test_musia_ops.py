from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from agenticapp import cli
from agenticapp import musia_ops as musia


class MusiaOpsTests(unittest.TestCase):
    def test_cli_registers_music_commands(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "music",
                "submit",
                "Create",
                "a",
                "song",
                "--source-scope",
                "chat:EchoMind",
                "--mode",
                "worker",
                "--dry-run",
                "--json",
            ]
        )

        self.assertEqual(args.music_command, "submit")
        self.assertEqual(args.source_scope, "chat:EchoMind")
        self.assertEqual(args.mode, "worker")
        self.assertTrue(args.dry_run)

    def test_scope_registry_never_stores_raw_chat_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Musia"
            registry = Path(tmp) / "registry.json"
            session = {
                "id": "session-1",
                "working_dir": str(root / "data" / "labcanvas_sessions" / "test"),
            }
            with mock.patch.object(musia, "_session_rows", return_value=[]), mock.patch.object(
                musia,
                "_request_json",
                return_value=session,
            ):
                result = musia.ensure_session(
                    root=root,
                    base_url="http://127.0.0.1:8767",
                    registry_path=registry,
                    source_scope="private chat name",
                    title="Music",
                )

            self.assertEqual(result["id"], "session-1")
            content = registry.read_text(encoding="utf-8")
            self.assertNotIn("private chat name", content)
            payload = json.loads(content)
            self.assertIn(musia.scope_key("private chat name"), payload["sessions"])

    def test_submit_reuses_session_and_worker_api(self) -> None:
        root = Path("/tmp/Musia")
        session = {"id": "session-7", "working_dir": "/tmp/Musia/data/session-7"}
        response = {
            "mode": "worker",
            "session_id": "session-7",
            "job": {"id": "job-9", "status": "queued"},
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            musia,
            "start_studio",
        ), mock.patch.object(
            musia,
            "ensure_session",
            return_value=session,
        ), mock.patch.object(
            musia,
            "_request_json",
            return_value=response,
        ) as requester:
            result = musia.submit_task(
                root=root,
                base_url="http://127.0.0.1:8767",
                registry_path=Path(tmp) / "registry.json",
                source_scope="chat-a",
                prompt="Generate and review a song",
                task_id="task-1",
            )

        self.assertEqual(result["job"]["id"], "job-9")
        request_payload = requester.call_args.kwargs["payload"]
        self.assertEqual(request_payload["session_id"], "session-7")
        self.assertIn("task-1", request_payload["message"])
        self.assertIn("Generate and review a song", request_payload["message"])

    def test_repeated_task_id_reuses_existing_job_without_resubmission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            source_scope = "chat-a"
            task_id = "task-1"
            message = f"LabCanvas task id: {task_id}\n\nGenerate a song"
            registry.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sessions": {},
                        "tasks": {
                            musia.idempotency_key(source_scope, task_id): {
                                "session_id": "session-7",
                                "job_id": "job-9",
                                "mode": "worker",
                                "prompt_hash": hashlib.sha256(
                                    message.encode("utf-8")
                                ).hexdigest(),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(musia, "start_studio"), mock.patch.object(
                musia,
                "ensure_session",
                return_value={"id": "session-7", "working_dir": "/tmp/session-7"},
            ), mock.patch.object(
                musia,
                "load_job",
                return_value={"id": "job-9", "status": "completed"},
            ), mock.patch.object(musia, "_request_json") as requester:
                result = musia.submit_task(
                    root=Path(tmp),
                    base_url="http://127.0.0.1:8767",
                    registry_path=registry,
                    source_scope=source_scope,
                    prompt="Generate a song",
                    task_id=task_id,
                )

        requester.assert_not_called()
        self.assertTrue(result["reused_task"])
        self.assertFalse(result["revision_required"])
        self.assertFalse(result["submitted"])
        self.assertEqual(result["job"]["id"], "job-9")

    def test_changed_task_prompt_requires_explicit_new_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            source_scope = "chat-a"
            task_id = "task-1"
            registry.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sessions": {},
                        "tasks": {
                            musia.idempotency_key(source_scope, task_id): {
                                "session_id": "session-7",
                                "job_id": "job-9",
                                "mode": "worker",
                                "prompt_hash": "old",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(musia, "start_studio"), mock.patch.object(
                musia,
                "ensure_session",
                return_value={"id": "session-7", "working_dir": "/tmp/session-7"},
            ), mock.patch.object(
                musia,
                "load_job",
                return_value={"id": "job-9", "status": "completed"},
            ), mock.patch.object(musia, "_request_json") as requester:
                result = musia.submit_task(
                    root=Path(tmp),
                    base_url="http://127.0.0.1:8767",
                    registry_path=registry,
                    source_scope=source_scope,
                    prompt="Revise the chorus",
                    task_id=task_id,
                )

        requester.assert_not_called()
        self.assertFalse(result["reused_task"])
        self.assertTrue(result["revision_required"])
        self.assertFalse(result["submitted"])

    def test_exact_artifact_download_uses_safe_response_filename(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"RIFF-audio"
        response.headers = {
            "Content-Disposition": 'attachment; filename="../reviewed master.wav"',
            "Content-Type": "audio/wav",
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            musia.request,
            "urlopen",
            return_value=response,
        ):
            result = musia.download_session_artifact(
                "http://127.0.0.1:8767",
                "session-1",
                "artifact-2",
                Path(tmp),
            )
            target = Path(result["path"])

            self.assertEqual(target.parent, Path(tmp).resolve())
            self.assertEqual(target.name, "reviewed master.wav")
            self.assertEqual(target.read_bytes(), b"RIFF-audio")
            self.assertEqual(result["size_bytes"], len(b"RIFF-audio"))
            self.assertEqual(
                result["sha256"],
                hashlib.sha256(b"RIFF-audio").hexdigest(),
            )

    def test_wait_polls_without_model_calls_until_terminal(self) -> None:
        with mock.patch.object(
            musia,
            "load_job",
            side_effect=[
                {"id": "job-1", "status": "running"},
                {"id": "job-1", "status": "completed", "artifacts": []},
            ],
        ) as loader, mock.patch.object(musia.time, "sleep"):
            result = musia.wait_for_job(
                "http://127.0.0.1:8767",
                "job-1",
                poll_seconds=0.2,
                timeout=5,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(loader.call_count, 2)

    def test_mv_pack_delegates_to_existing_musia_cli(self) -> None:
        args = argparse.Namespace(
            audio="/tmp/song.wav",
            title="Song MV",
            slug="song-mv",
            output_dir="",
            duration=15.0,
            start=None,
            ratio="4:3",
            mood="warm",
            scene="garden",
            copy_references=True,
        )

        command = musia.build_mv_pack_command(Path("/repo/Musia"), args)

        self.assertEqual(command[:3], ["node", "/repo/Musia/bin/musia.js", "mv-pack"])
        self.assertIn(str(Path("/tmp/song.wav").resolve()), command)
        self.assertIn("--copy-references", command)
        self.assertIn("4:3", command)

    def test_start_reuses_ready_studio(self) -> None:
        ready = {
            "ok": True,
            "musia_root": "/repo/Musia",
            "studio_url": "http://127.0.0.1:8767",
            "tmux": True,
            "setup": {"root": "/repo/Musia"},
            "error": "",
        }
        with mock.patch.object(musia, "service_status", return_value=ready), mock.patch.object(
            musia.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0),
        ) as runner:
            result = musia.start_studio(
                Path("/repo/Musia"),
                "http://127.0.0.1:8767",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["reused"])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
