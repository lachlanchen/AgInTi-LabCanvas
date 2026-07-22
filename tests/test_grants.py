from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agenticapp import grants


class GrantWorkspaceTests(unittest.TestCase):
    def test_initialize_is_durable_and_refreshes_current_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "grant"
            first = grants.initialize_grant_workspace(
                project,
                title="Organoid Imaging",
                objective="Draft the initial specific aims.",
                task_id="grant-1",
                chat="LabAgent",
            )
            created_at = first["goal"]["created_at"]

            second = grants.initialize_grant_workspace(
                project,
                title="Organoid Imaging",
                objective="Revise the aims around vascular validation.",
                task_id="grant-1",
                chat="LabAgent",
            )
            request = (project / "current_request.md").read_text(encoding="utf-8")
            prompt = (project / "agent_goal_prompt.md").read_text(encoding="utf-8")

        self.assertEqual(second["goal"]["created_at"], created_at)
        self.assertIn("vascular validation", request)
        self.assertIn("create_goal", prompt)
        self.assertIn("update_goal", prompt)
        self.assertIn("Do not submit", prompt)

    def test_empty_workspace_fails_completion_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "grant"
            grants.initialize_grant_workspace(
                project,
                title="Test Grant",
                objective="Create a proposal.",
            )

            result = grants.validate_grant_workspace(project)

        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["proposal_markdown"])
        self.assertFalse(result["checks"]["source_manifest"])
        self.assertFalse(result["checks"]["figure_manifest"])

    def test_complete_workspace_passes_evidence_and_editability_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "grant"
            grants.initialize_grant_workspace(
                project,
                title="Test Grant",
                objective="Create a proposal.",
            )
            (project / "proposal.md").write_text("# Proposal\n\n" + "Evidence-grounded aim. " * 30, encoding="utf-8")
            (project / "proposal.tex").write_text("\\documentclass{article}\n" + "% validated source\n" * 30, encoding="utf-8")
            (project / "proposal.pdf").write_bytes(b"%PDF-1.4\n" + b"validated proposal " * 4)
            (project / "references.bib").write_text(
                "@article{verified, title={Verified source}, doi={10.1000/example}}\n",
                encoding="utf-8",
            )
            (project / "sources" / "source_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sources": [{"title": "Verified source", "doi": "10.1000/example"}],
                    }
                ),
                encoding="utf-8",
            )
            overview = project / "figures" / "renders" / "overview.png"
            overview.write_bytes(b"checked editable figure preview")
            assembly = project / "figures" / "figure_assembly.tex"
            assembly.write_text("\\begin{picture}(10,10) editable assembly \\end{picture}\n", encoding="utf-8")
            part = project / "figures" / "parts" / "device.svg"
            part.write_text("<svg><rect width='10' height='10'/></svg>\n", encoding="utf-8")
            (project / "figures" / "figure_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "editable": True,
                        "overview": "figures/renders/overview.png",
                        "assembly_source": "figures/figure_assembly.tex",
                        "parts": [{"id": "device", "source": "figures/parts/device.svg"}],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(grants, "_pdf_text_readable", return_value=True):
                result = grants.validate_grant_workspace(project)

        self.assertTrue(result["ok"])
        self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()
