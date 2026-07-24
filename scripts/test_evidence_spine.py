import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evidence_spine import (
    EvidenceSpineError,
    coverage_fingerprint,
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

    def write_result(
        self,
        name,
        findings,
        *,
        pass_id=None,
        ledger_fingerprint=None,
        input_fingerprint=None,
        reviewer="",
    ):
        payload = {"schema_version": "test", "findings": findings}
        if pass_id:
            payload["pass_id"] = pass_id
        if ledger_fingerprint:
            payload["provenance"] = {
                "ledger_fingerprint": ledger_fingerprint,
                "input_fingerprint": input_fingerprint,
            }
        if pass_id == "claim_logic":
            payload["semantic_audit_status"] = "completed"
            payload["semantic_review"] = {
                "scope": "The targeted logic issue and its anchored manuscript context.",
                "reviewed_by": reviewer,
                "input_fingerprint": input_fingerprint,
                "ledger_fingerprint": ledger_fingerprint,
                "node_reviews": [],
                "edge_reviews": [],
                "contract_gap_reviews": [],
            }
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
            pass_id=pass_id,
            ledger_fingerprint=prepared["ledger"]["ledger_fingerprint"],
            input_fingerprint=prepared["ledger"]["input_fingerprint"],
            reviewer=reviewer,
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
    def test_completed_result_is_revalidated_during_reconstruction(self):
        prepared = self.prepare(
            name="revalidate-completed-spine",
            pass_id="language_tense",
        )
        valid_payload = {
            "schema_version": "test",
            "pass_id": "language_tense",
            "provenance": {
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                "input_fingerprint": prepared["ledger"]["input_fingerprint"],
            },
            "summary": {"review_completed": True},
            "findings": [],
        }
        valid_path = self.root / "language-valid.json"
        valid_path.write_text(json.dumps(valid_payload), encoding="utf-8")
        coverage_path = self.root / "language-valid-coverage.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id="language_tense",
            status="completed",
            result_path=valid_path,
            reviewer="language-reviewer",
        )
        baseline = self.finalize(
            prepared,
            coverage_path,
            name="language-valid-final",
        )
        self.assertEqual("ready_given_evidence", baseline["submission_readiness"])

        forged_path = self.root / "language-forged.json"
        forged_path.write_text("{}", encoding="utf-8")
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        record = next(
            item for item in coverage["passes"]
            if item["pass_id"] == "language_tense"
        )
        record["result"]["path"] = str(forged_path)
        record["result"]["sha256"] = hashlib.sha256(
            forged_path.read_bytes()
        ).hexdigest()
        coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)
        forged_coverage = self.root / "language-forged-coverage.json"
        forged_coverage.write_text(json.dumps(coverage), encoding="utf-8")

        result = self.finalize(
            prepared,
            forged_coverage,
            name="language-forged-final",
        )
        self.assertEqual("incomplete", result["review_status"])
        self.assertEqual(
            "manual_confirmation_required",
            result["submission_readiness"],
        )
        self.assertTrue(
            any(
                item.startswith("invalid_pass_result_contract:language_tense:")
                for item in result["diagnostics"]
            )
        )

    def test_not_applicable_result_and_inventory_are_revalidated(self):
        prepared = self.prepare(
            name="revalidate-na-spine",
            pass_id="visual",
        )
        valid_payload = {
            "schema_version": "test",
            "pass_id": "visual",
            "provenance": {
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                "input_fingerprint": prepared["ledger"]["input_fingerprint"],
            },
            "inventory": {
                "scope": "All figure and table callouts in the current manuscript.",
                "item_count": 0,
                "items": [],
            },
        }
        valid_path = self.root / "visual-na-valid.json"
        valid_path.write_text(json.dumps(valid_payload), encoding="utf-8")
        coverage_path = self.root / "visual-na-valid-coverage.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id="visual",
            status="not_applicable",
            result_path=valid_path,
            rationale="A current visual inventory found no figures or tables.",
            reviewer="visual-reviewer",
        )
        baseline = self.finalize(
            prepared,
            coverage_path,
            name="visual-na-valid-final",
        )
        self.assertEqual("ready_given_evidence", baseline["submission_readiness"])

        forged_payloads = {
            "malformed": {},
            "inventory-drift": {
                **valid_payload,
                "inventory": {
                    "scope": "A different claimed inventory scope.",
                    "item_count": 0,
                    "items": [],
                },
            },
        }
        for label, payload in forged_payloads.items():
            with self.subTest(label=label):
                forged_path = self.root / f"visual-na-{label}.json"
                forged_path.write_text(json.dumps(payload), encoding="utf-8")
                coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
                record = next(
                    item for item in coverage["passes"]
                    if item["pass_id"] == "visual"
                )
                record["result"]["path"] = str(forged_path)
                record["result"]["sha256"] = hashlib.sha256(
                    forged_path.read_bytes()
                ).hexdigest()
                coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)
                forged_coverage = self.root / f"visual-na-{label}-coverage.json"
                forged_coverage.write_text(json.dumps(coverage), encoding="utf-8")
                result = self.finalize(
                    prepared,
                    forged_coverage,
                    name=f"visual-na-{label}-final",
                )
                self.assertEqual("incomplete", result["review_status"])
                self.assertNotEqual(
                    "ready_given_evidence",
                    result["submission_readiness"],
                )


    def strict_payload(self, prepared, pass_id="language_tense"):
        return {
            "schema_version": "strict-contract-test",
            "pass_id": pass_id,
            "provenance": {
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                "input_fingerprint": prepared["ledger"]["input_fingerprint"],
            },
            "summary": {"review_completed": True},
            "findings": [],
        }

    def assert_strict_payload_rejected(
        self,
        prepared,
        payload,
        *,
        pass_id="language_tense",
        label,
    ):
        result_path = self.root / f"{label}-result.json"
        result_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / f"{label}-coverage.json",
                pass_id=pass_id,
                status="completed",
                result_path=result_path,
                reviewer=f"{pass_id}-reviewer",
            )

    def test_completed_result_requires_exact_pass_id(self):
        prepared = self.prepare(
            name="strict-missing-pass-id-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        payload.pop("pass_id")
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            label="strict-missing-pass-id",
        )

    def test_completed_result_requires_native_string_schema_version(self):
        prepared = self.prepare(
            name="strict-schema-type-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        payload["schema_version"] = {"fake": 1}
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            label="strict-schema-type",
        )

    def test_completed_result_requires_findings_array(self):
        prepared = self.prepare(
            name="strict-findings-type-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        payload["findings"] = {}
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            label="strict-findings-type",
        )

    def test_completed_result_rejects_false_completion_marker(self):
        prepared = self.prepare(
            name="strict-false-completion-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        payload["summary"] = {"review_completed": False}
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            label="strict-false-completion",
        )

    def test_completed_result_rejects_mismatched_finding_count(self):
        prepared = self.prepare(
            name="strict-count-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        payload["summary"]["finding_count"] = 99
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            label="strict-count",
        )

    def test_completed_result_rejects_empty_inventory_as_execution(self):
        prepared = self.prepare(
            name="strict-empty-inventory-spine",
            pass_id="deterministic_text",
        )
        payload = self.strict_payload(prepared, "deterministic_text")
        payload.pop("summary")
        payload.pop("findings")
        payload["inventory"] = {}
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            pass_id="deterministic_text",
            label="strict-empty-inventory",
        )

    def test_declared_wrong_source_cannot_fall_back_to_matching_digest(self):
        prepared = self.prepare(
            name="strict-wrong-source-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        payload["sources"] = [
            {
                "source": "not-the-manuscript.md",
                "sha256": self.source_hash(),
            }
        ]
        self.assert_strict_payload_rejected(
            prepared,
            payload,
            label="strict-wrong-source",
        )

    def test_finalize_revalidates_resigned_result_without_pass_id(self):
        prepared = self.prepare(
            name="strict-finalize-spine",
            pass_id="language_tense",
        )
        payload = self.strict_payload(prepared)
        result_path = self.root / "strict-finalize-result.json"
        result_path.write_text(json.dumps(payload), encoding="utf-8")
        coverage_path = self.root / "strict-finalize-coverage.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id="language_tense",
            status="completed",
            result_path=result_path,
            reviewer="language-reviewer",
        )

        payload.pop("pass_id")
        result_path.write_text(json.dumps(payload), encoding="utf-8")
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        record = next(
            item
            for item in coverage["passes"]
            if item["pass_id"] == "language_tense"
        )
        record["result"]["sha256"] = hashlib.sha256(
            result_path.read_bytes()
        ).hexdigest()
        coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)
        resigned_coverage = self.root / "strict-finalize-resigned-coverage.json"
        resigned_coverage.write_text(json.dumps(coverage), encoding="utf-8")

        final = self.finalize(
            prepared,
            resigned_coverage,
            name="strict-finalize-resigned",
        )
        self.assertEqual("incomplete", final["review_status"])
        self.assertTrue(
            any(
                item.startswith(
                    "invalid_pass_result_contract:language_tense:"
                )
                for item in final["diagnostics"]
            )
        )



if __name__ == "__main__":
    unittest.main()
