from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from agenticapp import cli
from agenticapp import protein_structure_ops as protein


class ProteinStructureOpsTests(unittest.TestCase):
    def test_cli_registers_thin_protein_commands(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["protein", "render", "backbones", "--json"])

        self.assertEqual(args.protein_command, "render")
        self.assertEqual(args.kind, "backbones")
        self.assertTrue(args.json)

    def test_status_reports_persistent_profile_and_visible_novnc(self) -> None:
        with mock.patch.object(
            protein,
            "_probe_json",
            side_effect=[{"Browser": "Chrome/test"}, [{"type": "page", "title": "AlphaFold", "url": "https://alphafoldserver.com/"}]],
        ), mock.patch.object(protein, "_probe_url", return_value=True), mock.patch.object(
            protein, "_tmux_ready", return_value=True
        ):
            payload = protein.browser_status(Path("/tmp/protein-workspace"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile"], str(Path.home() / ".cache" / "alphafold-server-chrome"))
        self.assertIn("resize=scale", payload["novnc_url"])
        self.assertEqual(payload["pages"][0]["title"], "AlphaFold")

    def test_submit_delegates_to_existing_submodule_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fasta = Path(tmp) / "target.fasta"
            fasta.write_text(">target\nACDEFG\n", encoding="utf-8")
            script_root = Path(tmp) / "alphafold_server"
            script_root.mkdir()
            submit_script = script_root / "submit_jobs.py"
            submit_script.write_text("# test fixture\n", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout="validated\n", stderr="")
            args = argparse.Namespace(
                workspace=tmp,
                json=True,
                fastas=[str(fasta)],
                dry_run=True,
                log="",
            )
            with mock.patch.object(protein, "SCRIPT_ROOT", script_root), mock.patch.object(
                protein, "_ensure_layout"
            ), mock.patch.object(
                protein.subprocess, "run", return_value=completed
            ) as runner, mock.patch("builtins.print"):
                result = protein.cmd_submit(args)

        self.assertEqual(result, 0)
        command = runner.call_args.args[0]
        self.assertEqual(Path(command[1]), submit_script)
        self.assertIn(str(fasta.resolve()), command)
        self.assertIn("--dry-run", command)
        self.assertEqual(runner.call_args.kwargs["cwd"], Path(tmp).resolve())

    def test_source_gitignore_keeps_outputs_local(self) -> None:
        if not (protein.SOURCE_ROOT / ".gitignore").is_file():
            self.skipTest("private ProteinStructure submodule is not initialized")
        content = (protein.SOURCE_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("/alphafold-results/", content)
        self.assertIn("/publication/**/*.pdf", content)
        self.assertIn("/publication/**/figures/", content)
        self.assertIn("*_full_data_*.json", content)

    def test_runbook_points_into_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "ProteinStructure"
            runbook = source_root / "references" / "alphafold_server_jobs" / "browser_automation_runbook.md"
            runbook.parent.mkdir(parents=True)
            runbook.write_text("# Runbook\n", encoding="utf-8")
            args = argparse.Namespace(workspace=str(protein.DEFAULT_WORKSPACE), json=True)
            with mock.patch.object(protein, "SOURCE_ROOT", source_root), mock.patch(
                "builtins.print"
            ) as printer:
                result = protein.cmd_runbook(args)

        self.assertEqual(result, 0)
        payload = json.loads(printer.call_args.args[0])
        self.assertEqual(payload["runbook"], str(runbook))


if __name__ == "__main__":
    unittest.main()
