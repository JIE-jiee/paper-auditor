import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_spine import ledger_fingerprint as evidence_spine_ledger_fingerprint
from manuscript_map import (
    ManuscriptMapError,
    ledger_fingerprint,
    main,
    manuscript_map_template,
    render_traceability_markdown,
    validate_manuscript_map,
    validate_to_files,
    write_template,
)


EVIDENCE_IDS = {
    "gap": "EVD-0000000000000001",
    "objective": "EVD-0000000000000002",
    "method": "EVD-0000000000000003",
    "result": "EVD-0000000000000004",
    "interpretation": "EVD-0000000000000005",
    "conclusion": "EVD-0000000000000006",
    "edge_1": "EVD-0000000000000007",
    "edge_2": "EVD-0000000000000008",
    "edge_3": "EVD-0000000000000009",
    "edge_4": "EVD-000000000000000A",
    "edge_5": "EVD-000000000000000B",
}


class ManuscriptMapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def complete_payload(self):
        payload = manuscript_map_template("complete")
        manuscript_map = payload["manuscript_map"]
        manuscript_map["card"]["central_message"] = (
            "The bounded engineering conclusion follows from the reported evidence."
        )
        for node in manuscript_map["nodes"]:
            node["status"] = "verified"
            node["summary"] = f"Reviewer-authored summary for {node['role']}."
            node["evidence_ids"] = [EVIDENCE_IDS[node["role"]]]
        for index, edge in enumerate(manuscript_map["edges"], start=1):
            edge["status"] = "verified"
            edge["rationale"] = "Reviewer-authored traceability decision."
            edge["evidence_ids"] = [EVIDENCE_IDS[f"edge_{index}"]]
        return payload

    def ledger(self):
        ledger = {
            "schema_version": "0.1.0",
            "paper_id": "PAPER-TEST",
            "input_fingerprint": "a" * 64,
            "text_mode": "excerpt",
            "evidence": [
                {"evidence_id": identifier}
                for identifier in EVIDENCE_IDS.values()
            ],
        }
        ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)
        return ledger

    def write_payload(self, payload, name="manuscript-map.json"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def test_draft_template_is_valid_without_false_completion_errors(self):
        result = validate_manuscript_map(manuscript_map_template())
        self.assertEqual("valid", result["status"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertEqual("draft", result["completion_mode"])
        self.assertFalse(result["summary"]["core_chain_complete"])
        self.assertEqual(0, result["summary"]["contract_gap_count"])
        self.assertEqual([], result["errors"])
        self.assertEqual([], result["warnings"])
        self.assertFalse(result["summary"]["semantic_audit_completed"])

    def test_complete_chain_and_ledger_binding_are_valid(self):
        result = validate_manuscript_map(
            self.complete_payload(), ledger=self.ledger()
        )
        self.assertEqual("valid", result["status"])
        self.assertEqual("closed", result["argument_status"])
        self.assertTrue(result["summary"]["core_chain_complete"])
        self.assertEqual([], result["contract_gaps"])
        self.assertEqual(
            "verified", result["summary"]["ledger_binding_status"]
        )
        self.assertEqual(
            len(EVIDENCE_IDS),
            result["summary"]["verified_evidence_reference_count"],
        )
        self.assertEqual(
            "not_performed_by_validator", result["semantic_audit_status"]
        )

    def test_complete_mode_requires_an_actual_continuous_core_chain(self):
        payload = self.complete_payload()
        payload["manuscript_map"]["edges"][2]["status"] = "planned"
        result = validate_manuscript_map(payload, ledger=self.ledger())
        codes = {item["code"] for item in result["contract_gaps"]}
        self.assertEqual("valid", result["status"])
        self.assertEqual([], result["errors"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertIn("complete_core_chain_missing", codes)
        self.assertIn("method_without_result", codes)
        self.assertGreater(result["summary"]["contract_gap_count"], 0)
        markdown = render_traceability_markdown(result)
        self.assertIn("Argument closure gaps", markdown)
        self.assertIn("method_without_result", markdown)

    def test_complete_core_statuses_and_evidence_are_fail_closed(self):
        payload = self.complete_payload()
        payload["manuscript_map"]["nodes"][2]["status"] = "needs_review"
        payload["manuscript_map"]["edges"][2]["status"] = "mapped"
        payload["manuscript_map"]["edges"][2]["evidence_ids"] = []
        result = validate_manuscript_map(payload, ledger=self.ledger())
        codes = {item["code"] for item in result["contract_gaps"]}
        self.assertEqual("valid", result["status"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertIn("critical_node_needs_review", codes)
        self.assertIn("unverified_complete_core_edge", codes)
        self.assertIn("core_edge_without_evidence", codes)
        self.assertIn("complete_core_chain_missing", codes)
        self.assertFalse(result["summary"]["core_chain_complete"])

    def test_complete_accepts_each_explicit_entry_role_as_an_alternative(self):
        for entry_role in ("research_question", "objective", "hypothesis"):
            with self.subTest(entry_role=entry_role):
                payload = self.complete_payload()
                entry = payload["manuscript_map"]["nodes"][1]
                entry["role"] = entry_role
                entry["label"] = f"Declared {entry_role}"
                result = validate_manuscript_map(payload, ledger=self.ledger())
                self.assertEqual("valid", result["status"], result["errors"])
                self.assertEqual("closed", result["argument_status"])
                self.assertTrue(result["summary"]["core_chain_complete"])

    def test_planned_extra_entry_keeps_complete_argument_unresolved(self):
        payload = self.complete_payload()
        extra_objective = copy.deepcopy(payload["manuscript_map"]["nodes"][1])
        extra_objective.update(
            {
                "id": "OBJ-PLANNED",
                "label": "Additional planned objective",
                "status": "planned",
                "evidence_ids": [],
            }
        )
        payload["manuscript_map"]["nodes"].append(extra_objective)
        result = validate_manuscript_map(payload, ledger=self.ledger())
        self.assertEqual("valid", result["status"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertIn(
            "unfinished_critical_node",
            {item["code"] for item in result["contract_gaps"]},
        )

    def test_each_declared_entry_requires_its_own_method_mapping(self):
        payload = self.complete_payload()
        manuscript_map = payload["manuscript_map"]
        second_entry = copy.deepcopy(manuscript_map["nodes"][1])
        second_entry.update(
            {
                "id": "RQ-002",
                "role": "research_question",
                "label": "Second declared research question",
            }
        )
        manuscript_map["nodes"].append(second_entry)
        gap_to_entry = copy.deepcopy(manuscript_map["edges"][0])
        gap_to_entry.update(
            {
                "id": "EDGE-006",
                "to": "RQ-002",
                "rationale": "The gap motivates the second question.",
            }
        )
        manuscript_map["edges"].append(gap_to_entry)
        third_entry = copy.deepcopy(manuscript_map["nodes"][1])
        third_entry.update(
            {
                "id": "HYP-003",
                "role": "hypothesis",
                "label": "Third declared hypothesis",
            }
        )
        manuscript_map["nodes"].append(third_entry)
        entry_to_method = copy.deepcopy(manuscript_map["edges"][1])
        entry_to_method.update(
            {
                "id": "EDGE-007",
                "from": "HYP-003",
                "rationale": "A method addresses the third hypothesis.",
            }
        )
        manuscript_map["edges"].append(entry_to_method)
        result = validate_manuscript_map(payload, ledger=self.ledger())
        codes = {item["code"] for item in result["contract_gaps"]}
        self.assertIn("entry_without_method", codes)
        self.assertIn("entry_without_gap", codes)

    def test_every_verified_core_node_needs_role_specific_edges(self):
        cases = (
            ("gap", "GAP-002", "OBJ-001", ("gap_without_entry",)),
            (
                "method",
                "MTH-002",
                "OBJ-001",
                ("method_without_entry", "method_without_result"),
            ),
            (
                "result",
                "RES-002",
                "MTH-001",
                ("result_without_method", "result_without_interpretation"),
            ),
            (
                "interpretation",
                "INT-002",
                "RES-001",
                (
                    "interpretation_without_result",
                    "interpretation_without_conclusion",
                ),
            ),
            (
                "conclusion",
                "CON-002",
                "INT-001",
                ("conclusion_without_interpretation",),
            ),
        )
        for role, identifier, source_id, expected_codes in cases:
            with self.subTest(role=role):
                payload = self.complete_payload()
                manuscript_map = payload["manuscript_map"]
                original = next(
                    node for node in manuscript_map["nodes"] if node["role"] == role
                )
                extra = copy.deepcopy(original)
                extra["id"] = identifier
                extra["label"] = f"Additional {role}"
                manuscript_map["nodes"].append(extra)
                manuscript_map["edges"].append(
                    {
                        "id": "EDGE-EXTRA",
                        "from": source_id,
                        "to": identifier,
                        "relation": "aligns_with",
                        "status": "verified",
                        "rationale": "Incidental edge that must not satisfy a core mapping.",
                        "evidence_ids": [EVIDENCE_IDS["edge_1"]],
                    }
                )
                result = validate_manuscript_map(payload, ledger=self.ledger())
                codes = {item["code"] for item in result["contract_gaps"]}
                for expected_code in expected_codes:
                    self.assertIn(expected_code, codes)

    def test_visual_role_alias_is_normalized_without_mutating_the_map(self):
        payload = self.complete_payload()
        manuscript_map = payload["manuscript_map"]
        manuscript_map["nodes"].append(
            {
                "id": "VIS-001",
                "role": "visual",
                "label": "Figure 1",
                "status": "verified",
                "summary": "A reviewer-declared visual evidence node.",
                "section": "Results",
                "evidence_ids": [EVIDENCE_IDS["result"]],
            }
        )
        manuscript_map["edges"].append(
            {
                "id": "EDGE-VISUAL",
                "from": "VIS-001",
                "to": "RES-001",
                "relation": "evidences",
                "status": "verified",
                "rationale": "Figure 1 evidences the principal result.",
                "evidence_ids": [EVIDENCE_IDS["edge_1"]],
            }
        )
        before = copy.deepcopy(payload)
        result = validate_manuscript_map(payload, ledger=self.ledger())
        self.assertEqual("valid", result["status"], result["errors"])
        self.assertEqual("closed", result["argument_status"])
        self.assertEqual(before, payload)
        self.assertEqual(
            "visual",
            result["manuscript_map"]["nodes"][-1]["role"],
        )
        self.assertIn(
            "normalized_node_role",
            {item["code"] for item in result["warnings"]},
        )
        visual_row = next(
            row
            for row in result["traceability_rows"]
            if row["edge_id"] == "EDGE-VISUAL"
        )
        self.assertEqual("figure_table", visual_row["from_role"])

    def test_complete_mode_reports_unfinished_and_unmapped_core_as_gaps(self):
        payload = self.complete_payload()
        payload["manuscript_map"]["nodes"][3]["status"] = "not_yet_written"
        result = validate_manuscript_map(payload, ledger=self.ledger())
        codes = {item["code"] for item in result["contract_gaps"]}
        self.assertEqual("valid", result["status"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertIn("unfinished_critical_node", codes)
        self.assertIn("missing_active_critical_role", codes)

    def test_duplicate_ids_and_dangling_edges_are_rejected(self):
        payload = manuscript_map_template()
        payload["manuscript_map"]["nodes"][1]["id"] = "GAP-001"
        payload["manuscript_map"]["edges"][0]["to"] = "MISSING-001"
        payload["manuscript_map"]["edges"][1]["id"] = "EDGE-001"
        result = validate_manuscript_map(payload)
        self.assertEqual("invalid", result["status"])
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("duplicate_node_id", codes)
        self.assertIn("duplicate_edge_id", codes)
        self.assertIn("dangling_edge_target", codes)

    def test_role_relation_and_status_enums_are_fail_closed(self):
        payload = manuscript_map_template()
        payload["manuscript_map"]["nodes"][0]["role"] = "invented_role"
        payload["manuscript_map"]["nodes"][1]["status"] = "done"
        payload["manuscript_map"]["edges"][0]["relation"] = "proves_forever"
        payload["manuscript_map"]["edges"][1]["status"] = "finished"
        result = validate_manuscript_map(payload)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("invalid_node_role", codes)
        self.assertIn("invalid_node_status", codes)
        self.assertIn("invalid_relation", codes)
        self.assertIn("invalid_edge_status", codes)

    def test_directional_relation_role_mismatch_is_rejected(self):
        payload = manuscript_map_template()
        payload["manuscript_map"]["edges"][0]["from"] = "MTH-001"
        payload["manuscript_map"]["edges"][0]["to"] = "RES-001"
        payload["manuscript_map"]["edges"][0]["relation"] = "motivates"
        result = validate_manuscript_map(payload)
        self.assertIn(
            "relation_role_mismatch",
            {item["code"] for item in result["errors"]},
        )

    def test_unknown_evidence_id_is_rejected_when_ledger_is_provided(self):
        payload = self.complete_payload()
        payload["manuscript_map"]["nodes"][0]["evidence_ids"] = [
            "EVD-FFFFFFFFFFFFFFFF"
        ]
        result = validate_manuscript_map(payload, ledger=self.ledger())
        self.assertEqual("invalid", result["status"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertIn(
            "unknown_evidence_id", {item["code"] for item in result["errors"]}
        )
        self.assertEqual(
            "invalid", result["summary"]["ledger_binding_status"]
        )

    def test_local_ledger_fingerprint_matches_evidence_spine_projection(self):
        ledger = self.ledger()
        self.assertEqual(
            evidence_spine_ledger_fingerprint(ledger),
            ledger_fingerprint(ledger),
        )

    def test_ledger_identity_fields_are_required_and_fail_closed(self):
        missing = object()
        cases = (
            (
                "missing_schema_version",
                "schema_version",
                missing,
                "invalid_ledger_schema_version",
            ),
            (
                "incompatible_schema_version",
                "schema_version",
                "9.9.9",
                "invalid_ledger_schema_version",
            ),
            ("missing_paper_id", "paper_id", missing, "invalid_ledger_paper_id"),
            ("blank_paper_id", "paper_id", "   ", "invalid_ledger_paper_id"),
            (
                "missing_input_fingerprint",
                "input_fingerprint",
                missing,
                "invalid_ledger_input_fingerprint",
            ),
            (
                "malformed_input_fingerprint",
                "input_fingerprint",
                "not-a-sha256",
                "invalid_ledger_input_fingerprint",
            ),
            (
                "missing_text_mode",
                "text_mode",
                missing,
                "invalid_ledger_text_mode",
            ),
            (
                "invalid_text_mode",
                "text_mode",
                "full-text",
                "invalid_ledger_text_mode",
            ),
            (
                "non_string_text_mode",
                "text_mode",
                ["excerpt"],
                "invalid_ledger_text_mode",
            ),
        )
        for name, field, value, expected_code in cases:
            with self.subTest(name=name):
                ledger = self.ledger()
                if value is missing:
                    ledger.pop(field)
                else:
                    ledger[field] = value
                ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)
                result = validate_manuscript_map(
                    self.complete_payload(), ledger=ledger
                )
                self.assertEqual("invalid", result["status"])
                self.assertEqual("unresolved", result["argument_status"])
                self.assertIn(
                    expected_code,
                    {item["code"] for item in result["errors"]},
                )
                self.assertEqual(
                    "invalid", result["summary"]["ledger_binding_status"]
                )

    def test_duplicate_ledger_evidence_id_is_rejected(self):
        ledger = self.ledger()
        ledger["evidence"].append(
            {"evidence_id": ledger["evidence"][0]["evidence_id"]}
        )
        ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)
        result = validate_manuscript_map(self.complete_payload(), ledger=ledger)
        self.assertIn(
            "duplicate_ledger_evidence_id",
            {item["code"] for item in result["errors"]},
        )

    def test_arbitrary_or_stale_ledger_fingerprint_is_rejected(self):
        cases = {}
        arbitrary = self.ledger()
        arbitrary["ledger_fingerprint"] = "arbitrary-fingerprint"
        cases["arbitrary"] = arbitrary
        stale = self.ledger()
        stale["evidence"].append(
            {"evidence_id": "EVD-CCCCCCCCCCCCCCCC"}
        )
        cases["stale_after_evidence_change"] = stale
        for name, ledger in cases.items():
            with self.subTest(name=name):
                result = validate_manuscript_map(
                    self.complete_payload(), ledger=ledger
                )
                self.assertEqual("invalid", result["status"])
                self.assertEqual("unresolved", result["argument_status"])
                self.assertIn(
                    "stale_ledger_fingerprint",
                    {item["code"] for item in result["errors"]},
                )
                self.assertEqual(
                    "invalid", result["summary"]["ledger_binding_status"]
                )

    def test_without_ledger_evidence_is_only_format_checked(self):
        result = validate_manuscript_map(self.complete_payload())
        self.assertEqual("valid", result["status"])
        self.assertEqual("unresolved", result["argument_status"])
        self.assertEqual("structure_only", result["validation_scope"])
        self.assertFalse(result["summary"]["core_chain_complete"])
        self.assertIn(
            "ledger_required_for_argument_closure",
            {item["code"] for item in result["contract_gaps"]},
        )
        self.assertFalse(result["summary"]["semantic_audit_completed"])
        self.assertIn(
            "evidence_ids_not_checked",
            {item["code"] for item in result["warnings"]},
        )
        markdown = render_traceability_markdown(result)
        self.assertIn("not a completed semantic audit", markdown)

    def test_validator_does_not_mutate_the_reviewer_map(self):
        payload = self.complete_payload()
        before = copy.deepcopy(payload)
        result = validate_manuscript_map(payload, ledger=self.ledger())
        self.assertEqual(before, payload)
        self.assertEqual(before["manuscript_map"], result["manuscript_map"])

    def test_strict_contract_rejects_unknown_fields(self):
        payload = manuscript_map_template()
        payload["manuscript_map"]["nodes"][0]["automatic_logic_score"] = 1.0
        result = validate_manuscript_map(payload)
        self.assertIn(
            "unknown_field", {item["code"] for item in result["errors"]}
        )

    def test_init_refuses_overwrite_without_force(self):
        output = self.root / "map.json"
        write_template(output)
        with self.assertRaises(ManuscriptMapError):
            write_template(output)
        write_template(output, stage="complete", force=True)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            "complete", payload["manuscript_map"]["manuscript_stage"]
        )

    def test_validate_refuses_output_alias_even_with_force(self):
        output_dir = self.root / "review"
        input_path = output_dir / "manuscript-map-validation.json"
        self.write_payload(manuscript_map_template(), str(input_path.relative_to(self.root)))
        with self.assertRaises(ManuscriptMapError):
            validate_to_files(input_path, output_dir, force=True)

    def test_validate_force_protects_all_ledger_declared_dependency_paths(self):
        for field in ("root_input", "dependencies", "artifacts", "sources"):
            with self.subTest(field=field):
                case_root = self.root / field
                source = self.write_payload(
                    manuscript_map_template(), f"{field}/map.json"
                )
                dependency = case_root / "manuscript-source.txt"
                dependency.write_text("preserve me", encoding="utf-8")
                output_dir = case_root / "review"
                output_dir.mkdir()
                output_alias = output_dir / "manuscript-map-validation.json"
                os.link(dependency, output_alias)
                ledger = self.ledger()
                if field == "root_input":
                    ledger[field] = str(dependency)
                else:
                    ledger[field] = [{"path": str(dependency)}]
                ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)
                ledger_path = self.write_payload(
                    ledger, f"{field}/evidence-ledger.json"
                )
                with self.assertRaises(ManuscriptMapError):
                    validate_to_files(
                        source,
                        output_dir,
                        ledger_path=ledger_path,
                        force=True,
                    )
                self.assertEqual(
                    "preserve me", dependency.read_text(encoding="utf-8")
                )

    def test_validate_force_protects_temporary_hardlink_to_dependency(self):
        source = self.write_payload(manuscript_map_template())
        dependency = self.root / "manuscript-source.txt"
        dependency.write_text("preserve me", encoding="utf-8")
        output_dir = self.root / "review"
        output_dir.mkdir()
        temporary_alias = output_dir / ".manuscript-map-validation.json.tmp"
        os.link(dependency, temporary_alias)
        ledger = self.ledger()
        ledger["dependencies"] = [{"path": str(dependency)}]
        ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)
        ledger_path = self.write_payload(ledger, "evidence-ledger.json")
        with self.assertRaises(ManuscriptMapError):
            validate_to_files(
                source,
                output_dir,
                ledger_path=ledger_path,
                force=True,
            )
        self.assertEqual("preserve me", dependency.read_text(encoding="utf-8"))

    def test_validate_force_rejects_symlink_output_to_ledger_dependency(self):
        source = self.write_payload(manuscript_map_template())
        dependency = self.root / "manuscript-source.txt"
        dependency.write_text("preserve me", encoding="utf-8")
        output_dir = self.root / "review"
        output_dir.mkdir()
        output_alias = output_dir / "manuscript-map-traceability.md"
        symlink_created = True
        try:
            output_alias.symlink_to(dependency)
        except (NotImplementedError, OSError):
            symlink_created = False
        ledger = self.ledger()
        ledger["dependencies"] = [{"path": str(dependency)}]
        ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)
        ledger_path = self.write_payload(ledger, "evidence-ledger.json")
        call = lambda: validate_to_files(
            source,
            output_dir,
            ledger_path=ledger_path,
            force=True,
        )
        if symlink_created:
            with self.assertRaises(ManuscriptMapError):
                call()
        else:
            # Windows commonly withholds symlink privileges. Exercise the same
            # fail-closed branch deterministically instead of weakening coverage.
            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaises(ManuscriptMapError):
                    call()
        self.assertEqual("preserve me", dependency.read_text(encoding="utf-8"))

    def test_cli_marks_structure_only_as_evidence_not_verified(self):
        source = self.write_payload(manuscript_map_template())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                ["validate", str(source), "--output-dir", str(self.root / "review")]
            )
        self.assertEqual(0, exit_code)
        self.assertIn(
            "valid (structure_only; evidence not verified)",
            output.getvalue(),
        )
        self.assertIn("argument unresolved", output.getvalue())

    def test_cli_reports_valid_contract_with_unresolved_argument(self):
        payload = self.complete_payload()
        payload["manuscript_map"]["edges"][2]["status"] = "mapped"
        source = self.write_payload(payload, "unresolved-map.json")
        ledger_path = self.write_payload(self.ledger(), "ledger.json")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "validate",
                    str(source),
                    "--ledger",
                    str(ledger_path),
                    "--output-dir",
                    str(self.root / "unresolved-review"),
                ]
            )
        self.assertEqual(0, exit_code)
        self.assertIn(
            "valid (contract; argument unresolved)", output.getvalue()
        )

    def test_validate_refuses_overwrite_then_allows_explicit_force(self):
        source = self.write_payload(manuscript_map_template())
        output_dir = self.root / "review"
        first, json_path, markdown_path = validate_to_files(source, output_dir)
        self.assertEqual("valid", first["status"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(markdown_path.is_file())
        with self.assertRaises(ManuscriptMapError):
            validate_to_files(source, output_dir)
        second, _, _ = validate_to_files(source, output_dir, force=True)
        self.assertEqual(first, second)

    def test_cli_returns_one_for_an_invalid_contract_but_writes_diagnostics(self):
        payload = manuscript_map_template()
        payload["manuscript_map"]["edges"][0]["to"] = "MISSING"
        source = self.write_payload(payload)
        output_dir = self.root / "invalid-review"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                ["validate", str(source), "--output-dir", str(output_dir)]
            )
        self.assertEqual(1, exit_code)
        self.assertIn("invalid (error_count=", output.getvalue())
        self.assertIn("dangling_edge_target @ $.manuscript_map.edges[0].to", output.getvalue())
        result = json.loads(
            (output_dir / "manuscript-map-validation.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("invalid", result["status"])

    def test_validate_help_requires_ledger_for_formal_review(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit) as captured:
            with contextlib.redirect_stdout(output):
                main(["validate", "--help"])
        self.assertEqual(0, captured.exception.code)
        self.assertIn(
            "正式审核必须提供 --ledger",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
