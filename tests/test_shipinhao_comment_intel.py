from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


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


def load_shipinhao_native_capture():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "shipinhao_native_capture.py"
    spec = importlib.util.spec_from_file_location("shipinhao_native_capture_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ShipinhaoCommentIntelTests(unittest.TestCase):
    def test_local_api_reads_paginated_comments_and_replies_without_export_path(self) -> None:
        module = load_shipinhao_comment_intel()
        top_page = {
            "code": 0,
            "data": {
                "errCode": 0,
                "data": {
                    "commentInfo": [
                        {
                            "commentId": "c1",
                            "nickname": "Reader",
                            "content": "Main comment",
                            "expandCommentCount": 1,
                            "levelTwoComment": [],
                        }
                    ],
                    "countInfo": {"commentCount": 1},
                    "lastBuffer": "",
                },
            },
        }
        reply_page = {
            "code": 0,
            "data": {
                "data": {
                    "commentInfo": [{"commentId": "r1", "nickname": "Yuanbao", "content": "summary text"}],
                    "lastBuffer": "",
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                api_url="http://127.0.0.1:2026",
                object_id="object-1",
                nonce_id="nonce-1",
                title="Demo",
                author="Creator",
                max_pages=4,
                max_reply_pages=2,
                json_out=Path(tmp) / "summary.json",
                markdown_out=None,
            )
            with mock.patch.object(module, "api_get_json", side_effect=[top_page, reply_page]) as get_json:
                path = module.fetch_comments_from_list_api(args)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(get_json.call_count, 2)
        self.assertEqual(payload["source"], "wx_channel:/api/channels/feed/comment/list")
        self.assertEqual(payload["commentInfo"][0]["levelTwoComment"][0]["content"], "summary text")

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

    def test_native_capture_plan_is_read_only(self) -> None:
        module = load_shipinhao_native_capture()

        plan = module.build_plan(output_dir=Path("/tmp/shipinhao-capture"), display=":97", scrolls=3, lang="chi_sim+eng")

        self.assertTrue(plan["read_only"])
        self.assertFalse(plan["public_actions"])
        self.assertIn("OCR", " ".join(plan["steps"]))
        self.assertIn("No likes", " ".join(plan["non_goals"]))


if __name__ == "__main__":
    unittest.main()
