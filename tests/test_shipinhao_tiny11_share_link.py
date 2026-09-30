import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agentic_tools/wechat_gui_agent/scripts"))
native = importlib.import_module("shipinhao_tiny11_share_link")
resolver = importlib.import_module("shipinhao_share_link_resolver")


class NativeChannelsLinkTests(unittest.TestCase):
    @staticmethod
    def identity_profiles(title, author):
        card = native.extract_shipinhao_media_profile(
            "<finderFeed><objectId>123</objectId>"
            f"<desc><![CDATA[{title}]]></desc>"
            f"<nickname><![CDATA[{author}]]></nickname></finderFeed>"
        )
        resolved = resolver.normalize_provider_result(
            {"data": {
                "feedInfo": {"description": title, "videoUrl": "https://finder.video.qq.com/video"},
                "authorInfo": {"nickname": author},
            }},
            canonical_url="https://weixin.qq.com/sph/ABcd123",
            token="ABcd123",
        )
        return card, resolved

    def test_copied_link_matches_full_long_card_identity(self):
        for size in (299, 300, 301, 1200):
            with self.subTest(title_length=size):
                title = "a" * size + " #ai episode 2"
                author = "author" * 30 + " studio"
                card, resolved = self.identity_profiles(title, author)
                self.assertEqual(card["title"], title)
                self.assertEqual(card["author"], author)
                with mock.patch.object(native, "resolve_sph_share_profile", return_value=resolved):
                    result = native.verify_resolved_card(card, "https://weixin.qq.com/sph/ABcd123")
                self.assertEqual(card["object_id"], "123")
                self.assertTrue(result["content_identity_verified"])
                self.assertEqual(result["title"], title)
                self.assertEqual(result["author"], author)

    def test_shared_long_prefix_cannot_hide_different_title_or_author(self):
        for field, prefix_length in (("title", 300), ("author", 160)):
            with self.subTest(field=field):
                title = "a" * 300 + " episode 1"
                author = "a" * 160 + " studio 1"
                card, _ = self.identity_profiles(title, author)
                other = {"title": title, "author": author}
                other[field] = "a" * prefix_length + " different 2"
                _, resolved = self.identity_profiles(**other)
                with mock.patch.object(native, "resolve_sph_share_profile", return_value=resolved):
                    with self.assertRaisesRegex(ValueError, f"native_link_resolved_{field}_mismatch"):
                        native.verify_resolved_card(card, "https://weixin.qq.com/sph/ABcd123")

    def test_resolved_link_requires_full_title_and_author_not_fuzzy_ocr(self):
        profile = {'object_id': '123', 'title': 'Poem title', 'author': 'Author'}
        resolved = {**profile, 'share_token': 'ABcd123'}
        with mock.patch.object(native, 'resolve_sph_share_profile', return_value=resolved):
            self.assertEqual(native.verify_resolved_card(profile, 'https://weixin.qq.com/sph/ABcd123')['title'], 'Poem title')
            for field in ('title', 'author'):
                for value in ('', 'Another'):
                    changed = {**profile, field: value}
                    with self.assertRaisesRegex(ValueError, 'mismatch'):
                        native.verify_resolved_card(changed, 'https://weixin.qq.com/sph/ABcd123')

    def test_exact_title_normalizes_punctuation_not_episode_or_glyph(self):
        title = "外星人访谈第53集：无尽长廊和无限的饼。"
        self.assertTrue(native.exact_player_title(title, title.replace("：", ": ")))
        self.assertFalse(native.exact_player_title(title, title.replace("53", "54")))
        self.assertFalse(native.exact_player_title(title, title.replace("星", "旦")))
        self.assertFalse(native.exact_player_title("", title))

    def test_second_ocr_mode_must_still_match_exactly(self):
        bridge = mock.Mock()
        bridge.ocr_scaled.side_effect = ["another episode", "Exact episode 53"]
        self.assertTrue(native.verify_player_title(bridge, Path("crop.png"), "Exact episode 53"))
        self.assertEqual([call.kwargs["psm"] for call in bridge.ocr_scaled.call_args_list], [6, 11])
        bridge.ocr_scaled.side_effect = ["Exact episode 54", "Exact episode 54"]
        self.assertFalse(native.verify_player_title(bridge, Path("crop.png"), "Exact episode 53"))

    def test_clipboard_waits_for_async_native_copy(self):
        bridge = mock.Mock()
        bridge.get_clipboard.side_effect = ["marker", "marker", "https://weixin.qq.com/sph/ABcd123"]
        with mock.patch.object(native.time, "sleep"):
            self.assertEqual(native.wait_copied_link(bridge, "marker"), "https://weixin.qq.com/sph/ABcd123")

    def test_clipboard_marker_or_multiple_links_never_passes(self):
        for value in ("marker", "https://weixin.qq.com/sph/ABcd123 https://weixin.qq.com/sph/EFgh456"):
            bridge = mock.Mock()
            bridge.get_clipboard.return_value = value
            with mock.patch.object(native.time, "monotonic", side_effect=[0, 1, 8]), \
                    mock.patch.object(native.time, "sleep"), \
                    self.assertRaisesRegex(RuntimeError, "clipboard_unavailable"):
                native.wait_copied_link(bridge, "marker", timeout=6)

    def test_native_centered_thumbnail_variants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cover = root / "cover.jpg"
            Image.new("RGB", (720, 405), "red").save(cover)
            sizes = []

            def candidates(screen, crop, **kwargs):
                with Image.open(crop) as image:
                    sizes.append(image.size)
                self.assertEqual(kwargs["min_confidence"], .8)
                return [{"match_confidence": .8 + len(sizes) / 100}]

            with mock.patch.object(native, "exact_cover_candidates", side_effect=candidates):
                result = native.card_candidates(cover, cover, {}, root)
            self.assertEqual(sizes, [(720, 405), (540, 405), (304, 405)])
            self.assertGreater(result[0]["match_confidence"], result[-1]["match_confidence"])

    def test_player_detection_requires_native_dark_right_pane(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.png"
            image = Image.new("RGB", (2560, 1440), "white")
            window = SimpleNamespace(x=1284, y=0, width=1276, height=1392)
            image.save(path)
            self.assertIsNone(native.player_box(path, window))
            image.paste((0, 0, 0), (2114, 80, 2560, 1392))
            image.save(path)
            box = native.player_box(path, window)
            self.assertEqual(box[0], 2114)
            self.assertTrue(300 <= box[2] <= 650)
            self.assertIsNone(native.player_box(path, SimpleNamespace(x=0, y=1400, width=835, height=900)))
            image.paste((255, 255, 255), (2114, 80, 2560, 1392))
            image.paste((218, 218, 223), (2110, 80, 2114, 1392))
            image.save(path)
            self.assertEqual(native.player_box(path, window)[0], 2114)

    def test_menu_icon_ocr_does_not_require_fuzzy_action_match(self):
        bridge = mock.Mock()
        bridge.crop.side_effect = [Path('menu.png'), Path('text.png')]
        bridge.find_ocr_line.side_effect = [None, None, {'similarity': 1, 'center_x': 30, 'center_y': 20}]
        with mock.patch.object(native, 'menu_panel_boxes', return_value=[]):
            point = native.match_menu(bridge, Path('screen'), (400, 200, 165, 260), ['Silent Play'], Path('/tmp'), 'menu')
        self.assertEqual(point, (459, 220))

    def test_popup_isolated_from_caption_and_video_background(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'menu.png'
            image = Image.new('RGB', (440, 320), 'black')
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((190, 98, 302, 237), radius=8, fill=(239, 239, 239))
            draw.text((201, 110), 'Copy Link', fill='black')
            draw.text((15, 272), 'Caption behind menu', fill='white')
            image.save(path)
            try:
                import cv2  # noqa: F401
            except ImportError:
                self.skipTest('native GUI optional dependency')
            self.assertEqual(native.menu_panel_boxes(path), [(190, 98, 113, 140)])
            bridge = mock.Mock()
            bridge.crop.side_effect = [path, root / 'panel.png']
            bridge.find_ocr_line.return_value = {'similarity': 1, 'center_x': 40, 'center_y': 117}
            self.assertEqual(native.match_menu(bridge, path, (2100, 1000, 440, 320),
                                              ['Copy Link'], root, 'menu'), (2330, 1215))

    def test_owned_tab_close_uses_only_unique_small_header_cross(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.skipTest('native GUI optional dependency')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'header.png'
            image = Image.new('RGB', (800, 300), 'white')
            draw = ImageDraw.Draw(image)
            # App close button must never be considered.
            draw.line((780, 5, 789, 14), fill='black')
            draw.line((789, 5, 780, 14), fill='black')
            draw.line((528, 50, 537, 59), fill='black')
            draw.line((537, 50, 528, 59), fill='black')
            image.save(path)
            window = SimpleNamespace(x=0, y=0)
            self.assertEqual(native.player_tab_close_point(path, window, (300, 80, 440, 220)), (533, 55))
            draw.line((428, 50, 437, 59), fill='black')
            draw.line((437, 50, 428, 59), fill='black')
            image.save(path)
            self.assertIsNone(native.player_tab_close_point(path, window, (300, 80, 440, 220)))

    def test_cleanup_verifies_owned_pane_disappears(self):
        bridge = mock.Mock()
        window = SimpleNamespace(x=1000, y=0)
        with mock.patch.object(native, 'player_tab_close_point', return_value=(2000, 55)), \
                mock.patch.object(native, 'player_box', return_value=(1900, 80, 400, 1200)), \
                mock.patch.object(native.time, 'sleep'), \
                self.assertRaisesRegex(RuntimeError, 'close_not_confirmed'):
            native.close_owned_player(bridge, window, (1900, 80, 400, 1200))
        self.assertEqual(bridge.click.call_args_list, [mock.call(1300, 40), mock.call(2000, 55)])

    def test_cleanup_checks_new_window_bounds_after_dock_shrinks(self):
        bridge = mock.Mock()
        old_window = SimpleNamespace(x=1000, y=0, width=1280)
        new_window = SimpleNamespace(x=1000, y=0, width=835)
        bridge.find_window.return_value = new_window
        with mock.patch.object(native, 'player_tab_close_point', return_value=(2000, 55)), \
                mock.patch.object(native, 'player_box', return_value=None) as detect, \
                mock.patch.object(native.time, 'sleep'):
            native.close_owned_player(bridge, old_window, (1900, 80, 400, 1200))
        self.assertIs(detect.call_args.args[1], new_window)

    def test_copied_link_survives_cleanup_failure_but_not_identity_mismatch(self):
        from contextlib import ExitStack
        import json

        for mismatch in (False, True):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as folder, ExitStack() as patches:
                root = Path(folder)
                (root / '1234').mkdir()
                Image.new('RGB', (30, 30)).save(root / '1234/card-cover.jpg')
                bridge = mock.MagicMock()
                bridge.tiny11.health.return_value = {'ok': True}
                window = SimpleNamespace(x=1000, y=0, width=1280, height=1392)
                bridge.ensure_chat.return_value = window
                bridge.find_window.return_value = window
                bridge.history_surface.return_value = (1300, 100, 600, 900)
                bridge.set_clipboard.side_effect = lambda text: setattr(bridge.get_clipboard, 'return_value', text)
                profile = {'object_id': '1234', 'title': 'Exact title', 'author': 'Author'}
                patches.enter_context(mock.patch.object(native, 'DEFAULT_CACHE_ROOT', root))
                patches.enter_context(mock.patch.object(native, 'extract_shipinhao_media_profile', return_value=profile))
                patches.enter_context(mock.patch.dict(sys.modules, {'cv2': mock.Mock()}))
                patches.enter_context(mock.patch.object(native.time, 'sleep'))
                patches.enter_context(mock.patch.object(native, 'player_box', side_effect=[None] + [(1900, 80, 400, 1200)] * 3))
                patches.enter_context(mock.patch.object(native, 'card_candidates', return_value=[{'center_x': 80, 'center_y': 80, 'match_confidence': .99}]))
                patches.enter_context(mock.patch.object(native, 'match_menu', return_value=(1400, 200)))
                patches.enter_context(mock.patch.object(native, 'verify_player_title', return_value=True))
                patches.enter_context(mock.patch.object(native, 'wait_copied_link', return_value='https://weixin.qq.com/sph/ABcd123'))
                patches.enter_context(mock.patch.object(native, 'close_owned_player', side_effect=RuntimeError('native_owned_tab_close_not_confirmed')))
                verify = patches.enter_context(mock.patch.object(native, 'verify_resolved_card', return_value=profile))
                if mismatch:
                    verify.side_effect = ValueError('native_link_resolved_title_mismatch')
                    with self.assertRaisesRegex(ValueError, 'title_mismatch'):
                        native.recover('Shares', 'source', root / 'run', bridge=bridge)
                    self.assertFalse((root / 'run/native-share-link.json').exists())
                else:
                    result = native.recover('Shares', 'source', root / 'run', bridge=bridge)
                    self.assertTrue(result['content_identity_verified'])
                    self.assertIn('cleanup_warning', result)
                    self.assertEqual(json.loads((root / 'run/native-share-link.json').read_text()), result)
                candidate = json.loads((root / 'run/native-share-candidate.json').read_text())
                self.assertFalse(candidate['content_identity_verified'])
                self.assertEqual(candidate['status'], 'identity_pending')

    def test_pending_candidate_retries_resolver_without_reopening_client(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = {'object_id': '1234', 'title': 'Exact title', 'author': 'Author'}
            candidate = {**profile, 'source_chat': 'Shares', 'status': 'identity_pending',
                         'content_identity_verified': False, 'share_url': 'https://weixin.qq.com/sph/ABcd123'}
            (root / 'native-share-candidate.json').write_text(json.dumps(candidate))
            bridge = mock.MagicMock()
            with mock.patch.object(native, 'extract_shipinhao_media_profile', return_value=profile), \
                    mock.patch.object(native, 'verify_resolved_card', side_effect=RuntimeError('resolver unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'resolver unavailable'):
                    native.recover('Shares', 'source', root, bridge=bridge)
            self.assertFalse((root / 'native-share-link.json').exists())
            with mock.patch.object(native, 'extract_shipinhao_media_profile', return_value=profile), \
                    mock.patch.object(native, 'verify_resolved_card', return_value=profile):
                result = native.recover('Shares', 'source', root, bridge=bridge)
            self.assertTrue(result['content_identity_verified'])
            self.assertTrue(result['reused'])
            bridge.serialized_gui.assert_not_called()

    def test_missing_card_identity_never_operates_gui(self):
        bridge = mock.Mock()
        with self.assertRaisesRegex(ValueError, "identity_missing"):
            native.recover("Shares", "not a native card", Path("unused"), bridge=bridge)
        bridge.serialized_gui.assert_not_called()

    def test_preserves_existing_player_without_clicking_or_dismissing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "1234").mkdir()
            Image.new("RGB", (30, 30)).save(root / "1234/card-cover.jpg")
            bridge = mock.MagicMock()
            with mock.patch.object(native, "DEFAULT_CACHE_ROOT", root), \
                    mock.patch.object(native, "extract_shipinhao_media_profile", return_value={"object_id": "1234", "title": "Exact title"}), \
                    mock.patch.object(native, "player_box", return_value=(2100, 80, 440, 1200)), \
                    mock.patch.dict(sys.modules, {"cv2": mock.Mock()}), \
                    self.assertRaisesRegex(RuntimeError, "already_open_preserve_user_tab"):
                native.recover("Shares", "source", root / "run", bridge=bridge)
            bridge.click.assert_not_called()
            bridge.right_click.assert_not_called()
            bridge.dismiss_transient_overlays.assert_not_called()


if __name__ == "__main__":
    unittest.main()
