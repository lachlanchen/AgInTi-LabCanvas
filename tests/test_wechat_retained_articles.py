from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from wechat_retained_articles import retained_article_evidence


class RetainedArticlesTests(unittest.TestCase):
    def test_exact_current_sources_only_and_no_silent_batch_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(5):
                folder = root / "articles" / str(index)
                folder.mkdir(parents=True)
                (folder / "meta.json").write_text(json.dumps({
                    "url": f"https://mp.weixin.qq.com/s?sn=source{index}",
                    "title": f"Source {index}",
                }))
                (folder / "article.html").write_text(
                    '<div id="js_content">' + f"Source {index} text. " * 30 + "</div>"
                )
            items = [{"item_id": str(i), "text": f"https://mp.weixin.qq.com/s?sn=source{i}"} for i in range(4)]
            evidence = retained_article_evidence(root, items)
            self.assertEqual([x["item_ids"] for x in evidence], [[str(i)] for i in range(4)])
            self.assertTrue(all(x["quality"] == "full_article" for x in evidence))
            self.assertNotIn("Source 4", str(evidence))
            self.assertEqual(retained_article_evidence(root, items, max_chars=100), [])
            (root / "articles/3/article.html").unlink()
            self.assertEqual(retained_article_evidence(root, items), [])

    def test_metadata_stays_metadata_and_unrelated_requests_do_not_enter_summary_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "articles" / "card"
            folder.mkdir(parents=True)
            (folder / "meta.json").write_text(json.dumps({"url": "https://mp.weixin.qq.com/s?sn=card", "title": "Card"}))
            (folder / "article.html").write_text("<html>Preview only</html>")
            items = [{"item_id": "card", "text": "https://mp.weixin.qq.com/s?sn=card"}]
            self.assertEqual(retained_article_evidence(root, items)[0]["quality"], "card_metadata")
            self.assertEqual(retained_article_evidence(root, items + [{"text": "Also manufacture this device"}]), [])


if __name__ == "__main__":
    unittest.main()
