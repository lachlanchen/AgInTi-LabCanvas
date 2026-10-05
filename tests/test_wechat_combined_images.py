import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agentic_tools/wechat_gui_agent/scripts"))
import wechat_combined_images as groups
import wechat_tiny11_image as images


def xml(identity="album-1", count=3):
    return (f'<msg><img length="9"/><extcommoninfo><groupinfo><type>1</type>'
            f'<id>{identity}</id><count>{count}</count></groupinfo></extcommoninfo></msg>')


class CombinedImageTests(unittest.TestCase):
    def test_native_group_metadata_and_guarded_parsing(self):
        self.assertEqual(groups.combined_image_group("sender:\n" + xml()),
                         {"id": "album-1", "count": 3, "type": "1"})
        for content in ("", "<msg><img/></msg>", xml(count=101), xml(count=1),
                        xml(identity=""), "<!DOCTYPE msg>" + xml(), xml().replace("</msg>", "")):
            self.assertIsNone(groups.combined_image_group(content))

    def test_native_members_are_ordered_and_exact_not_nearby(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "store.db"
            table = "Msg_" + "a" * 32
            with sqlite3.connect(store) as db:
                db.execute(f'CREATE TABLE {table}(local_id,server_id,create_time,local_type,'
                           'real_sender_id,message_content,compress_content,WCDB_CT_message_content)')
                db.executemany(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?)', [
                    (3, "103", 100, 3, 7, xml(), "", 0),
                    (1, "101", 100, 3, 7, xml(), "", 0),
                    (2, "102", 100, 3, 7, xml(), "", 0),
                    (4, "104", 100, 3, 8, xml(identity="different"), "", 0),
                ])
            task = {"chat": "Shares", "source": {"message_table": table, "local_id": 3,
                                                     "server_id": "103"}}
            with mock.patch.object(images, "image_request"), \
                    mock.patch("wechat_direct_chatops.decode_content", side_effect=lambda a, *rest: a):
                members = images.image_group_tasks(task, groups.combined_image_group(xml()), {}, store)
                self.assertEqual([m["source"]["server_id"] for m in members], ["101", "102", "103"])
                for sql, expected in (
                    (f'UPDATE {table} SET real_sender_id=8 WHERE local_id=1', "identity_mismatch"),
                    (f'UPDATE {table} SET real_sender_id=7,local_type=43 WHERE local_id=1', "separate_video"),
                    (f'DELETE FROM {table} WHERE local_id=1', "incomplete"),
                ):
                    with sqlite3.connect(store) as db:
                        db.execute(sql)
                    with self.assertRaisesRegex(ValueError, expected):
                        images.image_group_tasks(task, groups.combined_image_group(xml()), {}, store)

    def test_followup_text_can_bind_current_album_but_not_other_history(self):
        task = {"chat": "LightMind", "source": {"kind": "text", "local_type": 1,
            "message_table": "table", "message_db": "store", "local_id": 10, "server_id": "110"},
            "message_ledger": [{"chat": "LightMind", "role": "coalesced_source", "kind": "image",
                "message_db": "store", "local_id": i, "server_id": str(100+i)} for i in (8, 9)]}
        group = groups.combined_image_group(xml())
        with mock.patch.object(images, "image_request", return_value=({}, {"combined_image": group})):
            selected = images.coalesced_image_task(task, {}, Path("store"))
        self.assertEqual(selected["source"]["local_id"], 8)
        self.assertEqual(selected["source"]["kind"], "image")
        self.assertEqual(task["source"]["local_id"], 10)
        self.assertIs(selected["message_ledger"], task["message_ledger"])
        with mock.patch.object(images, "image_request", side_effect=[
            ({}, {"combined_image": group}), ({}, {"combined_image": {**group, "id": "other"}}),
        ]):
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                images.coalesced_image_task(task, {}, Path("store"))
        for field, value in (("chat", "Other"), ("message_db", "other"), ("role", "history")):
            wrong = {**task, "message_ledger": [{**entry, field: value} for entry in task["message_ledger"]]}
            self.assertEqual(images.coalesced_image_sources(wrong), [])

    def test_text_with_coalesced_images_uses_native_preflight(self):
        import wechat_task_worker as worker
        task = {"chat": "LightMind", "source": {"kind": "text", "local_type": 1, "message_db": "store"},
                "message_ledger": [{"chat": "LightMind", "role": "coalesced_source", "kind": "image",
                    "message_db": "store", "local_id": 8, "server_id": "108"}]}
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(worker, "uses_tiny11_wechat", return_value=True), \
                mock.patch.object(images, "recover_images", return_value=[]) as recover, \
                mock.patch.object(worker, "refresh_media_sync_for_task") as generic, \
                mock.patch.object(worker, "enrich_media_resolution_copies_with_image_read"), \
                mock.patch.object(worker, "enrich_copies_with_document_read"):
            worker.prepare_media_resolution_preflight(task, Path(folder))
        recover.assert_called_once()
        generic.assert_not_called()

    def test_recover_all_originals_with_distinct_identity_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            group = groups.combined_image_group(xml())
            task = {"source": {"server_id": "103"}}
            members = [{"source": {"server_id": str(sid)}} for sid in (101, 102, 103)]
            def recover(member, path):
                return {"source_path": str(Path(path) / member["source"]["server_id"]),
                        "combined_image": group, "original_resolution_verified": True}
            with mock.patch.object(images, "recover_image", side_effect=recover) as export, \
                    mock.patch.object(images, "image_group_tasks", return_value=members), \
                    mock.patch("wechat_tiny11_bridge.load_config", return_value={}):
                copies = images.recover_images(task, Path(folder))
            self.assertEqual(export.call_count, 3)
            self.assertEqual([c["source_server_id"] for c in copies], ["101", "102", "103"])
            self.assertEqual([c["album_index"] for c in copies], [1, 2, 3])
            self.assertTrue(all("combined_image" not in c for c in copies))
            manifest = Path(folder) / "native-combined-image-export.json"
            self.assertEqual(json.loads(manifest.read_text())["count"], 3)
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)

    def test_album_is_one_joint_vision_call_and_no_resize(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copies = []
            for index in range(3):
                path = root / f"{index}.png"
                Image.new("RGB", (1200, 1600)).save(path)
                copies.append({"task_copy_path": str(path), "album_index": index + 1,
                               "album_count": 3, "original_resolution_verified": True})
            result = {"status": "ok", "text_preview": "All three images understood."}
            with mock.patch.object(worker, "codex_read_image_file", return_value=result) as vision, \
                    mock.patch.object(worker, "read_image_file_with_fallback") as individual, \
                    mock.patch.object(worker, "ocr_image_file", return_value={}):
                worker.enrich_media_resolution_copies_with_image_read(copies, root)
            vision.assert_called_once()
            self.assertEqual(len(vision.call_args.kwargs["additional_images"]), 2)
            individual.assert_not_called()
            self.assertTrue(all(c["image_metadata"]["width"] == 1200 for c in copies))

    def test_sibling_album_tasks_dedupe_but_not_new_text_instruction(self):
        import wechat_direct_chatops as direct
        base = {"chat": "Shares", "status": "done", "album_intake_only": True,
                "routine": {"id": "file_intake"}, "source": {
                    "message_table": "table", "message_db": "store", "local_id": 1,
                    "server_id": "101", "sender": "person", "combined_image": groups.combined_image_group(xml())}}
        with tempfile.TemporaryDirectory() as folder:
            queue = Path(folder) / "queue.jsonl"
            queue.write_text(json.dumps(base) + "\n")
            sibling = {**base, "source": {**base["source"], "local_id": 2, "server_id": "102"}}
            self.assertIsNotNone(direct.find_duplicate_worker_task(queue, sibling))
            self.assertIsNone(direct.find_duplicate_worker_task(queue, {**sibling, "album_intake_only": False}))
            for key, value in (("chat", "Other"),):
                self.assertIsNone(direct.find_duplicate_worker_task(queue, {**sibling, key: value}))
            self.assertIsNone(direct.find_duplicate_worker_task(queue, {
                **sibling, "source": {**sibling["source"], "sender": "other"}}))

    def test_file_intake_retains_all_album_originals_and_reuses_joint_read(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copies = []
            for index in range(3):
                path = root / f"{index}.png"
                Image.new("RGB", (100, 200)).save(path)
                copies.append({"task_copy_path": str(path), "album_index": index + 1,
                               "album_count": 3, "original_resolution_verified": True,
                               "vision": {"status": "ok", "text_preview": "Joint album analysis."}})
            task = {"source": {"kind": "image", "local_type": 3},
                    "preflight": {"media_resolution": {"copied": copies}}}
            with mock.patch.object(worker, "codex_read_image_file") as vision, \
                    mock.patch.object(worker, "ocr_image_file", return_value={}), \
                    mock.patch.object(worker, "enrich_copies_with_document_read"):
                result = worker.prepare_file_intake_preflight(task, root)
            self.assertEqual(len(result["copied"]), 3)
            self.assertEqual([item["album_index"] for item in result["copied"]], [1, 2, 3])
            vision.assert_not_called()

    def test_image_vision_uses_shared_quota_route_and_actual_model(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "original.png"
            with mock.patch.object(worker.shutil, "which", return_value="codex"), \
                    mock.patch("wechat_codex_sessions.run_codex_across_accounts", return_value={
                        "ok": True, "message": "Three original images.", "returncode": 0,
                        "model": "gpt-5.6-luna", "quota_pool": "reserve"}) as run:
                result = worker.codex_read_image_file(path, Path(folder), additional_images=(path, path))
            self.assertEqual(len(run.call_args.kwargs["image_paths"]), 3)
            self.assertEqual(result["model"], "gpt-5.6-luna")
            self.assertEqual(result["quota_pool"], "reserve")
            self.assertEqual(Path(result["text_path"]).read_text().strip(), "Three original images.")

    def test_album_waits_for_exact_members_but_never_retries_wrong_identity(self):
        group = groups.combined_image_group(xml())
        first = {"combined_image": group}
        task = {"source": {"server_id": "101"}}
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(images, "recover_image", side_effect=lambda *a: dict(first)), \
                mock.patch("wechat_tiny11_bridge.load_config", return_value={}), \
                mock.patch.object(images.time, "sleep") as wait, \
                mock.patch.object(images, "image_group_tasks", side_effect=[
                    ValueError("combined_image_members_incomplete"),
                    [{"source": {"server_id": "101"}}],
                ]) as members:
            images.recover_images(task, Path(folder))
            self.assertEqual(members.call_count, 2)
            wait.assert_called_once_with(0.25)
            members.reset_mock(side_effect=True)
            members.side_effect = ValueError("image_group_identity_mismatch")
            wait.reset_mock()
            with self.assertRaisesRegex(ValueError, "identity_mismatch"):
                images.recover_images(task, Path(folder))
            wait.assert_not_called()
            members.assert_called_once()

    def test_exact_media_resolution_preserves_only_answer_context(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "original.png"
            Image.new("RGB", (20, 30)).save(path)
            task = {"chat": "LightMind", "source": {"kind": "image", "local_type": 3}}
            context_task = {**task, "context": [{"kind": "text", "local_type": 1,
                                                "content": "Could this product succeed?"}]}
            with mock.patch.object(worker, "uses_tiny11_wechat", return_value=True), \
                    mock.patch.object(images, "recover_images", return_value=[{"mirror_path": str(path)}]) as recover, \
                    mock.patch.object(worker, "enrich_media_resolution_copies_with_image_read") as vision, \
                    mock.patch.object(worker, "enrich_copies_with_document_read"):
                worker.prepare_media_resolution_preflight(task, root, image_context_task=context_task)
            self.assertIs(recover.call_args.args[0], task)
            self.assertIs(vision.call_args.kwargs["task"], context_task)

    def test_corrected_image_intake_defers_answer_to_resumed_agent(self):
        import wechat_task_worker as worker
        task = {"route_decision": {"route_kind": "file_intake"},
                "source": {"kind": "image", "local_type": 3},
                "reprocess_reason": "Read the complete album and answer the follow-up.",
                "preflight": {"file_intake": {"copied": [{"suffix": ".png",
                    "vision": {"status": "ok", "text_preview": "An old caption."}}]}}}
        self.assertIsNone(worker.deterministic_file_intake_result(task))
        self.assertIn("Read the complete album", worker.image_read_prompt_context(task))

    def test_group_vision_uses_the_same_chat_workspace_boundary(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workspace = root / "output" / "chat_workspaces" / "group-one"
            output = workspace / "tasks" / "image-one" / "image_text"
            with mock.patch.object(worker, "ROOT", root), \
                    mock.patch.object(worker.shutil, "which", return_value="codex"), \
                    mock.patch("wechat_codex_sessions.run_codex_across_accounts", return_value={
                        "ok": True, "message": "Read this group's original."}) as run:
                worker.codex_read_image_file(workspace / "image.png", output)
            self.assertEqual(run.call_args.kwargs["workdir"], workspace)
            self.assertEqual(run.call_args.kwargs["sandbox"], "read-only")
