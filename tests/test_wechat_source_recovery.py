from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]


def load_recovery():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_source_recovery.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("wechat_source_recovery_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatSourceRecoveryTests(unittest.TestCase):
    def test_parser_extracts_article_body_without_footer(self) -> None:
        recovery = load_recovery()
        article = recovery.parse_wechat_article(
            """
            <html><head><meta property="og:title" content="A useful article"></head>
            <body><span id="js_name">Lab Account</span><span id="publish_time">2026-07-15</span>
            <div id="js_content"><p>First claim.</p><p>Second claim.</p>
            <img data-src="https://mmbiz.qpic.cn/example.jpg" alt="Figure 1"></div>
            <footer>This is not article content.</footer></body></html>
            """
        )

        self.assertEqual(article.title, "A useful article")
        self.assertEqual(article.author, "Lab Account")
        self.assertIn("First claim.", article.body)
        self.assertIn("Second claim.", article.body)
        self.assertNotIn("not article content", article.body)
        self.assertEqual(article.image_urls, ["https://mmbiz.qpic.cn/example.jpg"])

    def test_gate_detection_and_captcha_target_unwrap(self) -> None:
        recovery = load_recovery()
        target = "https://mp.weixin.qq.com/s?__biz=abc&mid=123&idx=1&sn=deadbeef"
        wrapped = "https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?target_url=" + quote(target, safe="")

        self.assertTrue(recovery.detect_verification_gate("环境异常，完成验证后继续访问"))
        self.assertEqual(recovery.normalize_wechat_article_url(wrapped), target)

    def test_script_only_verification_page_is_not_a_post(self):
        recovery = load_recovery()
        self.assertTrue(recovery.detect_verification_gate("var PAGE_MID='mmbizwap:secitptpage/verify.html';"))

    def test_short_post_is_not_rejected_by_character_count(self):
        recovery = load_recovery()
        html = '<h1 id="activity-name">Short post</h1><div id="js_content"><p>A useful short observation.</p></div>'
        response = {'status': 200, 'bytes': len(html), 'final_url': 'https://mp.weixin.qq.com/s/short', 'text': html}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(recovery, 'fetch_html', return_value=response):
            result = recovery.recover_mp_weixin_article('https://mp.weixin.qq.com/s/short', Path(tmp)/'out', cache_dir=Path(tmp)/'cache')
            self.assertEqual(result['source_quality'], 'full_article')
            self.assertIn('A useful short observation', Path(result['markdown_path']).read_text())

    def test_js_image_post_preserves_text_and_ordered_images_without_execution(self):
        recovery = load_recovery()
        html = r'''<script>window.cgiDataNew = {content_noencode: JsDecode('<p>Useful \'quoted\' text.</p>')};
        window.picture_page_info_list = [{cdn_url: 'https://mmbiz.qpic.cn/first?x=1\x26amp;y=2'},
          {"cdn_url": "https://mmbiz.qpic.cn/second"}].slice(0,20);</script>'''
        article = recovery.parse_wechat_article(html)
        self.assertIn("Useful 'quoted' text.", article.body)
        self.assertEqual(article.image_urls, ['https://mmbiz.qpic.cn/first?x=1&y=2', 'https://mmbiz.qpic.cn/second'])
        self.assertTrue(article.content_present)
        self.assertEqual(recovery.extract_js_literal("content_noencode: dangerousCall()", 'content_noencode'), '')

    def test_mixed_post_exposes_embedded_media_not_just_a_title(self):
        recovery = load_recovery()
        article = recovery.parse_wechat_article('<div id="js_content"><audio src="https://example.com/voice.mp3"></audio><video src="https://example.com/video.mp4"></video></div>')
        self.assertEqual([x['kind'] for x in article.media_urls], ['audio', 'video'])
        self.assertTrue(article.content_present)

    def test_native_image_card_survives_article_gate_without_claiming_all_pages(self):
        recovery = load_recovery()
        url = 'https://mp.weixin.qq.com/s?__biz=b&mid=1&idx=1&sn=one'
        card = f'''<appmsg><title>Image post</title><url><![CDATA[{url}]]></url><sourcedisplayname>Author</sourcedisplayname>
        <mmreadershare><itemshowtype>8</itemshowtype><piccount>9</piccount><firstimageinfo><cdn_url>https://mmbiz.qpic.cn/original</cdn_url></firstimageinfo></mmreadershare></appmsg>'''
        response = {'status': 200, 'bytes': 100, 'final_url': url, 'text': 'secitptpage/verify'}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(recovery, 'fetch_html', return_value=response), \
                mock.patch('wechat_post_assets.download_post_images', return_value=[{'status': 'ready', 'path': '/private/original.jpg'}]) as download:
            result = recovery.recover_task_sources({'request': card}, Path(tmp), cache_dir=Path(tmp)/'cache')
            source = result['articles'][0]
            self.assertEqual(source['source_quality'], 'partial_post')
            self.assertEqual(source['page_coverage'], {'expected': 9, 'available': 1, 'complete': False})
            self.assertEqual(download.call_args.args[0], ['https://mmbiz.qpic.cn/original'])
            self.assertTrue(Path(source['agent_context_path']).is_file())
            self.assertEqual(result['status'], 'partial')

    def test_multiple_native_cards_keep_their_own_title_author_and_images(self):
        recovery = load_recovery()
        cards = ''.join(f'<appmsg><title>{name}</title><url>https://mp.weixin.qq.com/s/{name}</url><sourcedisplayname>{name} author</sourcedisplayname></appmsg>' for name in ('first','second'))
        response = {'status': 200, 'bytes': 1, 'final_url': '', 'text': 'secitptpage/verify'}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(recovery, 'fetch_html', return_value=response):
            result = recovery.recover_task_sources({'request': cards}, Path(tmp), cache_dir=Path(tmp)/'cache')
        self.assertEqual([x['title'] for x in result['articles']], ['first','second'])
        self.assertEqual([x['author'] for x in result['articles']], ['first author','second author'])

    def test_task_source_scope_ignores_old_history_url(self) -> None:
        recovery = load_recovery()
        current = "https://mp.weixin.qq.com/s/current-token"
        old = "https://mp.weixin.qq.com/s/old-token"
        task = {
            "request": (
                f"Current coalesced request:\nPlease read {current}\n\n"
                f"Recent history:\nold source {old}"
            )
        }

        self.assertEqual(recovery.extract_mp_weixin_urls(recovery.task_source_text(task)), [current])

    def test_sources_beyond_preflight_budget_are_explicitly_pending(self):
        recovery = load_recovery()
        urls = [f"https://mp.weixin.qq.com/s/post-{index}" for index in range(4)]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            recovery, "recover_mp_weixin_article", return_value={"source_quality": "full_article"}
        ) as recover:
            result = recovery.recover_task_sources({"request": "\n".join(urls)}, Path(tmp))
        self.assertEqual(recover.call_count, 3)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["deferred_sources"][0]["url"], urls[-1])
        self.assertIn(urls[-1], recovery.render_recovery_manifest(result))

    def test_image_only_html_post_does_not_require_native_type_metadata(self):
        recovery = load_recovery()
        html = '<div id="js_content"><img data-src="https://mmbiz.qpic.cn/original"></div>'
        response = {"status": 200, "bytes": len(html), "final_url": "", "text": html}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(recovery, "fetch_html", return_value=response), \
                mock.patch("wechat_post_assets.download_post_images", return_value=[{"status": "ready", "path": "/private/page.jpg"}]):
            result = recovery.recover_mp_weixin_article(
                "https://mp.weixin.qq.com/s/image", Path(tmp) / "post", cache_dir=Path(tmp) / "cache"
            )
        self.assertEqual(result["content_kind"], "image_post")
        self.assertTrue(result["page_coverage"]["complete"])

    def test_task_source_scope_ignores_compacted_history_article_cards(self) -> None:
        recovery = load_recovery()
        task = {
            "request": (
                "Prepare today's scheduled scholarly briefing.\n\n"
                "Model-budgeted lifetime memory from the complete exact-group history, followed\n"
                "by raw excerpts selected for this research lane:\n"
                "# Lifetime memory compaction\n"
                "- old correction: 公众号文章卡片 "
                "<title>Chat History for sunnyyty的聊天记录</title>"
            )
        }

        source_text = recovery.task_source_text(task)
        self.assertEqual(source_text, "Prepare today's scheduled scholarly briefing.")
        self.assertFalse(recovery.task_needs_source_recovery(task))
        self.assertEqual(recovery.extract_article_card_profile(source_text)["title"], "")

    def test_task_source_scope_includes_explicit_reference_section(self) -> None:
        recovery = load_recovery()
        referenced = "https://mp.weixin.qq.com/s/referenced-token"
        task = {
            "request": (
                "Current coalesced request:\nPlease read that article\n\n"
                "Recent history:\nunrelated text\n\n"
                f"Same-chat reference media/context rows:\n- local_id=41 content={referenced}\n\n"
                "Automatic media sync:\n(not run)"
            )
        }

        self.assertEqual(recovery.extract_mp_weixin_urls(recovery.task_source_text(task)), [referenced])

    def test_exact_file_link_row_excludes_older_coalesced_source_references(self) -> None:
        recovery = load_recovery()
        current = "https://mp.weixin.qq.com/s/current-token"
        old = "https://mp.weixin.qq.com/s/old-token"
        task = {
            "source": {"local_id": 44, "kind": "file/link"},
            "request": (
                "Current coalesced request:\nHandle this source. Finder and Shipinhao are supported.\n\n"
                f"Same-chat reference media/context rows:\n- local_id=41 content={old}\n\n"
                "Automatic media sync:\n(not run)"
            ),
            "context": [
                {"local_id": 41, "kind": "file/link", "content": f"old {old} <finderFeed></finderFeed>"},
                {"local_id": 44, "kind": "file/link", "content": f"current {current}"},
            ],
        }

        source_text = recovery.task_source_text(task)
        self.assertEqual(recovery.extract_mp_weixin_urls(source_text), [current])
        self.assertNotIn("finderFeed", source_text)
        self.assertFalse(recovery.build_shipinhao_recovery_packet(source_text)["detected"])

    def test_article_urls_deduplicate_tracking_variants_by_identity(self) -> None:
        recovery = load_recovery()
        first = "https://mp.weixin.qq.com/s?__biz=biz&mid=123&idx=1&sn=abc&scene=1"
        second = "https://mp.weixin.qq.com/s?__biz=biz&mid=123&idx=1&sn=abc&mpshare=1"

        self.assertEqual(recovery.extract_mp_weixin_urls(first + "\n" + second), [first])

    def test_recover_article_uses_wechat_fetch_and_private_cache(self) -> None:
        recovery = load_recovery()
        html = """
        <html><head><meta property="og:title" content="Recovered"></head><body>
        <span id="js_name">Account</span><div id="js_content"><p>{}</p></div>
        </body></html>
        """.format("substantive article sentence " * 20)
        response = {"status": 200, "bytes": len(html), "final_url": "https://mp.weixin.qq.com/s/demo", "text": html}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(recovery, "fetch_html", return_value=response) as fetch:
                result = recovery.recover_mp_weixin_article(
                    "https://mp.weixin.qq.com/s/demo",
                    root / "first",
                    cache_dir=root / "cache",
                )
            with mock.patch.object(recovery, "fetch_html", side_effect=AssertionError("cache should be used")):
                cached = recovery.recover_mp_weixin_article(
                    "https://mp.weixin.qq.com/s/demo",
                    root / "second",
                    cache_dir=root / "cache",
                )

        self.assertEqual(result["source_quality"], "full_article")
        self.assertEqual(fetch.call_args.kwargs["user_agent"], recovery.WECHAT_USER_AGENT)
        self.assertTrue(cached["cache_hit"])
        self.assertTrue(cached["verification_requested"] is False)

    def test_card_only_article_emits_exact_title_reconstruction_queries(self) -> None:
        recovery = load_recovery()
        title = "第一次，我们看到了高自由度灵巧手的另一种可能。"
        task = {
            "request": f"公众号文章卡片\n<title>{title}</title>",
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = recovery.recover_task_sources(task, Path(tmp))

        self.assertEqual(result["status"], "reconstruction_required")
        self.assertEqual(result["articles"][0]["source_quality"], "card_metadata")
        self.assertEqual(result["articles"][0]["title"], title)
        self.assertIn(f'"{title}"', result["articles"][0]["recovery_queries"])

    def test_shipinhao_packet_keeps_exact_card_identity(self) -> None:
        recovery = load_recovery()
        packet = recovery.build_shipinhao_recovery_packet(
            """
            <finderFeed><objectId><![CDATA[123456789]]></objectId>
            <objectNonceId><![CDATA[nonce-123456]]></objectNonceId>
            <nickname><![CDATA[Creator]]></nickname><desc><![CDATA[Video subject]]></desc></finderFeed>
            """
        )

        self.assertTrue(packet["detected"])
        self.assertEqual(packet["object_id"], "123456789")
        self.assertEqual(packet["title"], "Video subject")
        self.assertIn('"Video subject" "Creator"', packet["recovery_queries"])
        self.assertFalse(packet["write_actions_allowed"])


if __name__ == "__main__":
    unittest.main()
