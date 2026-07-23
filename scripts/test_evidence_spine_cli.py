import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit_manuscript import run_audit
from evidence_spine import prepare_evidence_spine, record_pass


class EvidenceSpineCliTests(unittest.TestCase):
    def test_finalize_cli_runs_after_all_helpers_are_defined(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manuscript = root / "cli.md"
            manuscript.write_text(
                """Abstract
A self-centering (SC) frame was tested. SC remained stable.

Introduction
A self-centering (SC) frame was analyzed. The self-centering frame remained stable.
""",
                encoding="utf-8",
            )
            audit_dir = root / "audit"
            run_audit(manuscript, audit_dir)
            prepared = prepare_evidence_spine(
                manuscript,
                root / "spine",
                mode="targeted",
                required_passes=["deterministic_text"],
            )
            coverage_path = root / "coverage.json"
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                coverage_path,
                pass_id="deterministic_text",
                status="completed",
                result_path=audit_dir / "findings.json",
            )
            output_dir = root / "final"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("evidence_spine.py")),
                    "finalize",
                    str(prepared["paths"]["manifest"]),
                    str(prepared["paths"]["ledger"]),
                    str(coverage_path),
                    "--output-dir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((output_dir / "review-report.md").exists())
            self.assertIn("complete", completed.stdout)


if __name__ == "__main__":
    unittest.main()
