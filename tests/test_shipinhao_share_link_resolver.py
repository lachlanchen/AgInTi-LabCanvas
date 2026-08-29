from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "shipinhao_share_link_resolver.py"
    spec = importlib.util.spec_from_file_location("shipinhao_share_link_resolver_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShipinhaoShareLinkResolverTests(unittest.TestCase):
    def test_extracts_only_canonical_weixin_sph_links(self) -> None:
        module = load_module()

        links = module.extract_share_urls(
            "first https://weixin.qq.com/sph/Ae2UMH6gqr?foo=private "
            "again https://weixin.qq.com/sph/Ae2UMH6gqr and https://example.com/sph/wrong"
        )

        self.assertEqual(links, ["https://weixin.qq.com/sph/Ae2UMH6gqr"])

    def test_provider_config_is_parse_only_and_private(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "config.yaml"
            module.write_provider_config(path, run_dir, "secret-cookie", api_port=25001, proxy_port=25002)
            text = path.read_text(encoding="utf-8")
            mode = path.stat().st_mode & 0o777

        self.assertEqual(mode, 0o600)
        self.assertIn("enabled: false", text)
        self.assertIn("system: false", text)
        self.assertIn("tun: false", text)
        self.assertIn("skipInstallRootCert: true", text)
        self.assertNotIn("tun: true", text)

    def test_normalizes_exact_profile_and_prefers_h264(self) -> None:
        module = load_module()
        payload = {
            "code": 0,
            "data": {
                "data": {
                    "errCode": 0,
                    "authorInfo": {"nickname": "Hui世界"},
                    "feedInfo": {
                        "description": "美国最后的边疆阿拉斯加",
                        "mediaType": 4,
                        "coverUrl": "https://finder.video.qq.com/cover",
                        "h264VideoInfo": {"videoUrl": "https://finder.video.qq.com/h264?signed=1"},
                        "h265VideoInfo": {"videoUrl": "https://finder.video.qq.com/h265?signed=1"},
                    },
                }
            },
        }

        result = module.normalize_provider_result(
            payload,
            canonical_url="https://weixin.qq.com/sph/Ae2UMH6gqr",
            token="Ae2UMH6gqr",
        )

        self.assertEqual(result["object_id"], "sph-Ae2UMH6gqr")
        self.assertEqual(result["author"], "Hui世界")
        self.assertEqual(result["title"], "美国最后的边疆阿拉斯加")
        self.assertEqual(result["media_urls"], ["https://finder.video.qq.com/h264?signed=1"])
        self.assertTrue(result["content_identity_verified"])
        self.assertNotIn("media_urls", module.safe_result(result))

    def test_resolver_refuses_root_or_active_tun_before_starting_provider(self) -> None:
        module = load_module()
        with mock.patch.object(module.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(module.ShareLinkResolutionError, "must not run as root"):
                module.resolve_share_link("https://weixin.qq.com/sph/Ae2UMH6gqr")

        with (
            mock.patch.object(module.os, "geteuid", return_value=1000),
            mock.patch.object(module.Path, "exists", autospec=True, return_value=True),
        ):
            with self.assertRaisesRegex(module.ShareLinkResolutionError, "tun0"):
                module.resolve_share_link("https://weixin.qq.com/sph/Ae2UMH6gqr")


if __name__ == "__main__":
    unittest.main()
