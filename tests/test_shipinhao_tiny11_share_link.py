import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agentic_tools/wechat_gui_agent/scripts"))
native = importlib.import_module("shipinhao_tiny11_share_link")


class NativeChannelsLinkTests(unittest.TestCase):
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
        point = native.match_menu(bridge, Path('screen'), (400, 200, 165, 260), ['Silent Play'], Path('/tmp'), 'menu')
        self.assertEqual(point, (459, 220))

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
