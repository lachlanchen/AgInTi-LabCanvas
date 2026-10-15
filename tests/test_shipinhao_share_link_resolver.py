from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
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
    def test_authenticated_flow_stops_before_feed_on_auth_failure(self) -> None:
        module = load_module()
        for payload in ({"code": 401}, {"code": 1, "msg": "not logged in"}):
            with self.subTest(payload=payload), mock.patch.object(
                module, "request_resolver_json", return_value=payload,
            ) as request:
                with self.assertRaises(module.ShareLinkResolutionError) as caught:
                    module.resolve_authenticated_share("https://weixin.qq.com/sph/ABcd123", "ABcd123", "secret", timeout=5)
                self.assertEqual(caught.exception.error_code, "yuanbao_login_required")
                request.assert_called_once()

    def test_http_401_is_login_blocker_not_playback_failure(self) -> None:
        module = load_module()
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError("private", 401, "Unauthorized", {}, io.BytesIO(b"secret"))
        with mock.patch.object(module.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(module.ShareLinkResolutionError) as caught:
                module.request_resolver_json("https://yuanbao.tencent.com/api/weixin/get_parse_result", {},
                                             timeout=5, cookie="secret", referer="https://yuanbao.tencent.com/", stage="yuanbao_parse")
        self.assertEqual(caught.exception.error_code, "yuanbao_login_required")
        self.assertNotIn("secret", str(caught.exception))

    def test_unusable_parse_never_calls_feed_with_empty_identity(self) -> None:
        module = load_module()
        for playable in ("", "https://example.org/?eid=x&token=y", "https://channels.weixin.qq.com/?eid=x"):
            with self.subTest(playable=playable), mock.patch.object(module, "request_resolver_json", return_value={
                "code": 0, "data": {"playable_url": playable},
            }) as request:
                with self.assertRaises(module.ShareLinkResolutionError) as caught:
                    module.resolve_authenticated_share("https://weixin.qq.com/sph/ABcd123", "ABcd123", "secret", timeout=5)
                self.assertEqual(caught.exception.error_code, "yuanbao_playback_identity_missing")
                request.assert_called_once()

    def test_authenticated_flow_preserves_identity_and_separates_cookies(self) -> None:
        module = load_module()
        with mock.patch.object(module, "request_resolver_json", side_effect=[
            {"code": 0, "data": {"playable_url": "https://channels.weixin.qq.com/finder-preview/pages/feed?token=abc&eid=def"}},
            {"errCode": 0, "data": {"errMsg": {"type": 0}, "feedInfo": {"description": "Exact title", "videoUrl": "https://finder.video.qq.com/source"},
                                   "authorInfo": {"nickname": "Exact author"}}},
        ]) as request:
            result = module.resolve_authenticated_share("https://weixin.qq.com/sph/ABcd123", "ABcd123", "secret", timeout=5)
        self.assertEqual(result["title"], "Exact title")
        self.assertEqual(result["author"], "Exact author")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].kwargs["cookie"], "secret")
        self.assertNotIn("cookie", request.call_args_list[1].kwargs)
        self.assertEqual(request.call_args_list[1].args[1], {"baseReq": {"generalToken": "abc"}, "exportId": "def"})

    def test_upstream_feed_error_is_not_silently_ignored(self) -> None:
        module = load_module()
        for payload in ({"errCode": 123, "data": {}}, {"errCode": 0, "data": {"errMsg": {"type": 1}}}):
            with self.subTest(payload=payload), self.assertRaises(module.ShareLinkResolutionError):
                module.normalize_provider_result(payload, canonical_url="https://weixin.qq.com/sph/ABcd123", token="ABcd123")

    def test_redirect_cannot_forward_authentication(self) -> None:
        module = load_module()
        self.assertIsNone(module.NoResolverRedirect().redirect_request(None, None, 302, "", {}, "https://other.test/"))

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

    def test_long_identity_fields_are_whitespace_normalized_not_truncated(self) -> None:
        module = load_module()
        title = "An example caption " * 40 + "\n\t #ai episode 2"
        author = "Example " * 30 + "\n Studio"
        result = module.normalize_provider_result(
            {"data": {
                "feedInfo": {"description": title, "videoUrl": "https://finder.video.qq.com/video"},
                "authorInfo": {"nickname": author},
            }},
            canonical_url="https://weixin.qq.com/sph/ABcd123",
            token="ABcd123",
        )
        self.assertEqual(result["title"], " ".join(title.split()))
        self.assertEqual(result["author"], " ".join(author.split()))


if __name__ == "__main__":
    unittest.main()
