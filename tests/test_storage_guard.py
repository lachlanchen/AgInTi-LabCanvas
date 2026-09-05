import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/labcanvas_storage_guard.py"
spec = importlib.util.spec_from_file_location("labcanvas_storage_guard_test", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class StorageGuardTests(unittest.TestCase):
    def test_mount_selection_and_escaped_spaces(self):
        mounts = "1 0 8:1 / / rw - ext4 root rw\n2 1 252:3 / /home/user/My\\040Projects rw - ext4 projects rw\n"
        self.assertEqual(guard.mount_for("/home/user/My Projects/repo", mounts)["device"], "252:3")
        self.assertEqual(guard.mount_for("/home/user/My ProjectsOther/repo", mounts)["device"], "8:1")

    def test_controller_traverses_lvm_slaves_and_partition_parents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            controller = root / "pci/nvme/nvme1"
            partition = controller / "nvme1n1/nvme1n1p2"
            partition.mkdir(parents=True)
            (controller / "state").write_text("dead\n")
            dm = root / "virtual/block/dm-3/slaves"
            dm.mkdir(parents=True)
            (dm / "nvme1n1p2").symlink_to(partition)
            dev = root / "dev"
            dev.mkdir()
            (dev / "252:3").symlink_to(dm.parent)
            self.assertEqual(guard.controller_states("252:3", dev), {"nvme1": "dead"})

    def test_missing_mount_does_not_probe_project(self):
        config = {"root": "/projects/app", "mountpoint": "/projects", "state_dir": "/home/state"}
        with patch.object(Path, "read_text", return_value="1 0 8:1 / / rw - ext4 root rw\n"):
            with patch.object(guard, "controller_states") as controllers:
                result = guard.probe(config)
                self.assertEqual(result["reason"], "required_mount_missing")
                controllers.assert_not_called()

    def test_dead_controller_short_circuits_project_reads_and_writes(self):
        mounts = "1 0 8:1 / / rw - ext4 root rw\n2 1 252:3 / /projects rw - ext4 projects rw\n"
        config = {"root": "/projects/app", "mountpoint": "/projects", "state_dir": "/home/state"}
        with patch.object(Path, "read_text", return_value=mounts), patch.object(
            guard, "controller_states", return_value={"nvme1": "dead"}
        ), patch.object(tempfile, "mkstemp") as create:
            result = guard.probe(config)
            self.assertFalse(result["ok"])
            self.assertTrue(result["latch"])
            create.assert_not_called()

    def test_same_volume_state_rejected(self):
        mounts = "1 0 8:1 / / rw - ext4 root rw\n"
        with patch.object(Path, "read_text", return_value=mounts):
            self.assertEqual(guard.probe({"root": "/app", "mountpoint": "/", "state_dir": "/state"})["reason"],
                             "guard_state_on_project_volume")

    def test_outage_is_not_cleared_by_restart_or_healthy_probe(self):
        outage = guard.evaluate({}, {"ok": False, "reason": "io", "latch": True})
        reloaded = json.loads(json.dumps(outage))
        result = guard.evaluate(reloaded, {"ok": True, "reason": "storage_ready"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "recovery_review_required")

    def test_acknowledgement_requires_healthy_storage(self):
        old = {"recovery_review_required": True}
        self.assertFalse(guard.evaluate(old, {"ok": False, "reason": "io", "latch": True}, True)["ok"])
        self.assertTrue(guard.evaluate(old, {"ok": True, "reason": "storage_ready"}, True)["ok"])

    def test_temporary_missing_mount_recovers_without_resetting_task_data(self):
        old = guard.evaluate({}, {"ok": False, "reason": "required_mount_missing", "latch": False})
        self.assertTrue(guard.evaluate(old, {"ok": True, "reason": "storage_ready"})["ok"])

    def test_timeout_retains_identity_and_does_not_spawn_again(self):
        process = unittest.mock.Mock(pid=42)
        process.communicate.side_effect = subprocess.TimeoutExpired("probe", 1)
        with patch.object(subprocess, "Popen", return_value=process), patch.object(guard, "pid_identity", return_value="123"):
            result = guard.bounded_probe(Path("/config"), {}, 1)
            self.assertEqual(result["reason"], "storage_probe_timeout")
            process.kill.assert_called_once()
        with patch.object(subprocess, "Popen") as spawn, patch.object(guard, "pid_identity", return_value="123"):
            result = guard.bounded_probe(Path("/config"), result, 1)
            self.assertEqual(result["reason"], "previous_probe_still_running")
            spawn.assert_not_called()

    def test_malformed_probe_fails_closed(self):
        process = unittest.mock.Mock(pid=42)
        process.communicate.return_value = ("[]", "")
        with patch.object(subprocess, "Popen", return_value=process), patch.object(guard, "pid_identity", return_value="123"):
            self.assertFalse(guard.bounded_probe(Path("/config"), {}, 1)["ok"])

    def test_private_atomic_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            guard.atomic_json(path, {"ok": False})
            guard.atomic_json(path, {"ok": True})
            self.assertTrue(json.loads(path.read_text())["ok"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(folder).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
