from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_shipinhao_comment_intel():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "shipinhao_comment_intel.py"
    spec = importlib.util.spec_from_file_location("shipinhao_comment_intel_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ShipinhaoCommentIntelTests(unittest.TestCase):
    def test_summary_detects_yuanbao_hits_in_comments_and_replies(self) -> None:
        module = load_shipinhao_comment_intel()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "comments.json"
            path.write_text(
                json.dumps(
                    {
                        "objectId": "oid",
                        "objectNonceId": "nonce",
                        "title": "demo video",
                        "author": "demo author",
                        "source": "finderGetCommentList",
                        "commentInfo": [
                            {
                                "commentId": "c1",
                                "nickname": "A",
                                "content": "@元宝 这个视频的英文全文",
                                "likeCount": 3,
                                "levelTwoComment": [
                                    {
                                        "commentId": "r1",
                                        "nickname": "B",
                                        "content": "summary please",
                                        "likeCount": 7,
                                    }
                                ],
                            },
                            {
                                "commentId": "c2",
                                "nickname": "C",
                                "content": "普通评论",
                                "likeCount": 10,
                                "levelTwoComment": [],
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = module.summarize_comment_payload(module.load_json(path), source_path=path, keywords=module.DEFAULT_KEYWORDS)

        self.assertEqual(summary["comment_count"], 3)
        self.assertEqual(summary["source_quality"], "comment_hits")
        hit_text = "\n".join(item["content"] for item in summary["keyword_hits"])
        self.assertIn("@元宝", hit_text)
        self.assertIn("summary please", hit_text)
        self.assertEqual(summary["high_signal_comments"][0]["content"], "普通评论")

    def test_markdown_reports_no_hits_without_overclaiming(self) -> None:
        module = load_shipinhao_comment_intel()
        summary = module.summarize_comment_payload(
            {"commentInfo": [{"content": "just a normal comment", "likeCount": 1}]},
            source_path=Path("/tmp/comments.json"),
            keywords=module.DEFAULT_KEYWORDS,
        )

        rendered = module.render_markdown(summary)

        self.assertEqual(summary["source_quality"], "comments_available")
        self.assertIn("No matching Yuanbao", rendered)
        self.assertIn("no Yuanbao/transcript request was found", rendered)


if __name__ == "__main__":
    unittest.main()
