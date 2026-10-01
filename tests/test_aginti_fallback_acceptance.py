import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_aginti_fallback.py"
SPEC = importlib.util.spec_from_file_location("aginti_fallback_acceptance", SCRIPT)
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class AgintiFallbackAcceptanceTests(unittest.TestCase):
    def test_default_invocation_does_not_spend_quota(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("No inference performed", result.stderr)

    def test_existing_payload_parser_accepts_fenced_json(self):
        result = {"message": '```json\n{"message":"ready","files":["artifacts/scene.json"]}\n```'}
        self.assertEqual(acceptance.result_files(result), {"scene.json"})
        with self.assertRaisesRegex(AssertionError, "usable JSON"):
            acceptance.result_payload({"message": "I probably made a file"})

    def test_pdf_overflow_cannot_pass_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(acceptance.subprocess, "run", return_value=subprocess.CompletedProcess(
                "xelatex", 0, "Overfull \\hbox (100pt too wide)", "",
            )) as run:
                with self.assertRaisesRegex(AssertionError, "clipped/overflowing"):
                    acceptance.compile_memo(Path(tmp), "memo")
            self.assertEqual(run.call_count, 1)
            self.assertIn("-no-shell-escape", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
