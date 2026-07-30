from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from agenticapp.feedback_ops import (
    FeedbackTarget,
    resolve_target,
    sanitize_text,
    write_feedback_report,
)


class FeedbackOpsTests(unittest.TestCase):
    def target_registry(self, root: Path) -> dict[str, FeedbackTarget]:
        return {
            "lazyedit": FeedbackTarget(
                id="lazyedit",
                title="LazyEdit",
                root=root,
            )
        }

    def payload(self) -> dict[str, object]:
        return {
            "target": "lazyedit",
            "kind": "bug",
            "title": "QR artifact is not exposed to the caller",
            "summary": "A verified publish login blocker has no reusable QR artifact.",
            "expected": "The caller can retrieve the current job-scoped QR image.",
            "observed": "Only an email notification is available.",
            "evidence": ["Reproduced through the local publish status endpoint."],
            "acceptance": ["Expose one current job-scoped QR artifact without duplicate sends."],
            "verified": True,
        }

    def test_write_is_idempotent_and_revisions_change_only_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = self.target_registry(root)
            first = write_feedback_report(
                self.payload(),
                registry=registry,
                now=datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc),
            )
            second = write_feedback_report(
                self.payload(),
                registry=registry,
                now=datetime(2026, 7, 30, 2, 0, tzinfo=timezone.utc),
            )
            changed_payload = self.payload()
            changed_payload["workaround"] = "Read the email notification."
            third = write_feedback_report(
                changed_payload,
                registry=registry,
                now=datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc),
            )

            self.assertTrue(first["created"])
            self.assertFalse(second["changed"])
            self.assertEqual(first["path"], second["path"])
            self.assertEqual(second["revision"], 1)
            self.assertTrue(third["changed"])
            self.assertEqual(third["revision"], 2)
            report = Path(third["path"]).read_text(encoding="utf-8")
            self.assertIn("Current Workaround", report)
            self.assertIn("Read the email notification.", report)

    def test_report_redacts_transport_ids_secrets_paths_and_signed_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.payload()
            payload["observed"] = (
                "password=plain wxid_private chat_id=abc123 "
                f"{Path.home()}/private/log.txt "
                "https://example.test/qr.png?token=secret&expires=123"
            )
            result = write_feedback_report(
                payload,
                registry=self.target_registry(root),
            )
            report = Path(result["path"]).read_text(encoding="utf-8")

            self.assertNotIn("plain", report)
            self.assertNotIn("wxid_private", report)
            self.assertNotIn(str(Path.home()), report)
            self.assertNotIn("token=secret", report)
            self.assertIn("<redacted>", report)
            self.assertIn("<private-chat-id>", report)
            self.assertIn("<HOME>", report)

    def test_unknown_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                resolve_target(
                    "arbitrary-repo",
                    registry=self.target_registry(Path(tmp)),
                )

    def test_sanitize_text_does_not_strip_normal_public_url(self) -> None:
        value = "See https://example.test/docs?section=api for the public contract."

        self.assertEqual(sanitize_text(value), value)


if __name__ == "__main__":
    unittest.main()
