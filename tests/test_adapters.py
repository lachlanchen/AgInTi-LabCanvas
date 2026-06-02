import json
import sys
import unittest

from agenticapp.adapters import dispatch_target
from agenticapp.config import Target


class AdapterTests(unittest.TestCase):
    def test_dry_run_returns_envelope(self):
        target = Target(name="blender", kind="blender", transport={"type": "http_json", "url": "http://localhost"})
        result = dispatch_target(target, "Create a cube", dry_run=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "dry-run")
        self.assertEqual(result.response["target"], "blender")
        self.assertEqual(result.response["instruction"], "Create a cube")

    def test_local_command_receives_json(self):
        target = Target(
            name="echo",
            kind="test",
            transport={
                "type": "local_command",
                "command": [
                    sys.executable,
                    "-c",
                    "import json,sys; data=json.load(sys.stdin); print(json.dumps({'instruction': data['instruction']}))",
                ],
            },
        )

        result = dispatch_target(target, "Round trip")

        self.assertTrue(result.ok)
        self.assertEqual(result.response["returncode"], 0)
        self.assertEqual(result.response["stdout"], {"instruction": "Round trip"})

    def test_payload_must_be_object_in_envelope(self):
        target = Target(name="noop", kind="test", transport={"type": "noop"})
        result = dispatch_target(target, "Use payload", payload={"asset": "cube"})

        self.assertEqual(json.dumps(result.response["payload"], sort_keys=True), '{"asset": "cube"}')


if __name__ == "__main__":
    unittest.main()
