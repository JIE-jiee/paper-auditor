import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from audit_manuscript import run_audit

from evidence_spine import (
    EvidenceSpineError,
    adjudicate_report,
    coverage_fingerprint,
    prepare_evidence_spine,
    record_pass,
)
from manuscript_map import manuscript_map_template, validate_manuscript_map


DRAFT_REQUIRED = {
    "deterministic_text",
    "language_tense",
    "abbreviation_terminology",
    "quantitative",
    "claim_logic",
}


class DraftModeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manuscript = self.root / "draft.md"
        self.manuscript.write_text(
            """Abstract
The proposed frame reduces residual drift.

Introduction
Residual drift delays recovery.

Methods
The frame was tested under cyclic loading.
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, name="spine"):
        return prepare_evidence_spine(
            self.manuscript,
            self.root / name,
            mode="draft",
        )

    def write_result(self, prepared, pass_id, payload=None, name=None):
        value = {
            "schema_version": "test",
            "pass_id": pass_id,
            "provenance": {
                "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                "input_fingerprint": prepared["ledger"]["input_fingerprint"],
            },
            "summary": {"review_completed": True},
            "findings": [],
        }
        if payload:
            value.update(copy.deepcopy(payload))
        path = self.root / (name or f"{pass_id}-result.json")
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def semantic_review(
        self,
        prepared,
        validation,
        *,
        scope="All manuscript material available in the current draft.",
        default_assessment=None,
        node_assessments=None,
        edge_assessments=None,
    ):
        if default_assessment is None:
            default_assessment = (
                "satisfied"
                if validation.get("argument_status") == "closed"
                else "not_yet_written"
            )
        node_assessments = node_assessments or {}
        edge_assessments = edge_assessments or {}
        return {
            "scope": scope,
            "reviewed_by": "logic-reviewer",
            "input_fingerprint": prepared["ledger"]["input_fingerprint"],
            "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
            "node_reviews": [
                {
                    "node_id": node["id"],
                    "assessment": node_assessments.get(
                        node["id"], default_assessment
                    ),
                    "rationale": "The node was semantically reviewed against the available manuscript.",
                }
                for node in validation["manuscript_map"]["nodes"]
            ],
            "edge_reviews": [
                {
                    "edge_id": edge["id"],
                    "assessment": edge_assessments.get(
                        edge["id"], default_assessment
                    ),
                    "rationale": "The connection was semantically reviewed against the available manuscript.",
                }
                for edge in validation["manuscript_map"]["edges"]
            ],
            "contract_gap_reviews": [
                {
                    "gap_index": index,
                    "gap_code": gap["code"],
                    "gap_path": gap["path"],
                    "assessment": "unresolved",
                    "rationale": "The contract gap remains open in the reviewed manuscript.",
                }
                for index, gap in enumerate(validation.get("contract_gaps", []))
            ],
        }

    def claim_logic_payload(self, prepared, *, include_work_items=True):
        map_payload = manuscript_map_template("draft")
        card = map_payload["manuscript_map"]["card"]
        card["target_journal"] = "Engineering Structures"
        card["article_type"] = "Research article"
        card["research_question"] = "Can the frame reduce residual drift?"
        card["central_message"] = "The draft tests a bounded residual-drift claim."
        card["scope_boundaries"] = ["cyclic loading", "single frame configuration"]
        validation = validate_manuscript_map(
            map_payload,
            ledger=prepared["ledger"],
            completion="draft",
        )
        value = {
            "semantic_audit_status": "completed",
            "manuscript_map_validation": validation,
            "semantic_review": self.semantic_review(prepared, validation),
        }
        if include_work_items:
            value["questions_for_author"] = [
                {
                    "id": "Q-001",
                    "node_ids": ["GAP-001"],
                    "question": "Which recovery decision is limited by residual drift?",
                    "why_it_matters": "It bounds the research gap.",
                    "needed_evidence_or_decision": "State the intended decision and scope.",
                }
            ]
            value["next_writing_tasks"] = [
                {
                    "id": "TASK-001",
                    "depends_on": [],
                    "task": "Bound the research gap.",
                    "why_now": "The objective depends on it.",
                    "completion_evidence": "An anchored gap statement.",
                },
                {
                    "id": "TASK-002",
                    "depends_on": ["TASK-001"],
                    "task": "Connect the objective to the cyclic test.",
                    "why_now": "The result chain needs a declared method.",
                    "completion_evidence": "A mapped objective-method edge.",
                },
            ]
        return value

    def record_all(self, prepared, claim_logic_payload):
        coverage_path = prepared["paths"]["coverage"]
        for index, pass_id in enumerate(sorted(DRAFT_REQUIRED), start=1):
            payload = claim_logic_payload if pass_id == "claim_logic" else None
            result_path = self.write_result(
                prepared,
                pass_id,
                payload,
                name=f"{index:02d}-{pass_id}.json",
            )
            next_coverage = self.root / f"coverage-{index:02d}.json"
            record_pass(
                coverage_path,
                prepared["paths"]["ledger"],
                next_coverage,
                pass_id=pass_id,
                status="completed",
                result_path=result_path,
                reviewer=(
                    "logic-reviewer" if pass_id == "claim_logic" else ""
                ),
            )
            coverage_path = next_coverage
        return coverage_path

    def complete_map_validation(self, prepared, *, unresolved=False):
        payload = manuscript_map_template("complete")
        card = payload["manuscript_map"]["card"]
        card["target_journal"] = "Engineering Structures"
        card["article_type"] = "Research article"
        card["research_question"] = "Can the frame reduce residual drift?"
        card["central_message"] = "The cyclic test bounds the residual-drift claim."
        card["scope_boundaries"] = [
            "cyclic loading",
            "single frame configuration",
        ]
        evidence_id = prepared["ledger"]["evidence"][0]["evidence_id"]
        for node in payload["manuscript_map"]["nodes"]:
            node["status"] = "verified"
            node["summary"] = f"Verified {node['role']} function."
            node["evidence_ids"] = [evidence_id]
        unresolved_edge_id = None
        for edge in payload["manuscript_map"]["edges"]:
            edge["status"] = "verified"
            edge["rationale"] = "The linked functions were checked in both directions."
            edge["evidence_ids"] = [evidence_id]
            if unresolved and edge["relation"] == "produces":
                edge["status"] = "needs_review"
                unresolved_edge_id = edge["id"]
        validation = validate_manuscript_map(
            payload,
            ledger=prepared["ledger"],
            completion="complete",
        )
        self.assertEqual("valid", validation["status"])
        if unresolved:
            self.assertEqual("unresolved", validation["argument_status"])
            self.assertTrue(validation["contract_gaps"])
        else:
            self.assertEqual("closed", validation["argument_status"])
        return validation, unresolved_edge_id

    def deep_claim_logic_payload(self, prepared, *, findings=None):
        validation, unresolved_edge_id = self.complete_map_validation(
            prepared,
            unresolved=True,
        )
        return {
            "semantic_audit_status": "completed",
            "manuscript_map_validation": validation,
            "semantic_review": self.semantic_review(
                prepared,
                validation,
                scope="The complete manuscript and every mapped functional connection.",
                default_assessment="satisfied",
                edge_assessments={unresolved_edge_id: "unresolved"},
            ),
            "questions_for_author": [],
            "next_writing_tasks": [],
            "findings": copy.deepcopy(findings or []),
        }

    def record_deep(self, prepared, claim_payload, *, prefix):
        coverage_path = prepared["paths"]["coverage"]
        required_passes = [
            item["pass_id"]
            for item in prepared["coverage"]["passes"]
            if item["required"]
        ]
        always_run = {
            "deterministic_text",
            "language_tense",
            "abbreviation_terminology",
            "quantitative",
            "claim_logic",
        }
        for index, pass_id in enumerate(required_passes, start=1):
            status = "completed" if pass_id in always_run else "not_applicable"
            payload = claim_payload if pass_id == "claim_logic" else None
            if status == "not_applicable":
                payload = {
                    "inventory": {
                        "scope": f"Complete-manuscript inventory for {pass_id}",
                        "item_count": 0,
                        "items": [],
                    }
                }
            result_path = self.write_result(
                prepared,
                pass_id,
                payload,
                name=f"{prefix}-{index:02d}-{pass_id}.json",
            )
            next_coverage = self.root / f"{prefix}-coverage-{index:02d}.json"
            record_pass(
                coverage_path,
                prepared["paths"]["ledger"],
                next_coverage,
                pass_id=pass_id,
                status=status,
                result_path=result_path,
                rationale=(
                    "A current inventory found no applicable items."
                    if status == "not_applicable"
                    else ""
                ),
                reviewer=(
                    "logic-reviewer"
                    if pass_id == "claim_logic"
                    else f"{pass_id}-reviewer"
                ),
            )
            coverage_path = next_coverage
        return coverage_path

    def test_draft_required_passes_are_declared_and_reconstructed(self):
        prepared = self.prepare()
        required = {
            item["pass_id"]
            for item in prepared["coverage"]["passes"]
            if item["required"]
        }
        self.assertEqual(DRAFT_REQUIRED, required)

        tampered = copy.deepcopy(prepared["coverage"])
        next(
            item
            for item in tampered["passes"]
            if item["pass_id"] == "claim_logic"
        )["required"] = False
        tampered["coverage_fingerprint"] = coverage_fingerprint(tampered)
        tampered_path = self.root / "coverage-tampered.json"
        tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaises(EvidenceSpineError):
            adjudicate_report(
                prepared["paths"]["manifest"],
                prepared["paths"]["ledger"],
                tampered_path,
                self.root / "tampered-final",
            )

    def test_clean_partial_draft_is_projected_but_never_submission_ready(self):
        prepared = self.prepare()
        coverage_path = self.record_all(
            prepared,
            self.claim_logic_payload(prepared),
        )
        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / "final",
        )

        self.assertEqual("complete", result["review_status"])
        self.assertEqual("draft_in_progress", result["submission_readiness"])
        self.assertNotEqual("ready_given_evidence", result["submission_readiness"])
        validation = result["manuscript_map_validation"]
        self.assertEqual("valid", validation["status"])
        self.assertEqual(
            "structure_and_evidence_binding",
            validation["validation_scope"],
        )
        self.assertEqual(
            prepared["ledger"]["ledger_fingerprint"],
            validation["provenance"]["ledger_fingerprint"],
        )
        self.assertTrue(validation["traceability_rows"])
        self.assertEqual([], result["findings"])
        self.assertEqual([], result["manual_checks"])
        self.assertEqual(1, len(result["questions_for_author"]))
        self.assertEqual(2, len(result["next_writing_tasks"]))

        report = (self.root / "final" / "review-report.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("# 论文写作导航报告", report)
        self.assertIn("## 论文主线卡", report)
        self.assertIn("The draft tests a bounded residual-drift claim.", report)
        self.assertIn("## 主线追踪", report)
        self.assertIn("GAP-001 · gap", report)
        self.assertIn("### 已满足的功能连接", report)
        self.assertIn("### 尚未解决的功能连接", report)
        self.assertIn("## 给作者的问题", report)
        self.assertIn("## 下一步写作/证据任务", report)

    def test_invalid_or_unbound_embedded_map_is_rejected_at_record_time(self):
        mutations = {
            "reported-invalid": lambda value: value.update({"status": "invalid"}),
            "structure-only": lambda value: value.update(
                {"validation_scope": "structure_only"}
            ),
            "stale-ledger": lambda value: value["provenance"].update(
                {"ledger_fingerprint": "stale-ledger"}
            ),
            "dangling-edge": lambda value: value["manuscript_map"]["edges"][0].update(
                {"to": "MISSING-001"}
            ),
        }
        for index, (name, mutate) in enumerate(mutations.items(), start=1):
            with self.subTest(name=name):
                prepared = self.prepare(f"spine-{index}")
                payload = self.claim_logic_payload(
                    prepared, include_work_items=False
                )
                mutate(payload["manuscript_map_validation"])
                result_path = self.write_result(
                    prepared,
                    "claim_logic",
                    payload,
                    name=f"invalid-{index}.json",
                )
                with self.assertRaises(EvidenceSpineError):
                    record_pass(
                        prepared["paths"]["coverage"],
                        prepared["paths"]["ledger"],
                        self.root / f"invalid-coverage-{index}.json",
                        pass_id="claim_logic",
                        status="completed",
                        result_path=result_path,
                        reviewer="logic-reviewer",
                    )

    def test_structural_validator_cannot_impersonate_semantic_claim_review(self):
        prepared = self.prepare()
        payload = self.claim_logic_payload(prepared, include_work_items=False)
        payload.pop("semantic_audit_status")
        result_path = self.write_result(
            prepared,
            "claim_logic",
            payload,
            name="validator-only.json",
        )
        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / "validator-only-coverage.json",
                pass_id="claim_logic",
                status="completed",
                result_path=result_path,
                reviewer="logic-reviewer",
            )


    def test_explicitly_planned_callouts_remain_tasks_not_defects(self):
        self.manuscript.write_text(
            """Experimental program
The specimen geometry and loading sequence are being finalized for Table 1.
Figure 3 will compare the measured and simulated responses.
""",
            encoding="utf-8",
        )
        prepared = self.prepare("planned-spine")
        deterministic_dir = self.root / "planned-deterministic"
        deterministic = run_audit(
            self.manuscript,
            deterministic_dir,
            manuscript_stage="draft",
        )
        self.assertEqual([], deterministic["findings"])
        self.assertEqual(2, len(deterministic["planned_items"]))
        source_text = " ".join(
            self.manuscript.read_text(encoding="utf-8").split()
        ).casefold()
        self.assertTrue(
            all(
                " ".join(item["quote"].split()).casefold() in source_text
                for item in deterministic["planned_items"]
            )
        )

        claim_logic = self.claim_logic_payload(prepared)
        coverage_path = prepared["paths"]["coverage"]
        for index, pass_id in enumerate(sorted(DRAFT_REQUIRED), start=1):
            if pass_id == "deterministic_text":
                result_path = deterministic_dir / "findings.json"
            else:
                payload = claim_logic if pass_id == "claim_logic" else None
                result_path = self.write_result(
                    prepared,
                    pass_id,
                    payload,
                    name=f"planned-{index:02d}-{pass_id}.json",
                )
            next_coverage = self.root / f"planned-coverage-{index:02d}.json"
            record_pass(
                coverage_path,
                prepared["paths"]["ledger"],
                next_coverage,
                pass_id=pass_id,
                status="completed",
                result_path=result_path,
                reviewer=(
                    "logic-reviewer" if pass_id == "claim_logic" else ""
                ),
            )
            coverage_path = next_coverage

        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / "planned-final",
        )
        self.assertEqual("complete", result["review_status"])
        self.assertEqual("draft_in_progress", result["submission_readiness"])
        self.assertEqual([], result["findings"])
        self.assertEqual([], result["manual_checks"])
        self.assertEqual(2, result["summary"]["draft_planned_item_count"])
        self.assertEqual(
            {
                "crossref-callout-planned-target",
            },
            {item["check_id"] for item in result["draft_planned_items"]},
        )
        self.assertTrue(
            all(item["evidence_ids"] for item in result["draft_planned_items"])
        )
        report = (self.root / "planned-final" / "review-report.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## 草稿计划项（尚未完成，不是缺陷）", report)
        self.assertIn("Table 1", report)
        self.assertIn("Figure 3", report)

    def test_planned_items_cannot_hide_missing_targets_in_deep_mode(self):
        self.manuscript.write_text(
            """Results
Figure 3 will compare the measured and simulated responses.
""",
            encoding="utf-8",
        )
        prepared = prepare_evidence_spine(
            self.manuscript,
            self.root / "deep-planned-spine",
            mode="deep",
        )
        deterministic_dir = self.root / "deep-planned-deterministic"
        run_audit(
            self.manuscript,
            deterministic_dir,
            manuscript_stage="draft",
        )
        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / "deep-planned-coverage.json",
                pass_id="deterministic_text",
                status="completed",
                result_path=deterministic_dir / "findings.json",
            )

    def test_deep_requires_a_semantic_envelope_and_embedded_current_map(self):
        prepared = prepare_evidence_spine(
            self.manuscript,
            self.root / "deep-spine",
            mode="deep",
        )
        raw_validation = validate_manuscript_map(
            manuscript_map_template("draft"),
            ledger=prepared["ledger"],
            completion="draft",
        )
        raw_path = self.root / "raw-validator-output.json"
        raw_path.write_text(
            json.dumps(raw_validation, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / "deep-raw-validator-coverage.json",
                pass_id="claim_logic",
                status="completed",
                result_path=raw_path,
                reviewer="logic-reviewer",
            )

        missing_map_path = self.root / "deep-missing-map.json"
        missing_map_path.write_text(
            json.dumps(
                {
                    "schema_version": "test",
                    "pass_id": "claim_logic",
                    "semantic_audit_status": "completed",
                    "provenance": {
                        "ledger_fingerprint": prepared["ledger"][
                            "ledger_fingerprint"
                        ],
                        "input_fingerprint": prepared["ledger"][
                            "input_fingerprint"
                        ],
                    },
                    "summary": {"review_completed": True},
                    "findings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with self.assertRaises(EvidenceSpineError):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.root / "deep-missing-map-coverage.json",
                pass_id="claim_logic",
                status="completed",
                result_path=missing_map_path,
                reviewer="logic-reviewer",
            )

    def test_always_applicable_core_passes_reject_not_applicable(self):
        core_passes = {
            "deterministic_text",
            "language_tense",
            "abbreviation_terminology",
            "claim_logic",
        }
        for index, pass_id in enumerate(sorted(core_passes), start=1):
            with self.subTest(pass_id=pass_id):
                prepared = prepare_evidence_spine(
                    self.manuscript,
                    self.root / f"na-core-{index}",
                    mode="targeted",
                    required_passes=[pass_id],
                )
                result_path = self.write_result(
                    prepared,
                    pass_id,
                    {
                        "inventory": {
                            "scope": "The complete current manuscript.",
                            "item_count": 0,
                            "items": [],
                        }
                    },
                    name=f"na-core-{index}.json",
                )
                with self.assertRaises(EvidenceSpineError):
                    record_pass(
                        prepared["paths"]["coverage"],
                        prepared["paths"]["ledger"],
                        self.root / f"na-core-coverage-{index}.json",
                        pass_id=pass_id,
                        status="not_applicable",
                        result_path=result_path,
                        rationale="Synthetic empty inventory.",
                        reviewer="logic-reviewer",
                    )

        prepared = self.prepare("na-reconstructed-spine")
        result_path = self.write_result(
            prepared,
            "claim_logic",
            {
                "inventory": {
                    "scope": "The current draft.",
                    "item_count": 0,
                    "items": [],
                }
            },
            name="na-reconstructed-result.json",
        )
        coverage = copy.deepcopy(prepared["coverage"])
        record = next(
            item for item in coverage["passes"]
            if item["pass_id"] == "claim_logic"
        )
        record.update(
            {
                "status": "not_applicable",
                "rationale": "Synthetic reconstructed empty inventory.",
                "ledger_binding": "native",
                "reviewer": "logic-reviewer",
                "result": {
                    "path": str(result_path),
                    "sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                    "schema_version": "test",
                    "finding_count": 0,
                    "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                    "planned_item_count": None,
                    "binding": "native",
                    "warnings": [],
                    "inventory": {
                        "scope": "The current draft.",
                        "item_count": 0,
                        "items": [],
                    },
                },
            }
        )
        coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)
        forged_path = self.root / "na-reconstructed-coverage.json"
        forged_path.write_text(json.dumps(coverage), encoding="utf-8")
        with self.assertRaises(EvidenceSpineError):
            adjudicate_report(
                prepared["paths"]["manifest"],
                prepared["paths"]["ledger"],
                forged_path,
                self.root / "na-reconstructed-final",
            )

    def test_semantic_review_requires_exact_map_coverage_and_current_binding(self):
        def missing_node(value):
            value["semantic_review"]["node_reviews"].pop()

        def extra_edge(value):
            value["semantic_review"]["edge_reviews"].append(
                {
                    "edge_id": "EDGE-UNKNOWN",
                    "assessment": "unresolved",
                    "rationale": "Synthetic extra edge.",
                }
            )

        def duplicate_node(value):
            value["semantic_review"]["node_reviews"].append(
                copy.deepcopy(value["semantic_review"]["node_reviews"][0])
            )

        def stale_semantic_ledger(value):
            value["semantic_review"]["ledger_fingerprint"] = "stale-ledger"

        def mismatched_reviewer(value):
            value["semantic_review"]["reviewed_by"] = "different-reviewer"

        def unresolved_marked_satisfied(value):
            for key in ("node_reviews", "edge_reviews"):
                for item in value["semantic_review"][key]:
                    item["assessment"] = "satisfied"

        mutations = {
            "missing-node": missing_node,
            "extra-edge": extra_edge,
            "duplicate-node": duplicate_node,
            "stale-ledger": stale_semantic_ledger,
            "reviewer-mismatch": mismatched_reviewer,
            "unresolved-all-satisfied": unresolved_marked_satisfied,
        }
        for index, (name, mutate) in enumerate(mutations.items(), start=1):
            with self.subTest(name=name):
                prepared = self.prepare(f"semantic-contract-{index}")
                payload = self.claim_logic_payload(
                    prepared,
                    include_work_items=False,
                )
                mutate(payload)
                result_path = self.write_result(
                    prepared,
                    "claim_logic",
                    payload,
                    name=f"semantic-contract-{index}.json",
                )
                with self.assertRaises(EvidenceSpineError):
                    record_pass(
                        prepared["paths"]["coverage"],
                        prepared["paths"]["ledger"],
                        self.root / f"semantic-contract-coverage-{index}.json",
                        pass_id="claim_logic",
                        status="completed",
                        result_path=result_path,
                        reviewer="logic-reviewer",
                    )

    def test_shallow_semantic_wrapper_is_rejected_during_reconstruction(self):
        prepared = self.prepare("shallow-reconstruction-spine")
        legal_payload = self.claim_logic_payload(prepared)
        coverage_path = self.record_all(prepared, legal_payload)
        shallow_payload = copy.deepcopy(legal_payload)
        shallow_payload.pop("semantic_review")
        shallow_result = self.write_result(
            prepared,
            "claim_logic",
            shallow_payload,
            name="shallow-reconstruction-result.json",
        )
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        claim_record = next(
            item for item in coverage["passes"]
            if item["pass_id"] == "claim_logic"
        )
        claim_record["result"]["path"] = str(shallow_result)
        claim_record["result"]["sha256"] = hashlib.sha256(
            shallow_result.read_bytes()
        ).hexdigest()
        coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)
        forged_path = self.root / "shallow-reconstruction-coverage.json"
        forged_path.write_text(json.dumps(coverage), encoding="utf-8")

        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            forged_path,
            self.root / "shallow-reconstruction-final",
        )
        self.assertEqual("incomplete", result["review_status"])
        self.assertEqual(
            "manual_confirmation_required",
            result["submission_readiness"],
        )
        self.assertTrue(
            any(
                item.startswith("invalid_pass_result_contract:claim_logic:")
                for item in result["diagnostics"]
            )
        )

    def test_fake_planned_items_without_target_or_future_are_rejected(self):
        self.manuscript.write_text(
            "Results\nFigure 3 will compare measured and simulated responses.\n",
            encoding="utf-8",
        )
        prepared = self.prepare("fake-planned-spine")
        deterministic_dir = self.root / "fake-planned-deterministic"
        deterministic = run_audit(
            self.manuscript,
            deterministic_dir,
            manuscript_stage="draft",
        )
        self.assertEqual(1, len(deterministic["planned_items"]))
        fake_quotes = {
            "missing-target": "The target will be prepared.",
            "missing-future": "Figure 3 compares measured and simulated responses.",
        }
        for index, (name, quote) in enumerate(fake_quotes.items(), start=1):
            with self.subTest(name=name):
                payload = copy.deepcopy(deterministic)
                payload["planned_items"][0]["quote"] = quote
                result_path = self.root / f"fake-planned-{index}.json"
                result_path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                with self.assertRaises(EvidenceSpineError):
                    record_pass(
                        prepared["paths"]["coverage"],
                        prepared["paths"]["ledger"],
                        self.root / f"fake-planned-coverage-{index}.json",
                        pass_id="deterministic_text",
                        status="completed",
                        result_path=result_path,
                    )

    def test_deep_unresolved_map_never_ready_and_report_lists_gaps(self):
        prepared = prepare_evidence_spine(
            self.manuscript,
            self.root / "deep-unresolved-spine",
            mode="deep",
        )
        coverage_path = self.record_deep(
            prepared,
            self.deep_claim_logic_payload(prepared),
            prefix="deep-unresolved",
        )
        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / "deep-unresolved-final",
        )
        self.assertEqual("complete", result["review_status"])
        self.assertEqual(
            "manual_confirmation_required",
            result["submission_readiness"],
        )
        self.assertEqual("valid", result["summary"]["manuscript_map_status"])
        self.assertEqual(
            "unresolved",
            result["summary"]["manuscript_argument_status"],
        )
        self.assertGreater(
            result["summary"]["manuscript_contract_gap_count"],
            0,
        )
        gap = result["manuscript_map_validation"]["contract_gaps"][0]
        report = (self.root / "deep-unresolved-final" / "review-report.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("地图契约状态：`valid`", report)
        self.assertIn("论证闭环状态：`unresolved`", report)
        self.assertIn("### 论证契约缺口", report)
        self.assertIn(gap["code"], report)
        self.assertIn(gap["path"], report)
        self.assertIn(gap["message"], report)

    def test_deep_unresolved_map_with_accepted_finding_requires_revision(self):
        prepared = prepare_evidence_spine(
            self.manuscript,
            self.root / "deep-unresolved-finding-spine",
            mode="deep",
        )
        finding = {
            "id": "LOGIC-001",
            "category": "logic",
            "check_id": "method-result-gap",
            "severity": "Minor",
            "confidence": 0.95,
            "status": "confirmed",
            "location": {
                "source": self.manuscript.name,
                "line": 8,
                "section": "Methods",
                "scope": "body",
            },
            "quote": "The frame was tested under cyclic loading.",
            "observation": "The mapped method-result connection remains unresolved.",
            "expected": "Every outcome-producing method has a traceable result.",
            "reason": "The current manuscript does not close the mapped connection.",
            "evidence": [],
            "suggested_fix": "Add the corresponding result or narrow the method claim.",
            "auto_fixable": False,
        }
        coverage_path = self.record_deep(
            prepared,
            self.deep_claim_logic_payload(prepared, findings=[finding]),
            prefix="deep-unresolved-finding",
        )
        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / "deep-unresolved-finding-final",
        )
        self.assertEqual("complete", result["review_status"])
        self.assertEqual("revision_required", result["submission_readiness"])
        self.assertEqual(["LOGIC-001"], [item["id"] for item in result["findings"]])

    def test_draft_with_accepted_formal_finding_requires_revision(self):
        prepared = self.prepare("draft-formal-spine")
        payload = self.claim_logic_payload(prepared)
        payload["findings"] = [
            {
                "id": "DRAFT-LOGIC-001",
                "category": "logic",
                "check_id": "objective-method-gap",
                "severity": "Minor",
                "confidence": 0.95,
                "status": "confirmed",
                "location": {
                    "source": self.manuscript.name,
                    "line": 8,
                    "section": "Methods",
                    "scope": "body",
                },
                "quote": "The frame was tested under cyclic loading.",
                "observation": "The current objective-method link is inconsistent.",
                "expected": "The objective and method should be traceable.",
                "reason": "The anchored draft text supports a formal logic issue.",
                "evidence": [],
                "suggested_fix": "Align the objective with the implemented method.",
                "auto_fixable": False,
            }
        ]
        coverage_path = self.record_all(prepared, payload)
        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / "draft-formal-final",
        )
        self.assertEqual("complete", result["review_status"])
        self.assertEqual("revision_required", result["submission_readiness"])
        self.assertEqual(
            ["DRAFT-LOGIC-001"],
            [item["id"] for item in result["findings"]],
        )

    def test_planned_quote_superset_injection_is_rejected_end_to_end(self):
        original_line = "Figure 3 will compare measured and simulated responses."
        self.manuscript.write_text(original_line + "\n", encoding="utf-8")
        prepared = self.prepare("planned-superset-spine")
        deterministic_dir = self.root / "planned-superset-deterministic"
        deterministic = run_audit(
            self.manuscript,
            deterministic_dir,
            manuscript_stage="draft",
        )
        self.assertEqual(1, len(deterministic["planned_items"]))

        injected = copy.deepcopy(deterministic)
        planned = injected["planned_items"][0]
        planned["quote"] = original_line + " Figure 999 will be prepared."
        planned["target"] = {"kind": "figure", "identifier": "999"}
        injected_path = self.root / "planned-superset-result.json"
        injected_path.write_text(
            json.dumps(injected, ensure_ascii=False),
            encoding="utf-8",
        )

        claim_logic = self.claim_logic_payload(prepared)
        coverage_path = prepared["paths"]["coverage"]
        for index, pass_id in enumerate(sorted(DRAFT_REQUIRED), start=1):
            if pass_id == "deterministic_text":
                result_path = injected_path
            else:
                payload = claim_logic if pass_id == "claim_logic" else None
                result_path = self.write_result(
                    prepared,
                    pass_id,
                    payload,
                    name=f"planned-superset-{index:02d}-{pass_id}.json",
                )
            next_coverage = self.root / (
                f"planned-superset-coverage-{index:02d}.json"
            )
            record_pass(
                coverage_path,
                prepared["paths"]["ledger"],
                next_coverage,
                pass_id=pass_id,
                status="completed",
                result_path=result_path,
                reviewer=(
                    "logic-reviewer" if pass_id == "claim_logic" else ""
                ),
            )
            coverage_path = next_coverage

        result = adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / "planned-superset-final",
        )
        self.assertEqual("incomplete", result["review_status"])
        self.assertEqual(
            "manual_confirmation_required",
            result["submission_readiness"],
        )
        self.assertEqual([], result["draft_planned_items"])
        self.assertTrue(
            any(
                "planned_quote_not_found_near_locator" in item
                for item in result["diagnostics"]
            )
        )

    def test_semantic_scope_and_rationales_require_native_strings(self):
        invalid_values = ([], {"not": "text"}, None)
        draft_mutations = {
            "scope": lambda review, value: review.update({"scope": value}),
            "node-rationale": lambda review, value: review["node_reviews"][0].update(
                {"rationale": value}
            ),
            "edge-rationale": lambda review, value: review["edge_reviews"][0].update(
                {"rationale": value}
            ),
        }
        case_number = 0
        for field, mutate in draft_mutations.items():
            for invalid in invalid_values:
                case_number += 1
                with self.subTest(field=field, invalid_type=type(invalid).__name__):
                    prepared = self.prepare(f"semantic-string-{case_number}")
                    payload = self.claim_logic_payload(
                        prepared,
                        include_work_items=False,
                    )
                    mutate(payload["semantic_review"], invalid)
                    result_path = self.write_result(
                        prepared,
                        "claim_logic",
                        payload,
                        name=f"semantic-string-{case_number}.json",
                    )
                    with self.assertRaises(EvidenceSpineError):
                        record_pass(
                            prepared["paths"]["coverage"],
                            prepared["paths"]["ledger"],
                            self.root / f"semantic-string-coverage-{case_number}.json",
                            pass_id="claim_logic",
                            status="completed",
                            result_path=result_path,
                            reviewer="logic-reviewer",
                        )

        for invalid in invalid_values:
            case_number += 1
            with self.subTest(
                field="contract-gap-rationale",
                invalid_type=type(invalid).__name__,
            ):
                prepared = prepare_evidence_spine(
                    self.manuscript,
                    self.root / f"semantic-gap-string-{case_number}",
                    mode="deep",
                )
                payload = self.deep_claim_logic_payload(prepared)
                gap_reviews = payload["semantic_review"]["contract_gap_reviews"]
                self.assertTrue(gap_reviews)
                gap_reviews[0]["rationale"] = invalid
                result_path = self.write_result(
                    prepared,
                    "claim_logic",
                    payload,
                    name=f"semantic-gap-string-{case_number}.json",
                )
                with self.assertRaises(EvidenceSpineError):
                    record_pass(
                        prepared["paths"]["coverage"],
                        prepared["paths"]["ledger"],
                        self.root / f"semantic-gap-string-coverage-{case_number}.json",
                        pass_id="claim_logic",
                        status="completed",
                        result_path=result_path,
                        reviewer="logic-reviewer",
                    )

if __name__ == "__main__":
    unittest.main()
