import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_spine import (
    EvidenceSpineError,
    adjudicate_report,
    prepare_evidence_spine,
    record_pass,
)


class EvidenceSpineContractTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manuscript = self.root / "paper.md"
        self.manuscript.write_text(
            "Methods\n"
            "The design followed ANSI/AISC 341-22, including provision E3.4.\n"
            "Results\n"
            "The tested frame reduced peak drift by 20% [1].\n",
            encoding="utf-8",
        )
        self.standard_source = self.root / "standard.txt"
        self.standard_source.write_text(
            "ANSI/AISC 341-22\nProvision E3.4 applies only within the stated scope.\n",
            encoding="utf-8",
        )
        self.registry = self.root / "standards-registry.json"
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": "0.2.0",
                    "checked_at": "2026-07-23",
                    "standards": [
                        {
                            "family": "AISC 341",
                            "canonical_designation": "ANSI/AISC 341-22",
                            "accepted_designations": [
                                "AISC 341-22",
                                "ANSI/AISC 341-22",
                            ],
                            "current_publication": True,
                            "fulltext_processing_policy": "rights-attestation-required",
                        },
                        {
                            "family": "ASCE/SEI 7",
                            "canonical_designation": "ASCE/SEI 7-22",
                            "accepted_designations": ["ASCE 7-22", "ASCE/SEI 7-22"],
                            "current_publication": True,
                            "fulltext_processing_policy": "permission-required",
                        },
                    ],
                    "families_requiring_part_or_local_adoption": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def prepare_targeted(self, pass_id, name=None):
        return prepare_evidence_spine(
            self.manuscript,
            self.root / (name or f"spine-{pass_id}"),
            mode="targeted",
            required_passes=[pass_id],
        )

    def result_envelope(self, prepared, pass_id, **values):
        payload = {
            "schema_version": "contract-test",
            "pass_id": pass_id,
            "provenance": {
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                "input_fingerprint": prepared["manifest"]["input_fingerprint"],
            },
            "sources": list(prepared["ledger"]["sources"]),
            "findings": [],
        }
        payload.update(values)
        return payload

    def record_completed(self, prepared, pass_id, payload, name):
        result_path = self.write_json(f"{name}-result.json", payload)
        coverage_path = self.root / f"{name}-coverage.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id=pass_id,
            status="completed",
            result_path=result_path,
            reviewer=f"{pass_id}-reviewer",
        )
        return coverage_path

    def finalize(self, prepared, coverage_path, name):
        return adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / name,
        )

    def source_map(self, name, *, designation, **overrides):
        row = {
            "designation": designation,
            "path": self.standard_source.name,
            "processing_mode": "local-deterministic",
            "rights_attested": True,
        }
        row.update(overrides)
        return self.write_json(
            name,
            {
                "schema_version": "0.2.0",
                "sources": [row],
            },
        )

    def assert_prepare_rejected_before_standard_read(
        self,
        *,
        source_map,
        manuscript=None,
        output_name,
    ):
        target = self.standard_source.resolve()
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.resolve(strict=False) == target:
                raise AssertionError(
                    "standard full text was opened before its rights gate passed"
                )
            return original_open(path, *args, **kwargs)

        output = self.root / output_name
        with mock.patch.object(Path, "open", guarded_open):
            with self.assertRaises(EvidenceSpineError):
                prepare_evidence_spine(
                    manuscript or self.manuscript,
                    output,
                    mode="targeted",
                    required_passes=["engineering_standards"],
                    standards_source_map=source_map,
                    standards_registry=self.registry,
                )
        self.assertFalse((output / "artifact-manifest.json").exists())


class StandardRightsGateContracts(EvidenceSpineContractTestCase):
    def test_rights_attested_false_fails_before_standard_is_read_or_hashed(self):
        source_map = self.source_map(
            "rights-false.json",
            designation="ANSI/AISC 341-22",
            rights_attested=False,
        )
        self.assert_prepare_rejected_before_standard_read(
            source_map=source_map,
            output_name="rights-false-output",
        )

    def test_asce_without_permission_reference_fails_before_read_or_hash(self):
        manuscript = self.root / "asce-paper.md"
        manuscript.write_text(
            "Methods\nThe design followed ASCE/SEI 7-22, Section 12.8.\n",
            encoding="utf-8",
        )
        source_map = self.source_map(
            "asce-no-permission.json",
            designation="ASCE/SEI 7-22",
            permission_reference="",
        )
        self.assert_prepare_rejected_before_standard_read(
            source_map=source_map,
            manuscript=manuscript,
            output_name="asce-no-permission-output",
        )

    def test_non_local_deterministic_mode_fails_before_read_or_hash(self):
        source_map = self.source_map(
            "wrong-mode.json",
            designation="ANSI/AISC 341-22",
            processing_mode="manual-browser",
        )
        self.assert_prepare_rejected_before_standard_read(
            source_map=source_map,
            output_name="wrong-mode-output",
        )

    def test_bare_standard_source_artifact_is_rejected_before_read_or_hash(self):
        target = self.standard_source.resolve()
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.resolve(strict=False) == target:
                raise AssertionError(
                    "bare standard_source was opened before being rejected"
                )
            return original_open(path, *args, **kwargs)

        output = self.root / "bare-standard-output"
        with mock.patch.object(Path, "open", guarded_open):
            with self.assertRaises(EvidenceSpineError):
                prepare_evidence_spine(
                    self.manuscript,
                    output,
                    mode="targeted",
                    required_passes=["engineering_standards"],
                    additional_artifacts=[
                        ("standard_source", self.standard_source),
                    ],
                )
        self.assertFalse((output / "artifact-manifest.json").exists())


class StandardsFindingContracts(EvidenceSpineContractTestCase):
    def test_authorized_standard_source_can_support_a_provision_finding(self):
        source_map = self.source_map(
            "authorized-aisc.json",
            designation="ANSI/AISC 341-22",
        )
        prepared = prepare_evidence_spine(
            self.manuscript,
            self.root / "authorized-standard-spine",
            mode="targeted",
            required_passes=["engineering_standards"],
            standards_source_map=source_map,
            standards_registry=self.registry,
        )
        standard_artifact = next(
            item
            for item in prepared["manifest"]["artifacts"]
            if item["role"] == "standard_source"
        )
        self.assertEqual("allowed", standard_artifact["authorization"]["gate_status"])
        finding = {
            "id": "STD-AUTHORIZED-001",
            "category": "standard",
            "check_id": "standard-provision-limit-mismatch",
            "severity": "Minor",
            "confidence": 0.95,
            "status": "confirmed",
            "standard": "ANSI/AISC 341-22",
            "location": {
                "source": "paper.md",
                "line": 2,
                "section": "Methods",
            },
            "quote": "The design followed ANSI/AISC 341-22, including provision E3.4.",
            "observation": "The manuscript application exceeds the stated provision scope.",
            "expected": "The application should remain within the authorized provision scope.",
            "reason": "The exact source passage states a narrower scope.",
            "evidence": [
                {
                    "class": "A",
                    "location": {"line": 2},
                    "quote": "Provision E3.4 applies only within the stated scope.",
                }
            ],
            "suggested_fix": "Revise the application or explain why the provision remains applicable.",
            "auto_fixable": False,
        }
        payload = self.result_envelope(
            prepared,
            "engineering_standards",
            findings=[finding],
            review_tasks=[],
            summary={"finding_count": 1, "clause_review_task_count": 0},
        )
        result_path = self.write_json("authorized-standard-result.json", payload)
        coverage_path = self.root / "authorized-standard-coverage.json"
        record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            coverage_path,
            pass_id="engineering_standards",
            status="completed",
            result_path=result_path,
            reviewer="standards-reviewer",
            capability_updates={"standard_text": "available"},
        )
        result = self.finalize(
            prepared,
            coverage_path,
            "authorized-standard-final",
        )

        self.assertEqual(1, len(result["findings"]))
    def test_non_metadata_standard_finding_requires_authorized_standard_text(self):
        prepared = self.prepare_targeted("engineering_standards")
        manuscript_quote = (
            "The design followed ANSI/AISC 341-22, including provision E3.4."
        )
        finding = {
            "id": "STD-CONTRACT-001",
            "category": "standard",
            "check_id": "standard-provision-limit-mismatch",
            "severity": "Minor",
            "confidence": 0.95,
            "status": "confirmed",
            "location": {
                "source": "paper.md",
                "line": 2,
                "section": "Methods",
            },
            "quote": manuscript_quote,
            "observation": "The manuscript exceeds a provision limit.",
            "expected": "The application should remain within the exact provision.",
            "reason": "A provision-level conclusion requires exact authorized text.",
            "evidence": [{"class": "A", "source": "manuscript"}],
            "suggested_fix": "Verify the exact edition, provision, and limit.",
            "auto_fixable": False,
        }
        payload = self.result_envelope(
            prepared,
            "engineering_standards",
            findings=[finding],
        )
        coverage_path = self.record_completed(
            prepared,
            "engineering_standards",
            payload,
            "standard-capability",
        )
        result = self.finalize(prepared, coverage_path, "standard-capability-final")

        self.assertEqual([], result["findings"])
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])
        manual = next(
            item for item in result["manual_checks"] if item["id"] == finding["id"]
        )
        reasons = manual["adjudication"]["reasons"]
        self.assertIn("missing_capability:standard_text", reasons)
        self.assertIn("missing_direct_artifact:standard_source", reasons)


class PassResultContracts(EvidenceSpineContractTestCase):
    def test_completed_pass_rejects_an_empty_result_envelope(self):
        prepared = self.prepare_targeted("deterministic_text")
        empty = self.result_envelope(prepared, "deterministic_text")
        result_path = self.write_json("empty-completed.json", empty)

        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / "empty-completed-coverage.json",
                pass_id="deterministic_text",
                status="completed",
                result_path=result_path,
            )

    def test_not_applicable_rejects_missing_or_malformed_inventory(self):
        prepared = self.prepare_targeted("claim_support")
        cases = (
            ("missing", {}),
            (
                "non-object",
                {"inventory": []},
            ),
            (
                "empty-scope",
                {"inventory": {"scope": "", "item_count": 0, "items": []}},
            ),
            (
                "nonzero-count",
                {
                    "inventory": {
                        "scope": "in-text citations",
                        "item_count": 1,
                        "items": [],
                    }
                },
            ),
            (
                "items-not-empty",
                {
                    "inventory": {
                        "scope": "in-text citations",
                        "item_count": 0,
                        "items": [{"citation": "[1]"}],
                    }
                },
            ),
        )
        for label, extra in cases:
            with self.subTest(label=label):
                payload = self.result_envelope(
                    prepared,
                    "claim_support",
                    **extra,
                )
                result_path = self.write_json(f"na-{label}.json", payload)
                with self.assertRaises(EvidenceSpineError):
                    record_pass(
                        prepared["paths"]["coverage"],
                        prepared["paths"]["ledger"],
                        self.root / f"na-{label}-coverage.json",
                        pass_id="claim_support",
                        status="not_applicable",
                        result_path=result_path,
                        rationale="A current citation inventory found no citations.",
                        reviewer="citation-inventory",
                    )

    def test_not_applicable_accepts_machine_verifiable_empty_inventory(self):
        prepared = self.prepare_targeted("claim_support")
        payload = self.result_envelope(
            prepared,
            "claim_support",
            inventory={
                "scope": "in-text citations in the complete manuscript",
                "item_count": 0,
                "items": [],
            },
        )
        result_path = self.write_json("na-valid.json", payload)
        output = self.root / "na-valid-coverage.json"

        updated = record_pass(
            prepared["paths"]["coverage"],
            prepared["paths"]["ledger"],
            output,
            pass_id="claim_support",
            status="not_applicable",
            result_path=result_path,
            rationale="A current citation inventory found no citations.",
            reviewer="citation-inventory",
        )

        record = next(
            item
            for item in updated["passes"]
            if item["pass_id"] == "claim_support"
        )
        self.assertEqual("not_applicable", record["status"])
        self.assertEqual(0, record["result"]["inventory"]["item_count"])


class UnresolvedEvidenceProjectionContracts(EvidenceSpineContractTestCase):
    def test_priority_claim_unable_to_verify_enters_manual_checks(self):
        prepared = self.prepare_targeted("claim_support")
        claim = {
            "id": "CLM-UNABLE-001",
            "claim": "The tested frame reduced peak drift by 20% [1].",
            "priority": True,
            "location": {
                "source": "paper.md",
                "line": 4,
                "section": "Results",
            },
            "references": [
                {
                    "citation_key": "Smith2021",
                    "assessment_status": "assessed",
                    "verdict": "unable_to_verify",
                    "confidence": 0.0,
                    "rationale": "The cited full text was not available.",
                    "source_access": {"status": "missing"},
                    "dimension_matches": {},
                    "selected_evidence": [],
                }
            ],
            "overall_verdict": "unable_to_verify",
        }
        payload = self.result_envelope(
            prepared,
            "claim_support",
            stage="finalized",
            claims=[claim],
            formal_findings=[],
            summary={
                "review_completed": True,
                "claim_count": 1,
                "reference_assessment_count": 1,
                "by_reference_verdict": {"unable_to_verify": 1},
                "formal_finding_count": 0,
            },
        )
        coverage_path = self.record_completed(
            prepared,
            "claim_support",
            payload,
            "claim-unable",
        )
        result = self.finalize(prepared, coverage_path, "claim-unable-final")

        rendered = json.dumps(result["manual_checks"], ensure_ascii=False)
        self.assertIn("CLM-UNABLE-001", rendered)
        self.assertIn("Smith2021", rendered)
        self.assertIn("unable_to_verify", rendered)
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])

    def test_blocked_standard_review_task_enters_manual_checks(self):
        prepared = self.prepare_targeted("engineering_standards")
        task = {
            "id": "STD-TASK-BLOCKED-001",
            "type": "standard-clause-review",
            "standard": "ASCE/SEI 7-22",
            "reference_kind": "section",
            "reference_identifier": "12.8",
            "manuscript_location": {
                "source": "paper.md",
                "line": 2,
                "section": "Methods",
            },
            "manuscript_context": (
                "The design followed ANSI/AISC 341-22, including provision E3.4."
            ),
            "evidence_status": "publisher-permission-required",
            "source_evidence": [],
            "assessment": "not_assessed",
        }
        payload = self.result_envelope(
            prepared,
            "engineering_standards",
            mentions=[],
            review_tasks=[task],
            summary={
                "review_completed": True,
                "mention_count": 0,
                "finding_count": 0,
                "clause_review_task_count": 1,
            },
        )
        coverage_path = self.record_completed(
            prepared,
            "engineering_standards",
            payload,
            "standard-task",
        )
        result = self.finalize(prepared, coverage_path, "standard-task-final")

        rendered = json.dumps(result["manual_checks"], ensure_ascii=False)
        self.assertIn("STD-TASK-BLOCKED-001", rendered)
        self.assertIn("publisher-permission-required", rendered)
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])


if __name__ == "__main__":
    unittest.main()
