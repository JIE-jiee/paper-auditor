import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import evidence_spine as spine
from evidence_spine import (
    EvidenceSpineError,
    adjudicate_report,
    prepare_evidence_spine,
    record_pass,
)


class EvidenceSpineReleaseSecurityTests(unittest.TestCase):
    """Release-gate regressions for evidence and output-alias fail-closed rules."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manuscript = self.root / "paper.md"
        self.manuscript.write_text(
            "Results\n"
            "The tested frame reduced peak drift by 20%.\n"
            "Context line three.\n"
            "Context line four.\n"
            "Context line five.\n"
            "Context line six.\n"
            "Context line seven.\n"
            "Context line eight.\n"
            "Context line nine.\n"
            "A remote sentence belongs to a different issue.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def file_hash(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def write_json(self, name, payload, *, directory=None):
        target_dir = directory or self.root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
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
        output_name=None,
        additional_artifacts=(),
    ):
        return prepare_evidence_spine(
            manuscript or self.manuscript,
            self.root / (output_name or f"spine-{pass_id}"),
            mode="targeted",
            required_passes=[pass_id],
            additional_artifacts=additional_artifacts,
        )

    def finding(self, *, manuscript=None, **changes):
        source = manuscript or self.manuscript
        value = {
            "id": "RELEASE-SECURITY-001",
            "category": "terminology",
            "check_id": "release-security-regression",
            "severity": "Minor",
            "confidence": 0.95,
            "status": "confirmed",
            "location": {
                "source": source.name,
                "line": 2,
                "section": "Results",
                "scope": "body",
            },
            "quote": "The tested frame reduced peak drift by 20%.",
            "observation": "Synthetic release-security observation.",
            "expected": "The evidence contract must remain fail-closed.",
            "reason": "This proposal exercises a release security invariant.",
            "evidence": [],
            "suggested_fix": "Reject or route the unsupported proposal to manual review.",
            "auto_fixable": False,
        }
        value.update(changes)
        return value

    def citation_finding(
        self,
        citation_key,
        source,
        source_quote,
        *,
        source_sha256=None,
        finding_id="RELEASE-CITATION-001",
        **changes,
    ):
        evidence = {
            "rank": 1,
            "citation_key": citation_key,
            "location": {"source": source.name, "line": 1},
            "quote": source_quote,
        }
        if source_sha256 is not None:
            evidence["source_sha256"] = source_sha256
        value = self.finding(
            id=finding_id,
            category="citation-support",
            check_id="citation-partially-supports-claim",
            citation_key=citation_key,
            verdict="partially_supports",
            dimension_matches={},
            evidence=[evidence],
        )
        value.update(changes)
        return value

    def result_file(self, prepared, pass_id, findings, *, name):
        return self.write_json(
            name,
            {
                "schema_version": "release-security-test",
                "pass_id": pass_id,
                "provenance": {
                    "ledger_fingerprint": prepared["ledger"]["ledger_fingerprint"],
                    "input_fingerprint": prepared["manifest"]["input_fingerprint"],
                },
                "sources": list(prepared["ledger"]["sources"]),
                "findings": findings,
                "summary": {"finding_count": len(findings)},
            },
        )

    def complete_pass(
        self,
        prepared,
        pass_id,
        result_path,
        *,
        output_name,
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
            reviewer=f"{pass_id}-release-security-reviewer",
            capability_updates=capability_updates,
        )
        return output

    def finalize(self, prepared, coverage_path, *, output_name):
        return adjudicate_report(
            prepared["paths"]["manifest"],
            prepared["paths"]["ledger"],
            coverage_path,
            self.root / output_name,
        )

    def assert_manual_not_formal(self, result, finding_id, *expected_reasons):
        self.assertFalse(
            any(item.get("id") == finding_id for item in result["findings"]),
            f"{finding_id} unexpectedly became a formal finding",
        )
        manual = next(
            item for item in result["manual_checks"] if item.get("id") == finding_id
        )
        reasons = manual["adjudication"]["reasons"]
        for reason in expected_reasons:
            self.assertIn(reason, reasons)
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])

    def test_engineering_standard_cannot_masquerade_as_citation_support(self):
        cited_source = self.root / "ordinary-cited-source.txt"
        cited_quote = "A secondary paper paraphrases a standard provision."
        cited_source.write_text(cited_quote + "\n", encoding="utf-8")
        prepared = self.prepare(
            "engineering_standards",
            output_name="standard-citation-masquerade-spine",
            additional_artifacts=(("cited_source", cited_source),),
        )
        finding = self.citation_finding(
            cited_source.stem,
            cited_source,
            cited_quote,
            finding_id="STD-CITATION-MASQUERADE",
            check_id="standard-clause-applicability",
            required_capabilities=["manuscript_text", "cited_full_text"],
        )
        result_path = self.result_file(
            prepared,
            "engineering_standards",
            [finding],
            name="standard-citation-masquerade-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "engineering_standards",
            result_path,
            output_name="standard-citation-masquerade-coverage.json",
            capability_updates={"cited_full_text": "available"},
        )
        result = self.finalize(
            prepared,
            coverage_path,
            output_name="standard-citation-masquerade-final",
        )

        self.assert_manual_not_formal(
            result,
            finding["id"],
            "incompatible_pass_category:engineering_standards:citation-support",
            "missing_capability:standard_text",
            "missing_direct_artifact:standard_source",
        )

    def test_visual_pass_cannot_masquerade_as_standard_finding(self):
        prepared = self.prepare(
            "visual",
            output_name="visual-standard-masquerade-spine",
        )
        finding = self.finding(
            id="VISUAL-STANDARD-MASQUERADE",
            category="standard",
            check_id="standard-clause-applicability",
            required_capabilities=["manuscript_text"],
        )
        result_path = self.result_file(
            prepared,
            "visual",
            [finding],
            name="visual-standard-masquerade-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "visual",
            result_path,
            output_name="visual-standard-masquerade-coverage.json",
        )
        result = self.finalize(
            prepared,
            coverage_path,
            output_name="visual-standard-masquerade-final",
        )

        self.assert_manual_not_formal(
            result,
            finding["id"],
            "incompatible_pass_category:visual:standard",
            "missing_capability:rendered_pages",
        )

    def test_visual_pass_cannot_masquerade_as_citation_finding(self):
        cited_source = self.root / "visual-citation.txt"
        cited_quote = "The cited paper describes a plotted response."
        cited_source.write_text(cited_quote + "\n", encoding="utf-8")
        prepared = self.prepare(
            "visual",
            output_name="visual-citation-masquerade-spine",
            additional_artifacts=(("cited_source", cited_source),),
        )
        finding = self.citation_finding(
            cited_source.stem,
            cited_source,
            cited_quote,
            finding_id="VISUAL-CITATION-MASQUERADE",
            required_capabilities=["manuscript_text", "cited_full_text"],
        )
        result_path = self.result_file(
            prepared,
            "visual",
            [finding],
            name="visual-citation-masquerade-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "visual",
            result_path,
            output_name="visual-citation-masquerade-coverage.json",
            capability_updates={"cited_full_text": "available"},
        )
        result = self.finalize(
            prepared,
            coverage_path,
            output_name="visual-citation-masquerade-final",
        )

        self.assert_manual_not_formal(
            result,
            finding["id"],
            "incompatible_pass_category:visual:citation-support",
            "missing_capability:rendered_pages",
        )

    def test_prepare_force_rejects_manifest_output_aliasing_manuscript(self):
        alias_dir = self.root / "prepare-alias"
        alias_dir.mkdir()
        manuscript = alias_dir / "artifact-manifest.json"
        manuscript.write_text(
            "Results\nThe tested frame reduced peak drift by 20%.\n",
            encoding="utf-8",
        )
        before = self.file_hash(manuscript)

        # The production loader intentionally accepts manuscript formats rather
        # than JSON. Supply an equivalent parsed unit so this adversarial filename
        # reaches the write-target preflight instead of stopping at suffix routing.
        parser_probe = self.root / "prepare-alias-parser-probe.md"
        parser_probe.write_text(manuscript.read_text(encoding="utf-8"), encoding="utf-8")
        units = spine._load_sources(parser_probe, [])
        for unit in units:
            unit.path = manuscript
            unit.source = manuscript.name

        with mock.patch.object(spine, "_load_sources", return_value=units):
            with self.assertRaisesRegex(EvidenceSpineError, "受保护输入或依赖路径"):
                prepare_evidence_spine(
                    manuscript,
                    alias_dir,
                    mode="targeted",
                    required_passes=["deterministic_text"],
                    force=True,
                )

        self.assertEqual(before, self.file_hash(manuscript))
        self.assertFalse((alias_dir / "evidence-ledger.json").exists())
        self.assertFalse((alias_dir / "coverage.json").exists())

    def test_record_pass_force_rejects_output_equal_to_manuscript_dependency(self):
        prepared = self.prepare(
            "deterministic_text",
            output_name="record-pass-alias-spine",
        )
        finding = self.finding(id="RECORD-PASS-ALIAS")
        result_path = self.result_file(
            prepared,
            "deterministic_text",
            [finding],
            name="record-pass-alias-result.json",
        )
        before = self.file_hash(self.manuscript)

        with self.assertRaisesRegex(EvidenceSpineError, "受保护输入或依赖路径"):
            record_pass(
                prepared["paths"]["coverage"],
                prepared["paths"]["ledger"],
                self.manuscript,
                pass_id="deterministic_text",
                status="completed",
                result_path=result_path,
                reviewer="record-pass-alias-reviewer",
                force=True,
            )

        self.assertEqual(before, self.file_hash(self.manuscript))

    def test_finalize_force_rejects_review_report_aliasing_manuscript(self):
        alias_dir = self.root / "finalize-alias"
        alias_dir.mkdir()
        manuscript = alias_dir / "review-report.md"
        manuscript.write_text(
            "Results\nThe tested frame reduced peak drift by 20%.\n",
            encoding="utf-8",
        )
        prepared = self.prepare(
            "deterministic_text",
            manuscript=manuscript,
            output_name="finalize-alias-spine",
        )
        finding = self.finding(
            manuscript=manuscript,
            id="FINALIZE-ALIAS",
        )
        result_path = self.result_file(
            prepared,
            "deterministic_text",
            [finding],
            name="finalize-alias-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "deterministic_text",
            result_path,
            output_name="finalize-alias-coverage.json",
        )
        before = self.file_hash(manuscript)

        with self.assertRaisesRegex(EvidenceSpineError, "受保护输入或依赖路径"):
            adjudicate_report(
                prepared["paths"]["manifest"],
                prepared["paths"]["ledger"],
                coverage_path,
                alias_dir,
                force=True,
            )

        self.assertEqual(before, self.file_hash(manuscript))
        self.assertFalse((alias_dir / "findings.json").exists())
        self.assertFalse((alias_dir / "final-evidence-ledger.json").exists())

    def test_remote_same_source_evidence_id_cannot_bind_to_current_finding(self):
        prepared = self.prepare(
            "deterministic_text",
            output_name="remote-evd-spine",
        )
        far_evidence = next(
            item
            for item in prepared["ledger"]["evidence"]
            if item["locator"].get("source") == self.manuscript.name
            and item["locator"].get("line") == 10
        )
        finding = self.finding(
            id="REMOTE-EVD-MISBIND",
            evidence_ids=[far_evidence["evidence_id"]],
        )
        result_path = self.result_file(
            prepared,
            "deterministic_text",
            [finding],
            name="remote-evd-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "deterministic_text",
            result_path,
            output_name="remote-evd-coverage.json",
        )
        result = self.finalize(
            prepared,
            coverage_path,
            output_name="remote-evd-final",
        )

        self.assert_manual_not_formal(
            result,
            finding["id"],
            "evidence_id_outside_locator",
        )

    def test_citation_key_b_rejects_source_a_locator_hash_and_quote(self):
        source_a = self.root / "A.txt"
        source_b = self.root / "B.txt"
        quote_a = "Source A reports a 20% reduction for one specimen."
        source_a.write_text(quote_a + "\n", encoding="utf-8")
        source_b.write_text(
            "Source B concerns a different structural system.\n",
            encoding="utf-8",
        )
        prepared = self.prepare(
            "claim_support",
            output_name="citation-key-mismatch-spine",
            additional_artifacts=(
                ("cited_source", source_a),
                ("cited_source", source_b),
            ),
        )
        finding = self.citation_finding(
            "B",
            source_a,
            quote_a,
            source_sha256=self.file_hash(source_a),
            finding_id="CITATION-KEY-B-SOURCE-A",
        )
        result_path = self.result_file(
            prepared,
            "claim_support",
            [finding],
            name="citation-key-mismatch-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "claim_support",
            result_path,
            output_name="citation-key-mismatch-coverage.json",
            capability_updates={"cited_full_text": "available"},
        )
        result = self.finalize(
            prepared,
            coverage_path,
            output_name="citation-key-mismatch-final",
        )

        self.assert_manual_not_formal(
            result,
            finding["id"],
            "external_citation_key_not_declared:1",
        )

    def test_rehashed_manifest_cannot_forge_cited_source_identity(self):
        source_a = self.root / "forged-A.txt"
        source_b = self.root / "forged-B.txt"
        quote_a = "Source A reports a 20% reduction for one specimen."
        source_a.write_text(quote_a + "\n", encoding="utf-8")
        source_b.write_text(
            "Source B concerns a different structural system.\n",
            encoding="utf-8",
        )
        prepared = self.prepare(
            "claim_support",
            output_name="forged-identity-spine",
            additional_artifacts=(
                ("cited_source", source_a),
                ("cited_source", source_b),
            ),
        )

        manifest = json.loads(
            prepared["paths"]["manifest"].read_text(encoding="utf-8")
        )
        artifact_a = next(
            item
            for item in manifest["artifacts"]
            if item["role"] == "cited_source" and item["source"] == source_a.name
        )
        artifact_a["identity"]["citation_keys"].append(source_b.stem)
        manifest["input_fingerprint"] = spine.manifest_fingerprint(manifest)
        manifest_path = self.write_json("forged-identity-manifest.json", manifest)

        ledger = json.loads(
            prepared["paths"]["ledger"].read_text(encoding="utf-8")
        )
        ledger["input_fingerprint"] = manifest["input_fingerprint"]
        ledger["ledger_fingerprint"] = spine.ledger_fingerprint(ledger)
        ledger_path = self.write_json("forged-identity-ledger.json", ledger)

        coverage = json.loads(
            prepared["paths"]["coverage"].read_text(encoding="utf-8")
        )
        coverage["input_fingerprint"] = manifest["input_fingerprint"]
        coverage["ledger_fingerprint"] = ledger["ledger_fingerprint"]
        coverage["coverage_fingerprint"] = spine.coverage_fingerprint(coverage)
        coverage_path = self.write_json("forged-identity-coverage.json", coverage)

        tampered = {
            "manifest": manifest,
            "ledger": ledger,
            "coverage": coverage,
            "paths": {
                "manifest": manifest_path,
                "ledger": ledger_path,
                "coverage": coverage_path,
            },
        }
        finding = self.citation_finding(
            source_b.stem,
            source_a,
            quote_a,
            source_sha256=self.file_hash(source_a),
            finding_id="FORGED-CITED-SOURCE-IDENTITY",
        )
        result_path = self.result_file(
            tampered,
            "claim_support",
            [finding],
            name="forged-identity-result.json",
        )
        completed_coverage = self.complete_pass(
            tampered,
            "claim_support",
            result_path,
            output_name="forged-identity-completed-coverage.json",
            capability_updates={"cited_full_text": "available"},
        )

        try:
            result = self.finalize(
                tampered,
                completed_coverage,
                output_name="forged-identity-final",
            )
        except EvidenceSpineError:
            return
        self.assertFalse(
            any(item.get("id") == finding["id"] for item in result["findings"]),
            "a rehashed, forged citation identity unexpectedly became formal",
        )
        self.assertEqual("manual_confirmation_required", result["submission_readiness"])

    def test_explicit_cited_alias_cannot_collide_with_default_stem_identity(self):
        arbitrary_source = self.root / "arbitrary.txt"
        default_b_source = self.root / "B.txt"
        arbitrary_source.write_text(
            "The arbitrary source contains otherwise valid full text.\n",
            encoding="utf-8",
        )
        default_b_source.write_text(
            "The default B source owns the citation key derived from its stem.\n",
            encoding="utf-8",
        )
        source_map = self.write_json(
            "colliding-cited-source-map.json",
            {
                "schema_version": "0.1.0",
                "sources": [
                    {
                        "citation_key": "B",
                        "path": arbitrary_source.name,
                    }
                ],
            },
        )
        output_name = "colliding-cited-alias-spine"

        with self.assertRaises(EvidenceSpineError):
            self.prepare(
                "claim_support",
                output_name=output_name,
                additional_artifacts=(
                    ("cited_source", arbitrary_source),
                    ("cited_source", default_b_source),
                    ("cited_source_map", source_map),
                ),
            )

        self.assertFalse((self.root / output_name / "artifact-manifest.json").exists())

    def test_explicit_cited_source_map_binds_arbitrary_filename(self):
        source = self.root / "opaque-local-fulltext.txt"
        source_quote = "The source reports a 20% reduction for the tested frame."
        source.write_text(source_quote + "\n", encoding="utf-8")
        citation_key = "SmithAndJones2026"
        source_map = self.write_json(
            "cited-source-map.json",
            {
                "schema_version": "0.1.0",
                "sources": [
                    {
                        "citation_key": citation_key,
                        "path": source.name,
                    }
                ],
            },
        )
        prepared = self.prepare(
            "claim_support",
            output_name="explicit-cited-map-spine",
            additional_artifacts=(
                ("cited_source", source),
                ("cited_source_map", source_map),
            ),
        )
        cited_artifact = next(
            item
            for item in prepared["manifest"]["artifacts"]
            if item["role"] == "cited_source"
        )
        self.assertIn(citation_key, cited_artifact["identity"]["citation_keys"])

        finding = self.citation_finding(
            citation_key,
            source,
            source_quote,
            source_sha256=self.file_hash(source),
            finding_id="EXPLICIT-CITED-SOURCE-MAP",
        )
        result_path = self.result_file(
            prepared,
            "claim_support",
            [finding],
            name="explicit-cited-map-result.json",
        )
        coverage_path = self.complete_pass(
            prepared,
            "claim_support",
            result_path,
            output_name="explicit-cited-map-coverage.json",
            capability_updates={"cited_full_text": "available"},
        )
        result = self.finalize(
            prepared,
            coverage_path,
            output_name="explicit-cited-map-final",
        )

        self.assertEqual("complete", result["review_status"])
        self.assertEqual([finding["id"]], [item["id"] for item in result["findings"]])
        self.assertEqual("accepted", result["findings"][0]["adjudication"]["outcome"])
        self.assertGreaterEqual(len(result["findings"][0]["evidence_ids"]), 2)
        self.assertEqual(1, result["summary"]["external_evidence_count"])


if __name__ == "__main__":
    unittest.main()
