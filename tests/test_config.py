import unittest

from agenticapp.config import parse_config


class ConfigTests(unittest.TestCase):
    def test_parse_targets(self):
        config = parse_config(
            {
                "targets": [
                    {
                        "name": "blender",
                        "kind": "blender",
                        "transport": {"type": "noop"},
                    }
                ]
            }
        )

        self.assertEqual(config.get_target("blender").kind, "blender")

    def test_rejects_duplicate_targets(self):
        with self.assertRaises(ValueError):
            parse_config(
                {
                    "targets": [
                        {"name": "unity", "kind": "unity"},
                        {"name": "unity", "kind": "unity"},
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
