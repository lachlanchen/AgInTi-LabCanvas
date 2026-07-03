from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_backfill():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_image_backfill.py"
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("wechat_image_backfill_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatImageBackfillTests(unittest.TestCase):
    def test_select_recent_image_rows_excludes_self_and_keeps_order(self) -> None:
        backfill = load_backfill()
        config = {"self_wxid": "bot"}
        rows = [
            {"local_id": 1, "local_type": 1, "sender": "alice"},
            {"local_id": 2, "local_type": 3, "sender": "alice"},
            {"local_id": 3, "local_type": 3, "sender": "bot"},
            {"local_id": 4, "local_type": 3, "sender": "bob"},
            {"local_id": 5, "local_type": 3, "sender": "carol"},
        ]

        selected = backfill.select_recent_image_rows(config, rows, limit=2)

        self.assertEqual([row["local_id"] for row in selected], [4, 5])

    def test_best_image_candidate_prefers_original_over_thumbnail(self) -> None:
        backfill = load_backfill()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "msg" / "attach" / "chat" / "2026-07" / "Img" / "abc123.jpg"
            thumb = root / "cache" / "2026-07" / "Message" / "chat" / "Thumb" / "abc123_thumb.jpg"
            original.parent.mkdir(parents=True)
            thumb.parent.mkdir(parents=True)
            original.write_bytes(b"original")
            thumb.write_bytes(b"thumbnail-but-larger" * 20)

            candidate = backfill.best_image_candidate(
                [
                    {"mirror_path": str(thumb), "suffix": ".jpg", "score": 100, "size_bytes": thumb.stat().st_size},
                    {"mirror_path": str(original), "suffix": ".jpg", "score": 100, "size_bytes": original.stat().st_size},
                ]
            )

        self.assertEqual(Path(candidate["mirror_path"]).name, "abc123.jpg")


if __name__ == "__main__":
    unittest.main()
