import json
import tempfile
import unittest
from pathlib import Path

from audit_manuscript import run_audit
from evidence_spine import adjudicate_report, prepare_evidence_spine, record_pass
from quantitative_checks import analyze_file
from verify_standards import build_ledger as build_standards_ledger


class EvidenceSpineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write_json(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def record_and_finalize(
        self,
        prepared,
        *,
        pass_id,
        result_path,
        reviewer="",
        attest=False,
        capability_updates=None,
        final_name="final",
    ):
        coverage_path = self.root / f"coverage-{pass_id}.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id=pass_id,
            status="completed",
            result_path=result_path,
            reviewer=reviewer,
            attest_ledger_read=attest,
            capability_updates=capability_updates,
        )
        return adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / final_name,
        )

    def test_ingests_current_deterministic_audit_output(self):
        manuscript = self.root / "abbreviation.md"
        manuscript.write_text(
            """Abstract
A self-centering (SC) frame was tested. SC remained stable.

Introduction
A self-centering (SC) frame was analyzed. The self-centering frame remained stable.
""",
            encoding="utf-8",
        )
        audit_dir = self.root / "audit-output"
        audit = run_audit(manuscript, audit_dir)
        self.assertTrue(audit["findings"])
        prepared = prepare_evidence_spine(
            manuscript,
            self.root / "spine",
            mode="targeted",
            required_passes=["deterministic_text"],
        )
        result = self.record_and_finalize(
            prepared,
            pass_id="deterministic_text",
            result_path=audit_dir / "findings.json",
        )
        self.assertEqual("complete", result["review_status"])
        self.assertTrue(result["findings"])
        self.assertTrue(all(item["evidence_ids"] for item in result["findings"]))

    def test_ingests_current_quantitative_output(self):
        manuscript = self.root / "quantity.md"
        manuscript.write_text(
            "Results\nThe reported conversion was 1000 N = 2 kN.\n",
            encoding="utf-8",
        )
        quantitative = analyze_file(manuscript)
        self.assertIn(
            "unit-conversion-mismatch",
            {item["check_id"] for item in quantitative["findings"]},
        )
        result_path = self.write_json("quantitative.json", quantitative)
        prepared = prepare_evidence_spine(
            manuscript,
            self.root / "spine",
            mode="targeted",
            required_passes=["quantitative"],
        )
        result = self.record_and_finalize(
            prepared,
            pass_id="quantitative",
            result_path=result_path,
        )
        self.assertEqual("complete", result["review_status"])
        self.assertIn(
            "unit-conversion-mismatch",
            {item["check_id"] for item in result["findings"]},
        )

    def test_modified_bibliography_invalidates_review(self):
        manuscript = self.root / "paper.tex"
        bibliography = self.root / "refs.bib"
        manuscript.write_text(
            "\\section{Introduction}\nPrior work was reviewed~\\cite{sample}.\n",
            encoding="utf-8",
        )
        bibliography.write_text(
            "@article{sample,title={Sample},year={2020}}\n",
            encoding="utf-8",
        )
        prepared = prepare_evidence_spine(
            manuscript,
            self.root / "spine",
            mode="targeted",
            required_passes=["citation_integrity"],
            additional_artifacts=[("bibliography", bibliography)],
        )
        bibliography.write_text(
            "@article{sample,title={Changed},year={2020}}\n",
            encoding="utf-8",
        )
        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            prepared["paths"]["coverage"],
            self.root / "final",
        )
        self.assertEqual("stale", result["review_status"])
        self.assertIn("stale_artifact:refs.bib", result["diagnostics"])

    def test_not_applicable_pass_requires_a_current_inventory_result(self):
        manuscript = self.root / "no-citations.md"
        manuscript.write_text("Introduction\nNo literature claims are made here.\n", encoding="utf-8")
        prepared = prepare_evidence_spine(
            manuscript,
            self.root / "spine",
            mode="targeted",
            required_passes=["claim_support"],
        )
        inventory = self.write_json(
            "citation-inventory.json",
            {
                "schema_version": "test",
                "pass_id": "claim_support",
                "provenance": {
                    "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"]
                },
                "inventory": {
                    "scope": "in-text citations in the complete manuscript",
                    "item_count": 0,
                    "items": [],
                },
                "findings": [],
            },
        )
        coverage = self.root / "coverage-na.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage,
            pass_id="claim_support",
            status="not_applicable",
            result_path=inventory,
            rationale="The completed citation inventory found no in-text citations.",
            reviewer="citation-inventory",
        )
        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage,
            self.root / "final",
        )
        self.assertEqual("complete", result["review_status"])
        self.assertEqual("ready_given_evidence", result["submission_readiness"])

        inventory.write_text("{}", encoding="utf-8")
        stale = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage,
            self.root / "stale-final",
        )
        self.assertEqual("incomplete", stale["review_status"])
        self.assertIn("stale_pass_result:claim_support", stale["diagnostics"])

    def test_claim_support_source_passage_gets_content_addressed_evidence_id(self):
        manuscript = self.root / "claim.md"
        manuscript_claim = "The tested frame reduced peak drift by 20%."
        manuscript.write_text(
            f"Results\n{manuscript_claim}\n",
            encoding="utf-8",
        )
        source = self.root / "cited-source.txt"
        source_quote = (
            "For the tested single-bay frame, the measured peak drift was reduced by "
            "approximately 20% relative to the reference specimen."
        )
        source.write_text(source_quote + "\n", encoding="utf-8")
        source_map = self.write_json(
            "cited-source-map.json",
            {
                "sources": [
                    {"citation_key": "Synthetic2026", "path": source.name}
                ]
            },
        )
        prepared = prepare_evidence_spine(
            manuscript,
            self.root / "spine",
            mode="targeted",
            required_passes=["claim_support"],
            additional_artifacts=[
                ("cited_source", source),
                ("cited_source_map", source_map),
            ],
        )
        finding = {
            "id": "CITE-SYNTHETIC",
            "category": "citation-support",
            "check_id": "citation-partially-supports-claim",
            "severity": "Minor",
            "confidence": 0.91,
            "status": "confirmed",
            "location": {
                "source": "claim.md",
                "line": 2,
                "section": "Results",
                "scope": "body",
            },
            "quote": manuscript_claim,
            "verdict": "partially_supports",
            "citation_key": "Synthetic2026",
            "dimension_matches": {
                "population_or_object": "partial",
            },
            "observation": "The source is limited to one tested frame.",
            "evidence": [
                {
                    "rank": 1,
                    "location": {"line": 1, "paragraph": 1},
                    "quote": source_quote,
                    "retrieval_score": 0.96,
                }
            ],
            "suggested_fix": "Limit the claim to the tested configuration.",
            "auto_fixable": False,
        }
        result_path = self.write_json(
            "claim-support.json",
            {
                "schema_version": "test",
                "pass_id": "claim_support",
                "provenance": {
                    "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"]
                },
                "formal_findings": [finding],
            },
        )
        result = self.record_and_finalize(
            prepared,
            pass_id="claim_support",
            result_path=result_path,
            reviewer="claim-support-reviewer",
            capability_updates={"cited_full_text": "available"},
        )
        self.assertEqual(1, len(result["findings"]))
        self.assertEqual(1, result["summary"]["external_evidence_count"])
        self.assertGreaterEqual(len(result["findings"][0]["evidence_ids"]), 2)
        final_ledger_path = self.root / "final" / "final-evidence-ledger.json"
        final_ledger = json.loads(final_ledger_path.read_text(encoding="utf-8"))
        external = [
            item
            for item in final_ledger["evidence"]
            if item.get("kind") == "external_source_span"
        ]
        self.assertEqual(source_quote, external[0]["quote"])
        self.assertEqual(result["final_ledger_fingerprint"], final_ledger["ledger_fingerprint"])

    def test_standard_metadata_finding_has_a_real_quote(self):
        manuscript = self.root / "standard.md"
        manuscript.write_text(
            "Methods\nThe design followed ASCE 7 for the loading combinations.\n",
            encoding="utf-8",
        )
        registry = Path(__file__).resolve().parent.parent / "references" / "standards-registry.json"
        standards = build_standards_ledger(manuscript, registry)
        missing = next(
            item
            for item in standards["findings"]
            if item["check_id"] == "standard-version-missing"
        )
        self.assertIn("ASCE 7", missing["quote"])
        self.assertEqual("deterministic", missing["evidence_mode"])

        result_path = self.write_json("standards.json", standards)
        prepared = prepare_evidence_spine(
            manuscript,
            self.root / "spine",
            mode="targeted",
            required_passes=["engineering_standards"],
            additional_artifacts=[("standards_registry", registry)],
        )
        result = self.record_and_finalize(
            prepared,
            pass_id="engineering_standards",
            result_path=result_path,
            reviewer="standards-metadata-pass",
            attest=True,
        )
        self.assertIn(
            "standard-version-missing",
            {item["check_id"] for item in result["findings"]},
        )


if __name__ == "__main__":
    unittest.main()
