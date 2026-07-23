import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evidence_spine import (
    EvidenceSpineError,
    adjudicate_report,
    prepare_evidence_spine,
    record_pass,
)


class EvidenceSpineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manuscript = self.root / "paper.md"
        self.manuscript.write_text(
            """Abstract
A self-centering (SC) frame was tested at a peak drift ratio of 2.0%.

Methods
The frame was calibrated against the measured response.

Results
The proposed model predicts the peak response accurately.
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def source_hash(self):
        return hashlib.sha256(self.manuscript.read_bytes()).hexdigest()

    def prepare(self, name="spine", *, pass_id="deterministic_text", text_mode="excerpt"):
        return prepare_evidence_spine(
            self.manuscript,
            self.root / name,
            mode="targeted",
            required_passes=[pass_id],
            text_mode=text_mode,
        )

    def finding(self, **changes):
        value = {
            "id": "TEST-001",
            "category": "terminology",
            "check_id": "test-anchored-finding",
            "severity": "Minor",
            "confidence": 0.95,
            "status": "confirmed",
            "location": {
                "source": "paper.md",
                "line": 2,
                "section": "Abstract",
                "scope": "abstract",
            },
            "quote": "A self-centering (SC) frame was tested at a peak drift ratio of 2.0%.",
            "observation": "Synthetic anchored issue.",
            "expected": "Synthetic expected state.",
            "reason": "Synthetic deterministic reason.",
            "evidence": [{"class": "A", "source": "manuscript"}],
            "suggested_fix": "Revise the synthetic issue.",
            "auto_fixable": False,
        }
        value.update(changes)
        return value

    def write_result(self, name, findings, *, ledger_fingerprint=None):
        payload = {"schema_version": "test", "findings": findings}
        if ledger_fingerprint:
            payload["provenance"] = {"ledger_fingerprint": ledger_fingerprint}
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def complete_pass(
        self,
        prepared,
        *,
        pass_id,
        findings,
        reviewer="",
        capability_updates=None,
        name="coverage-complete.json",
    ):
        result_path = self.write_result(
            f"{pass_id}-result.json",
            findings,
            ledger_fingerprint=prepared["ledger"]["ledger_fingerprint"],
        )
        coverage_path = self.root / name
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id=pass_id,
            status="completed",
            result_path=result_path,
            reviewer=reviewer,
            capability_updates=capability_updates,
        )
        return coverage_path, result_path

    def finalize(self, prepared, coverage_path, name="final"):
        return adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / name,
        )

    def test_prepare_is_read_only_and_fingerprints_are_stable(self):
        before = self.source_hash()
        first = self.prepare("first")
        second = self.prepare("second")
        self.assertEqual(before, self.source_hash())
        self.assertEqual(
            first["manifest"]["input_fingerprint"],
            second["manifest"]["input_fingerprint"],
        )
        self.assertEqual(
            first["ledger"]["ledger_fingerprint"],
            second["ledger"]["ledger_fingerprint"],
        )
        self.assertEqual(
            [item["evidence_id"] for item in first["ledger"]["evidence"]],
            [item["evidence_id"] for item in second["ledger"]["evidence"]],
        )
        self.assertTrue(first["ledger"]["privacy"]["contains_manuscript_excerpts"])

    def test_hash_only_ledger_omits_manuscript_quotes(self):
        prepared = self.prepare(text_mode="hash-only")
        self.assertTrue(prepared["ledger"]["evidence"])
        self.assertTrue(all("quote" not in item for item in prepared["ledger"]["evidence"]))
        self.assertFalse(prepared["ledger"]["privacy"]["contains_manuscript_excerpts"])

    def test_targeted_mode_requires_at_least_one_pass(self):
        with self.assertRaises(EvidenceSpineError):
            prepare_evidence_spine(
                self.manuscript,
                self.root / "invalid-targeted",
                mode="targeted",
            )

    def test_anchored_finding_is_accepted_and_bound_to_ledger(self):
        prepared = self.prepare()
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="deterministic_text",
            findings=[self.finding()],
        )
        result = self.finalize(prepared, coverage_path)
        self.assertEqual("complete", result["review_status"])
        self.assertEqual("revision_required", result["submission_readiness"])
        self.assertEqual(1, len(result["findings"]))
        self.assertTrue(result["findings"][0]["evidence_ids"])
        self.assertEqual("accepted", result["findings"][0]["adjudication"]["outcome"])

    def test_not_run_required_pass_prevents_clean_statement(self):
        prepared = self.prepare()
        result = self.finalize(prepared, prepared["paths"]["coverage"])
        self.assertEqual("incomplete", result["review_status"])
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])
        report = (self.root / "final" / "review-report.md").read_text(encoding="utf-8")
        self.assertIn("不能把“未发现问题”解释为稿件无问题", report)

    def test_modified_manuscript_makes_report_stale(self):
        prepared = self.prepare()
        self.manuscript.write_text(
            self.manuscript.read_text(encoding="utf-8") + "\nChanged after audit.\n",
            encoding="utf-8",
        )
        result = self.finalize(prepared, prepared["paths"]["coverage"])
        self.assertEqual("stale", result["review_status"])
        self.assertIn("stale_artifact:paper.md", result["diagnostics"])

    def test_quote_mismatch_is_a_manual_check_not_a_formal_finding(self):
        prepared = self.prepare()
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="deterministic_text",
            findings=[self.finding(quote="This sentence is not in the manuscript.")],
        )
        result = self.finalize(prepared, coverage_path)
        self.assertEqual([], result["findings"])
        self.assertEqual(1, len(result["manual_checks"]))
        self.assertIn(
            "quote_not_found_near_locator",
            result["manual_checks"][0]["adjudication"]["reasons"],
        )
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])

    def test_unsafe_or_unresolved_related_location_is_deferred(self):
        prepared = self.prepare()
        finding = self.finding(
            related_locations=[{"source": "../outside.md", "line": 1}]
        )
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="deterministic_text",
            findings=[finding],
        )
        result = self.finalize(prepared, coverage_path)
        self.assertEqual([], result["findings"])
        self.assertIn(
            "related_unsafe_source_locator",
            result["manual_checks"][0]["adjudication"]["reasons"],
        )

    def test_claim_support_requires_cited_full_text_capability(self):
        prepared = self.prepare(pass_id="claim_support")
        finding = self.finding(
            category="citation-support",
            check_id="citation-does-not-support-claim",
        )
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="claim_support",
            findings=[finding],
            reviewer="support-reviewer",
        )
        result = self.finalize(prepared, coverage_path)
        self.assertEqual([], result["findings"])
        self.assertIn(
            "missing_capability:cited_full_text",
            result["manual_checks"][0]["adjudication"]["reasons"],
        )

    def test_semantic_major_requires_alternatives_and_independent_recheck(self):
        prepared = self.prepare(pass_id="claim_logic")
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="claim_logic",
            findings=[self.finding(severity="Major")],
            reviewer="logic-proposer",
        )
        result = self.finalize(prepared, coverage_path)
        self.assertEqual([], result["findings"])
        self.assertIn(
            "missing_alternative_explanations",
            result["manual_checks"][0]["adjudication"]["reasons"],
        )
        self.assertEqual("Major", result["manual_checks"][0]["severity"])
        self.assertLess(result["manual_checks"][0]["confidence"], 0.60)

    def test_completed_semantic_major_is_accepted(self):
        prepared = self.prepare(pass_id="claim_logic")
        finding = self.finding(
            severity="Major",
            alternative_explanations=[
                {
                    "explanation": "The difference could be caused by rounding.",
                    "status": "ruled_out",
                    "evidence_ids": [],
                }
            ],
            independent_recheck={
                "status": "confirmed",
                "reviewer": "independent-reviewer",
                "rationale": "The current source and calculation confirm the discrepancy.",
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
            },
        )
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="claim_logic",
            findings=[finding],
            reviewer="logic-proposer",
        )
        result = self.finalize(prepared, coverage_path)
        self.assertEqual(1, len(result["findings"]))
        self.assertEqual("Major", result["findings"][0]["severity"])
        self.assertEqual("verified", result["findings"][0]["adjudication"]["semantic_controls"])

    def test_same_reviewer_is_not_an_independent_recheck(self):
        prepared = self.prepare(pass_id="claim_logic")
        finding = self.finding(
            severity="Major",
            alternative_explanations=[
                {"explanation": "Rounding.", "status": "ruled_out", "evidence_ids": []}
            ],
            independent_recheck={
                "status": "confirmed",
                "reviewer": "logic-proposer",
                "rationale": "Repeated the same review.",
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
            },
        )
        coverage_path, _ = self.complete_pass(
            prepared,
            pass_id="claim_logic",
            findings=[finding],
            reviewer="logic-proposer",
        )
        result = self.finalize(prepared, coverage_path)
        self.assertIn(
            "rechecker_not_independent",
            result["manual_checks"][0]["adjudication"]["reasons"],
        )

    def test_changed_pass_result_cannot_remain_completed(self):
        prepared = self.prepare()
        coverage_path, result_path = self.complete_pass(
            prepared,
            pass_id="deterministic_text",
            findings=[self.finding()],
        )
        result_path.write_text("{}", encoding="utf-8")
        result = self.finalize(prepared, coverage_path)
        self.assertEqual("incomplete", result["review_status"])
        self.assertIn("stale_pass_result:deterministic_text", result["diagnostics"])

    def test_direct_coverage_edit_is_rejected(self):
        prepared = self.prepare()
        coverage = json.loads(prepared["paths"]["coverage"].read_text(encoding="utf-8"))
        coverage["passes"][0]["status"] = "completed"
        tampered = self.root / "coverage-tampered.json"
        tampered.write_text(json.dumps(coverage), encoding="utf-8")
        with self.assertRaises(EvidenceSpineError):
            self.finalize(prepared, tampered)

    def test_not_applicable_requires_rationale_and_inventory_result(self):
        prepared = self.prepare(pass_id="claim_support")
        output = self.root / "coverage-na.json"
        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                output,
                pass_id="claim_support",
                status="not_applicable",
                rationale="No in-text citations were found.",
                reviewer="citation-inventory",
            )

    def test_existing_outputs_are_not_overwritten_without_force(self):
        prepared = self.prepare()
        with self.assertRaises(EvidenceSpineError):
            prepare_evidence_spine(
                self.manuscript,
                prepared["paths"]["manifest"].parent,
                mode="targeted",
                required_passes=["deterministic_text"],
            )


if __name__ == "__main__":
    unittest.main()
