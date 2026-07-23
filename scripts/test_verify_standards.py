from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_standards as vs


REGISTRY = Path(__file__).resolve().parent.parent / "references" / "standards-registry.json"


class StandardLedgerTests(unittest.TestCase):
    def test_missing_and_mixed_editions_are_anchored_but_old_is_not_called_wrong(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manuscript = root / "paper.tex"
            manuscript.write_text(
                r"""\section{Methods}
The seismic demand was determined using ASCE 7.
The earlier comparison followed ASCE 7-16, whereas the redesign used ASCE/SEI 7-22.
""",
                encoding="utf-8",
            )

            data = vs.build_ledger(manuscript, REGISTRY)
            checks = [item["check_id"] for item in data["findings"]]
            self.assertIn("standard-version-missing", checks)
            self.assertIn("standard-edition-review", checks)
            self.assertIn("standard-edition-inconsistent", checks)
            old = next(item for item in data["findings"] if item["check_id"] == "standard-edition-review")
            self.assertEqual("needs-review", old["status"])
            self.assertIn("不能仅凭出版时间判错", old["reason"])

    def test_local_standard_text_yields_clause_evidence_without_copying_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manuscript = root / "paper.tex"
            standard = root / "my-lawful-copy.txt"
            source_map = root / "source-map.json"
            manuscript.write_text(
                r"The equivalent lateral force was calculated under ASCE/SEI 7-22 Section 12.8.1.",
                encoding="utf-8",
            )
            standard.write_text(
                "12.8 Equivalent Lateral Force Procedure\n12.8.1 General requirements and scope\nThe procedure shall apply only when its stated limits are satisfied.\n",
                encoding="utf-8",
            )
            source_map.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "designation": "ASCE/SEI 7-22",
                                "path": standard.name,
                                "processing_mode": "local-deterministic",
                                "rights_attested": True,
                                "permission_reference": "publisher permission recorded by user",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            before = hashlib.sha256(standard.read_bytes()).hexdigest()

            data = vs.build_ledger(manuscript, REGISTRY, source_map_path=source_map)

            reference = data["mentions"][0]["references"][0]
            self.assertEqual("located-candidates", reference["evidence_status"])
            self.assertIn("General requirements", reference["source_evidence"][0]["quote"])
            self.assertEqual(before, hashlib.sha256(standard.read_bytes()).hexdigest())
            self.assertEqual("not_assessed", data["review_tasks"][0]["assessment"])
            source_access = data["mentions"][0]["source_access"]
            self.assertEqual(standard.name, source_access["basename"])
            self.assertNotIn("path", source_access)

    def test_asce_source_is_not_read_without_publisher_permission_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manuscript = root / "paper.tex"
            standard = root / "ASCE_7-22.txt"
            source_map = root / "source-map.json"
            manuscript.write_text(
                r"ASCE/SEI 7-22 Section 12.8.1 was used.", encoding="utf-8"
            )
            standard.write_text("12.8.1 General requirements", encoding="utf-8")
            source_map.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "designation": "ASCE/SEI 7-22",
                                "path": standard.name,
                                "processing_mode": "local-deterministic",
                                "rights_attested": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(vs, "read_standard_source") as reader:
                data = vs.build_ledger(manuscript, REGISTRY, source_map_path=source_map)

            reader.assert_not_called()
            mention = data["mentions"][0]
            self.assertEqual(
                "publisher-permission-required", mention["source_access"]["status"]
            )
            self.assertEqual(
                "publisher-permission-required", mention["references"][0]["evidence_status"]
            )

    def test_standards_directory_is_metadata_only_without_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manuscript = root / "paper.md"
            standard = root / "ANSI_AISC_341-22.txt"
            manuscript.write_text(
                "ANSI/AISC 341-22 Section D1.1 was used.", encoding="utf-8"
            )
            standard.write_text("D1.1 Scope", encoding="utf-8")

            with patch.object(vs, "read_standard_source") as reader:
                data = vs.build_ledger(manuscript, REGISTRY, standards_dir=root)

            reader.assert_not_called()
            mention = data["mentions"][0]
            self.assertEqual(
                "rights-attestation-required", mention["source_access"]["status"]
            )
            self.assertEqual(
                "rights-attestation-required", mention["references"][0]["evidence_status"]
            )

    def test_clause_without_source_is_unable_not_a_false_defect(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = Path(tmp) / "paper.md"
            manuscript.write_text(
                "The member was checked using ANSI/AISC 341-22 Section D1.1.",
                encoding="utf-8",
            )
            data = vs.build_ledger(manuscript, REGISTRY)
            self.assertEqual("source-unavailable", data["review_tasks"][0]["evidence_status"])
            self.assertNotIn(
                "standard-clause-invalid",
                {item["check_id"] for item in data["findings"]},
            )

    def test_gb_jgj_and_eurocode_require_explicit_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = Path(tmp) / "paper.txt"
            manuscript.write_text(
                "The checks referenced EN 1998-1, GB 50011, and JGJ/T 101 without edition years.",
                encoding="utf-8",
            )
            data = vs.build_ledger(manuscript, REGISTRY)
            missing = [item for item in data["findings"] if item["check_id"] == "standard-version-missing"]
            self.assertEqual(3, len(missing))


class StandardOutputSafetyTests(unittest.TestCase):
    def test_outputs_do_not_overwrite_without_force_and_manuscript_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manuscript = root / "paper.txt"
            output = root / "review"
            manuscript.write_text("ASCE/SEI 7-22 Section 12.8.1 was used.", encoding="utf-8")
            before = hashlib.sha256(manuscript.read_bytes()).hexdigest()
            data = vs.build_ledger(manuscript, REGISTRY)
            vs.write_outputs(data, output)
            with self.assertRaises(FileExistsError):
                vs.write_outputs(data, output)
            self.assertEqual(before, hashlib.sha256(manuscript.read_bytes()).hexdigest())
            self.assertTrue((output / "standards.json").is_file())
            self.assertTrue((output / "standards-report.md").is_file())


if __name__ == "__main__":
    unittest.main()
