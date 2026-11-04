from contextlib import ExitStack
import hashlib
from io import BytesIO
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
import wechat_linux_image as images
import wechat_direct_chatops as direct
import wechat_task_worker as worker


def image_bytes(size, fmt="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return buffer.getvalue()


class LinuxImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.decrypted = self.root / "decrypted"
        (self.decrypted / "message").mkdir(parents=True)
        self.account = self.root / "wxid_owner_1234"
        self.chatroom = "exact-chat@chatroom"
        self.table = "Msg_" + hashlib.md5(self.chatroom.encode()).hexdigest()
        self.shard = self.decrypted / "message/message_1.db"
        self.resource_db = self.decrypted / "message/message_resource.db"
        self.token = "a" * 32
        self.attach = self.account / "msg/attach" / self.table[4:] / "2026-11/Img"
        self.attach.mkdir(parents=True)
        self.original = image_bytes((780, 3084))
        self.dat = self.attach / (self.token + ".dat")
        self.dat.write_bytes(bytes(byte ^ 0x88 for byte in self.original))
        (self.attach / (self.token + "_t.dat")).write_bytes(
            bytes(byte ^ 0x88 for byte in image_bytes((117, 210))))
        self.config_id = "shares.json"
        (self.private / self.config_id).write_text(json.dumps({
            "chat_name": "Shares", "chatroom_id": self.chatroom,
            "message_table": self.table, "self_wxid": "wxid_owner",
        }))
        decoder = self.private / "external/wechat-decrypt/config.json"
        decoder.parent.mkdir(parents=True)
        decoder.write_text(json.dumps({"db_dir": str(self.account / "db_storage"),
                                       "decrypted_dir": str(self.decrypted)}))
        self.task = {"id": "exact-image", "chat": "Shares", "source": {
            "chat": "Shares", "kind": "image", "local_type": 3,
            "config_id": self.config_id, "message_table": self.table,
            "message_db": self.shard.name, "local_id": 652,
            "server_id": "12345", "create_time": 100,
        }}
        with sqlite3.connect(self.shard) as conn:
            conn.execute(f'CREATE TABLE "{self.table}" (local_id, server_id, create_time, local_type)')
            conn.execute(f'INSERT INTO "{self.table}" VALUES (652,12345,100,3)')
        with sqlite3.connect(self.resource_db) as conn:
            conn.executescript('''CREATE TABLE ChatName2Id(user_name);
                CREATE TABLE MessageResourceInfo(chat_id, message_local_id, message_svr_id,
                    message_create_time, message_local_type, packed_info);''')
            conn.execute('INSERT INTO ChatName2Id VALUES (?)', (self.chatroom,))
            conn.execute('INSERT INTO MessageResourceInfo VALUES (1,652,12345,100,3,?)',
                         (b"\x12\x22\x0a\x20" + self.token.encode(),))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(images, "PRIVATE", self.private))
        self.stack.enter_context(mock.patch.object(direct, "DECRYPTED", self.decrypted))

    def test_original_uses_exact_resource_not_xml_digest_or_thumbnail(self):
        self.task["request"] = 'md5: ' + "b" * 32
        result = images.recover_images(self.task, self.root / "output")[0]
        path = Path(result["source_path"])
        self.assertEqual(path.read_bytes(), self.original)
        self.assertEqual((result["width"], result["height"]), (780, 3084))
        self.assertTrue(result["original_resolution_verified"])
        self.assertEqual(result["matched_by"], "native-image-exact-message-resource")
        manifest = json.loads(Path(result["metadata"]["export_manifest"]).read_text())
        self.assertFalse(manifest["resized"])
        self.assertEqual(manifest["resource_token"], self.token)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_original_never_substitutes_existing_thumbnail(self):
        self.dat.unlink()
        with self.assertRaisesRegex(ValueError, "exact_full_image_not_cached"):
            images.recover_images(self.task, self.root / "output")

    def test_message_chat_account_shard_and_time_are_all_verified(self):
        for change in ({"server_id": "999"}, {"local_id": 653}, {"create_time": 101},
                       {"chat": "Other"}, {"message_table": "Msg_" + "c" * 32},
                       {"message_db": "../message_1.db"}, {"message_db": "message_999998.db"}):
            with self.subTest(change=change), self.assertRaises((ValueError, sqlite3.Error)):
                images.native_request({**self.task, "source": {**self.task["source"], **change}})
        config = self.private / self.config_id
        config.write_text(config.read_text().replace("wxid_owner", "wxid_other"))
        with self.assertRaisesRegex(ValueError, "image_account_identity_mismatch"):
            images.native_request(self.task)

    def test_resource_rejects_ambiguous_loose_hash_and_other_chat_mapping(self):
        for blob in (b"a" * 32, b"\x12\x22\x0a\x20" + b"a" * 32
                     + b"\x12\x22\x0a\x20" + b"b" * 32):
            with sqlite3.connect(self.resource_db) as conn:
                conn.execute('UPDATE MessageResourceInfo SET packed_info=?', (blob,))
            with self.assertRaisesRegex(ValueError, "image_resource_identity_ambiguous"):
                images.native_request(self.task)
        with sqlite3.connect(self.resource_db) as conn:
            conn.execute('UPDATE ChatName2Id SET user_name="other-chat"')
        with self.assertRaisesRegex(ValueError, "image_resource_identity_unavailable"):
            images.native_request(self.task)

    def test_symlink_escape_is_rejected(self):
        self.dat.unlink()
        target = self.root / "elsewhere.dat"
        target.write_bytes(self.original)
        self.dat.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "image_cache_path_escape"):
            images.recover_images(self.task, self.root / "output")

    def test_worker_native_recovery_bypasses_generic_mirror_and_gui_clicks(self):
        output = self.root / "output"
        output.mkdir()
        with mock.patch.object(worker, "uses_tiny11_wechat", return_value=False), \
                mock.patch.object(worker, "refresh_media_sync_for_task") as sync, \
                mock.patch.object(worker, "resolve_synced_media_from_mirror") as mirror, \
                mock.patch.object(worker, "materialize_chat_for_media_cache") as gui, \
                mock.patch.object(worker, "enrich_media_resolution_copies_with_image_read"), \
                mock.patch.object(worker, "enrich_copies_with_document_read"):
            result = worker.prepare_media_resolution_preflight(self.task, output)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["refresh"]["transport"], "wechat_linux_image")
            self.assertEqual(len(result["copied"]), 1)
            self.dat.unlink()
            result = worker.prepare_media_resolution_preflight(self.task, output)
            self.assertEqual(result["status"], "missing")
            self.assertIn("exact_full_image_not_cached", result["refresh"]["reason"])
            sync.assert_not_called()
            mirror.assert_not_called()
            gui.assert_not_called()

    def test_coalesced_images_remain_ordered_complete_and_deduplicated(self):
        earlier = {**self.task["source"], "local_id": 650, "server_id": "12343", "create_time": 98,
                   "role": "coalesced_source"}
        task = {**self.task, "message_ledger": [earlier, {**self.task["source"], "role": "coalesced_source"}]}
        with mock.patch.object(images, "recover_image", side_effect=lambda task, out: {
                "source_server_id": task["source"]["server_id"], "original_resolution_verified": True}):
            result = images.recover_images(task, self.root / "output")
        self.assertEqual([item["source_server_id"] for item in result], ["12343", "12345"])
        self.assertEqual([item["album_index"] for item in result], [1, 2])
        self.assertTrue(all(item["album_count"] == 2 for item in result))

    def test_wxgf_container_is_retained_and_decoded_without_resizing(self):
        payload = b"wxgf-exact-native-container"
        def decode(source, target):
            self.assertEqual(source.read_bytes(), payload)
            Image.new("RGB", (800, 1600), "white").save(target)
            return 800, 1600
        with mock.patch.object(images, "decode_wechat_v_container", return_value=("wxgf", payload)), \
                mock.patch.object(images, "decode_wxgf", side_effect=decode):
            result = images.recover_images(self.task, self.root / "output")[0]
        self.assertEqual((result["width"], result["height"]), (800, 1600))
        self.assertEqual(Path(result["source_path"]).with_suffix(".wxgf").read_bytes(), payload)

    def test_profile_key_recovery_is_validated_cached_and_private(self):
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
        except ModuleNotFoundError:
            self.skipTest("pycryptodome not installed")
        import struct
        xor = 0x44
        code = str((1 << 8) | xor)
        account = self.root / ("wxid_owner_" + hashlib.md5(code.encode()).hexdigest()[:4])
        key = hashlib.md5((code + "wxid_owner").encode()).hexdigest()[:16].encode()
        dat = account / "image.dat"
        account.mkdir()
        def container(payload):
            encrypted = AES.new(key, AES.MODE_ECB).encrypt(pad(payload[:32], 16))
            return V2 + struct.pack("<LL", 32, len(payload) - 45) + b"\0" + encrypted + payload[32:45] + bytes(b ^ xor for b in payload[45:])
        V2 = images.V2
        dat.write_bytes(container(image_bytes((100, 200), "JPEG")))
        dat.with_name("image_t.dat").write_bytes(container(image_bytes((20, 40), "JPEG")))
        with mock.patch.object(images, "image_decode_keys", return_value=(b"wrong-key-123456", 0)):
            self.assertEqual(images.profile_keys(account, dat), (key, xor))
        cache = next((self.private / "image_keys").glob("*.json"))
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        with mock.patch.object(images, "derive_profile_key", side_effect=AssertionError("must use verified cache")):
            self.assertEqual(images.profile_keys(account, dat), (key, xor))

    def test_unread_original_is_not_misdiagnosed_as_low_resolution(self):
        task = {"route_decision": {"route_kind": "file_intake"}, "source": {"kind": "image"},
                "preflight": {"file_intake": {"copied": [{
                    "suffix": ".png", "original_resolution_verified": True,
                    "vision": {"status": "failed"}, "ocr": {"status": "empty"},
                }]}}}
        self.assertIsNone(worker.deterministic_file_intake_result(task))
        self.assertNotIn("缩略图", worker.image_intake_description_message({}))

    def test_vision_default_uses_shared_model_policy_and_original_file(self):
        # The shared runner resolves AgentShell/pinned installs even when the
        # service's PATH lacks the interactive Codex command.
        with mock.patch.object(worker.shutil, "which", return_value=None), \
                mock.patch.dict(worker.os.environ, {}, clear=True), \
                mock.patch.object(worker, "load_worker_model_policy", return_value={"model": "current-vision-model"}), \
                mock.patch("wechat_codex_sessions.run_codex_across_accounts", return_value={
                    "ok": True, "message": "Useful image summary.", "returncode": 0}) as agent:
            worker.codex_read_image_file(self.dat, self.root / "vision")
        self.assertEqual(agent.call_args.kwargs["model"], "current-vision-model")
        self.assertEqual(agent.call_args.kwargs["image_paths"], (self.dat,))


if __name__ == "__main__":
    unittest.main()
