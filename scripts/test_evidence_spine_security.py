import json
import tempfile
import unittest
from pathlib import Path

from evidence_spine import (
    EvidenceSpineError,
    adjudicate_report,
    coverage_fingerprint,
    prepare_evidence_spine,
    record_pass,
)


class EvidenceSpineSecurityTests(unittest.TestCase):
    """Adversarial regression tests for fail-closed evidence-spine behavior."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manuscript = self.root / "paper.md"
        self.manuscript.write_text(
            "Results\nThe tested frame reduced peak drift by 20%.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_json(self, name, payload):
        path = self.root / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def prepare(
        self,
        pass_id,
        *,
        manuscript=None,
        mode="targeted",
        output_name="spine",
        additional_artifacts=(),
    ):
        kwargs = {}
        if mode == "targeted":
            kwargs["required_passes"] = [pass_id]
        return prepare_evidence_spine(
            manuscript or self.manuscript,
            self.root / output_name,
            mode=mode,
            additional_artifacts=additional_artifacts,
            **kwargs,
        )

    def finding(self, **changes):
        value = {
            "id": "SECURITY-001",
            "category": "terminology",
            "check_id": "security-regression",
            "severity": "Minor",
            "confidence": 0.95,
            "status": "confirmed",
            "location": {
                "source": self.manuscript.name,
                "line": 2,
                "section": "Results",
                "scope": "body",
            },
            "quote": "The tested frame reduced peak drift by 20%.",
            "observation": "Synthetic security-regression observation.",
            "expected": "The evidence contract should remain fail-closed.",
            "reason": "The synthetic input exercises an evidence-boundary invariant.",
            "evidence": [],
            "suggested_fix": "Do not accept the synthetic proposal.",
            "auto_fixable": False,
        }
        value.update(changes)
        return value

    def result_file(self, prepared, name, findings):
        required_passes = [
            item["pass_id"]
            for item in prepared["coverage"]["passes"]
            if item.get("required")
        ]
        self.assertEqual(1, len(required_passes))
        return self.write_json(
            name,
            {
                "schema_version": "security-test",
                "pass_id": required_passes[0],
                "provenance": {
                    "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"]
                },
                "findings": findings,
            },
        )

    def complete_pass(
        self,
        prepared,
        pass_id,
        result_path,
        *,
        output_name="coverage-complete.json",
        reviewer="security-reviewer",
        capability_updates=None,
    ):
        output = self.root / output_name
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            output,
            pass_id=pass_id,
            status="completed",
            result_path=result_path,
            reviewer=reviewer,
            capability_updates=capability_updates,
        )
        return output

    def finalize(self, prepared, coverage_path, *, name="final", manifest_path=None):
        return adjudicate_report(
            manifest_path or prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / name,
        )

    def assert_rejected_or_no_formal_findings(self, operation):
        try:
            result = operation()
        except EvidenceSpineError:
            return
        self.assertEqual([], result["findings"])
        self.assertNotEqual("ready_given_evidence", result["submission_readiness"])

    def test_deep_required_passes_are_reconstructed_not_trusted_from_coverage(self):
        prepared = self.prepare(
            "deterministic_text",
            mode="deep",
            output_name="deep-spine",
        )
        coverage = json.loads(
            prepared["paths"]["coverage"].read_text(encoding="utf-8")
        )
        for item in coverage["passes"]:
            item["required"] = False
        coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)
        tampered = self.write_json("coverage-required-cleared.json", coverage)

        try:
            result = self.finalize(prepared, tampered, name="deep-final")
        except EvidenceSpineError:
            return
        self.assertNotEqual("complete", result["review_status"])
        self.assertNotEqual("ready_given_evidence", result["submission_readiness"])

    def test_root_input_substitution_is_rejected_or_marks_report_stale(self):
        original_dir = self.root / "original"
        substitute_dir = self.root / "substitute"
        original_dir.mkdir()
        substitute_dir.mkdir()
        original = original_dir / "paper.md"
        substitute = substitute_dir / "paper.md"
        original.write_text("Results\nOriginal sentence.\n", encoding="utf-8")
        substitute.write_text("Results\nSubstitute sentence.\n", encoding="utf-8")

        prepared = self.prepare(
            "deterministic_text",
            manuscript=original,
            output_name="root-spine",
        )
        finding = self.finding(
            location={
                "source": "paper.md",
                "line": 2,
                "section": "Results",
                "scope": "body",
            },
            quote="Substitute sentence.",
        )
        result_path = self.result_file(prepared, "root-result.json", [finding])
        coverage_path = self.complete_pass(
            prepared,
            "deterministic_text",
            result_path,
            output_name="root-coverage.json",
        )

        manifest = json.loads(
            prepared["paths"]["manifest"].read_text(encoding="utf-8")
        )
        manifest["root_input"] = str(substitute)
        altered_manifest = self.write_json("root-manifest-altered.json", manifest)

        try:
            result = self.finalize(
                prepared,
                coverage_path,
                name="root-final",
                manifest_path=altered_manifest,
            )
        except EvidenceSpineError:
            return
        self.assertEqual("stale", result["review_status"])
        self.assertEqual([], result["findings"])

    def test_claim_support_quote_cannot_bind_to_a_different_citation_source(self):
        source_a = self.root / "a.txt"
        source_b = self.root / "b.txt"
        source_quote = "Source A reports a 20% reduction for one specimen."
        source_a.write_text(source_quote + "\n", encoding="utf-8")
        source_b.write_text(
            "Source B discusses a different structural system.\n",
            encoding="utf-8",
        )
        prepared = self.prepare(
            "claim_support",
            output_name="wrong-source-spine",
            additional_artifacts=(
                ("cited_source", source_a),
                ("cited_source", source_b),
            ),
        )
        finding = self.finding(
            category="citation-support",
            check_id="citation-partially-supports-claim",
            citation_key="B",
            evidence=[
                {
                    "rank": 1,
                    "citation_key": "B",
                    "location": {"source": "b.txt", "line": 1},
                    "quote": source_quote,
                }
            ],
        )
        result_path = self.result_file(
            prepared,
            "wrong-source-result.json",
            [finding],
        )

        def operation():
            coverage_path = self.complete_pass(
                prepared,
                "claim_support",
                result_path,
                output_name="wrong-source-coverage.json",
                capability_updates={"cited_full_text": "available"},
            )
            return self.finalize(
                prepared,
                coverage_path,
                name="wrong-source-final",
            )

        self.assert_rejected_or_no_formal_findings(operation)

    def test_external_evidence_locator_must_resolve_to_the_quoted_passage(self):
        source = self.root / "cited-source.txt"
        source_quote = "The source reports a 20% reduction for one specimen."
        source.write_text(source_quote + "\n", encoding="utf-8")
        prepared = self.prepare(
            "claim_support",
            output_name="bad-locator-spine",
            additional_artifacts=(("cited_source", source),),
        )
        finding = self.finding(
            category="citation-support",
            check_id="citation-partially-supports-claim",
            citation_key="cited-source",
            evidence=[
                {
                    "rank": 1,
                    "citation_key": "cited-source",
                    "location": {
                        "source": source.name,
                        "line": 999,
                        "page": 999,
                    },
                    "quote": source_quote,
                }
            ],
        )
        result_path = self.result_file(
            prepared,
            "bad-locator-result.json",
            [finding],
        )

        def operation():
            coverage_path = self.complete_pass(
                prepared,
                "claim_support",
                result_path,
                output_name="bad-locator-coverage.json",
                capability_updates={"cited_full_text": "available"},
            )
            return self.finalize(
                prepared,
                coverage_path,
                name="bad-locator-final",
            )

        self.assert_rejected_or_no_formal_findings(operation)

    def test_empty_not_applicable_result_is_rejected_as_inventory_evidence(self):
        manuscript = self.root / "citation.md"
        manuscript.write_text(
            "Introduction\nA literature-dependent claim is cited [1].\n",
            encoding="utf-8",
        )
        prepared = self.prepare(
            "claim_support",
            manuscript=manuscript,
            output_name="empty-inventory-spine",
        )
        empty_inventory = self.write_json(
            "empty-inventory.json",
            {
                "schema_version": "security-test",
                "provenance": {
                    "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"]
                },
            },
        )

        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / "empty-inventory-coverage.json",
                pass_id="claim_support",
                status="not_applicable",
                result_path=empty_inventory,
                rationale="No claims require source-support review.",
                reviewer="citation-inventory",
            )

    def test_self_reported_deterministic_mode_cannot_bypass_semantic_controls(self):
        prepared = self.prepare(
            "claim_logic",
            output_name="deterministic-bypass-spine",
        )
        finding = self.finding(
            category="logic",
            check_id="scope-overclaim",
            severity="Major",
            evidence_mode="deterministic",
        )
        result_path = self.result_file(
            prepared,
            "deterministic-bypass-result.json",
            [finding],
        )

        def operation():
            coverage_path = self.complete_pass(
                prepared,
                "claim_logic",
                result_path,
                output_name="deterministic-bypass-coverage.json",
                reviewer="logic-proposer",
            )
            return self.finalize(
                prepared,
                coverage_path,
                name="deterministic-bypass-final",
            )

        self.assert_rejected_or_no_formal_findings(operation)

    def test_declared_capabilities_cannot_remove_visual_render_requirement(self):
        prepared = self.prepare(
            "visual",
            output_name="capability-bypass-spine",
        )
        finding = self.finding(
            category="visual",
            check_id="figure-legibility",
            required_capabilities=["manuscript_text"],
            observation="The figure labels are unreadable.",
        )
        result_path = self.result_file(
            prepared,
            "capability-bypass-result.json",
            [finding],
        )

        def operation():
            coverage_path = self.complete_pass(
                prepared,
                "visual",
                result_path,
                output_name="capability-bypass-coverage.json",
                reviewer="visual-reviewer",
            )
            return self.finalize(
                prepared,
                coverage_path,
                name="capability-bypass-final",
            )

        self.assert_rejected_or_no_formal_findings(operation)

    def test_invalid_confidence_is_controlled_not_an_unhandled_conversion_error(self):
        prepared = self.prepare(
            "deterministic_text",
            output_name="invalid-confidence-spine",
        )
        finding = self.finding(confidence="high")
        result_path = self.result_file(
            prepared,
            "invalid-confidence-result.json",
            [finding],
        )
        try:
            coverage_path = self.complete_pass(
                prepared,
                "deterministic_text",
                result_path,
                output_name="invalid-confidence-coverage.json",
            )
            result = self.finalize(
                prepared,
                coverage_path,
                name="invalid-confidence-final",
            )
        except EvidenceSpineError:
            return
        except (TypeError, ValueError) as exc:
            self.fail(f"invalid confidence escaped as an unhandled conversion error: {exc}")

        self.assertEqual([], result["findings"])
        self.assertTrue(result["manual_checks"])
        self.assertIn(
            "invalid_confidence",
            result["manual_checks"][0]["adjudication"]["reasons"],
        )

    def test_generated_finding_id_is_stable_across_location_key_order(self):
        prepared = self.prepare(
            "deterministic_text",
            output_name="stable-id-spine",
        )
        location_a = {
            "source": "paper.md",
            "line": 2,
            "section": "Results",
            "scope": "body",
        }
        location_b = {
            "scope": "body",
            "section": "Results",
            "line": 2,
            "source": "paper.md",
        }
        finding_a = self.finding(location=location_a)
        finding_b = self.finding(location=location_b)
        finding_a.pop("id")
        finding_b.pop("id")
        result_a = self.result_file(prepared, "stable-id-result-a.json", [finding_a])
        result_b = self.result_file(prepared, "stable-id-result-b.json", [finding_b])
        coverage_a = self.complete_pass(
            prepared,
            "deterministic_text",
            result_a,
            output_name="stable-id-coverage-a.json",
        )
        coverage_b = self.complete_pass(
            prepared,
            "deterministic_text",
            result_b,
            output_name="stable-id-coverage-b.json",
        )
        final_a = self.finalize(prepared, coverage_a, name="stable-id-final-a")
        final_b = self.finalize(prepared, coverage_b, name="stable-id-final-b")

        self.assertEqual(1, len(final_a["findings"]))
        self.assertEqual(1, len(final_b["findings"]))
        self.assertEqual(final_a["findings"][0]["id"], final_b["findings"][0]["id"])

    def test_identical_latex_include_files_receive_unique_evidence_ids(self):
        manuscript = self.root / "main.tex"
        manuscript.write_text(
            "\\input{a}\n\\input{b}\n",
            encoding="utf-8",
        )
        repeated = "\\section{Results}\nThe model is stable.\n"
        (self.root / "a.tex").write_text(repeated, encoding="utf-8")
        (self.root / "b.tex").write_text(repeated, encoding="utf-8")
        prepared = self.prepare(
            "deterministic_text",
            manuscript=manuscript,
            output_name="duplicate-evidence-spine",
        )
        evidence_ids = [
            item["evidence_id"] for item in prepared["ledger"]["evidence"]
        ]

        self.assertEqual(len(evidence_ids), len(set(evidence_ids)))

    def test_bare_standard_source_cannot_bypass_rights_and_permission_gate(self):
        manuscript = self.root / "standard.md"
        manuscript_quote = "ASCE 7-22 Section 1.2 was applied."
        manuscript.write_text(
            "Methods\n" + manuscript_quote + "\n",
            encoding="utf-8",
        )
        standard_source = self.root / "asce-7-22.txt"
        standard_quote = "Section 1.2 applies only to the stated scope."
        standard_source.write_text(standard_quote + "\n", encoding="utf-8")

        def operation():
            prepared = self.prepare(
                "engineering_standards",
                manuscript=manuscript,
                output_name="rights-spine",
                additional_artifacts=(("standard_source", standard_source),),
            )
            finding = self.finding(
                category="standard",
                check_id="standard-clause-applicability",
                location={
                    "source": manuscript.name,
                    "line": 2,
                    "section": "Methods",
                    "scope": "body",
                },
                quote=manuscript_quote,
                evidence=[
                    {
                        "location": {
                            "source": standard_source.name,
                            "line": 1,
                        },
                        "quote": standard_quote,
                    }
                ],
            )
            result_path = self.result_file(
                prepared,
                "rights-result.json",
                [finding],
            )
            coverage_path = self.complete_pass(
                prepared,
                "engineering_standards",
                result_path,
                output_name="rights-coverage.json",
                capability_updates={"standard_text": "available"},
            )
            return self.finalize(prepared, coverage_path, name="rights-final")

        self.assert_rejected_or_no_formal_findings(operation)


if __name__ == "__main__":
    unittest.main()
