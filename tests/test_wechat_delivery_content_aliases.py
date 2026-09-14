import importlib
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"))
worker = importlib.import_module("wechat_task_worker")


class DeliveryContentAliasTests(unittest.TestCase):
    def test_duplicate_names_collapse_but_edits_and_other_formats_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, renamed, edited, different_format = [root / name for name in (
                "original.mp4", "readable-title.mp4", "edited.mp4", "same-bytes.txt",
            )]
            for path in (original, renamed, different_format):
                path.write_bytes(b"video")
            edited.write_bytes(b"other")
            task = {}
            selected = worker.unique_delivery_files(
                [original, renamed, original, edited, different_format], task,
            )
            self.assertEqual(selected, [original, edited, different_format])
            self.assertEqual(worker.verified_delivery_alias(renamed, task), original)
            self.assertEqual(worker.unique_delivery_files(selected, task), selected)
            # A stale alias cannot vouch for a changed file.
            renamed.write_bytes(b"new-video")
            self.assertEqual(worker.verified_delivery_alias(renamed, task), renamed)

    def test_one_receipt_satisfies_all_identical_required_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = [Path(tmp) / name for name in ("first.mp4", "second.mp4")]
            first.write_bytes(b"exact-video")
            second.write_bytes(first.read_bytes())
            task = {"sent_file_paths": [str(first)]}
            result = {"files": [str(first), str(second)]}
            self.assertEqual(worker.required_delivery_file_paths(result, task), [first])
            self.assertTrue(worker.required_file_delivery_complete(task, result))

    def test_missing_path_is_preserved_for_normal_failure_reporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.mp4"
            self.assertEqual(worker.unique_delivery_files([missing], {}), [missing])


if __name__ == "__main__":
    unittest.main()
