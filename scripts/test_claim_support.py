import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import claim_support as cs


def write_references(path: Path, entries: list[dict]) -> Path:
    payload = {
        "schema_version": "0.3.0",
        "entries": [
            {
                "id": f"REF-{index:03d}",
                "status": "verified",
                "input_metadata": entry,
            }
            for index, entry in enumerate(entries, 1)
        ],
        "extraction_diagnostics": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_source_map(path: Path, sources: list[dict]) -> Path:
    path.write_text(
        json.dumps({"schema_version": "0.1.0", "sources": sources}),
        encoding="utf-8",
    )
    return path


def reference_entry(
    key="Smith2021",
    doi="10.1000/smith",
    title="Residual drift response of self-centering frames",
    authors=None,
    year="2021",
):
    return {
        "key": key,
        "doi": doi,
        "title": title,
        "authors": authors or ["Smith, Jane", "Jones, Alex"],
        "year": year,
        "container": "Engineering Structures",
        "location": {"source": "refs.bib", "line": 1},
    }


def long_source_text(doi="10.1000/smith", result="Residual drift decreased by 50% in the tested self-centering frame."):
    background = (
        "Self-centering structural systems use restoring forces to limit permanent deformation. "
        "The experimental program included repeated cyclic loading and careful displacement measurements. "
    )
    return (
        f"Residual drift response of self-centering frames\nDOI: {doi}\n\n"
        + background * 4
        + "\n\nResults\n"
        + result
        + " The reported values apply to the tested frame and loading protocol.\n\n"
        + background * 3
    )


class PrepareTests(unittest.TestCase):
    def test_prepare_local_text_source_is_read_only_and_ids_are_stable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manuscript = root / "paper.tex"
            manuscript.write_text(
                "\\section{Introduction}\n"
                "Self-centering frames reduced residual drift by 50\\% in prior tests "
                "\\cite{Smith2021}.\n",
                encoding="utf-8",
            )
            refs = write_references(root / "references.json", [reference_entry()])
            source = root / "Smith2021.txt"
            source.write_text(long_source_text(), encoding="utf-8")
            source_map = write_source_map(
                root / "source-map.json",
                [
                    {
                        "citation_key": "Smith2021",
                        "doi": "10.1000/smith",
                        "path": source.name,
                        "access": "user-provided",
                    }
                ],
            )
            manuscript_hash = hashlib.sha256(manuscript.read_bytes()).hexdigest()
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            first = cs.prepare_claim_evidence(
                manuscript,
                root / "review-one",
                references_json=refs,
                source_map=source_map,
                scope="all",
            )
            second = cs.prepare_claim_evidence(
                manuscript,
                root / "review-two",
                references_json=refs,
                source_map=source_map,
                scope="all",
            )

            self.assertEqual(len(first["claims"]), 1)
            self.assertEqual(first["claims"][0]["id"], second["claims"][0]["id"])
            cited = first["claims"][0]["references"][0]
            self.assertEqual(cited["source_match"]["status"], "matched")
            self.assertEqual(cited["source_access"]["status"], "fulltext")
            self.assertTrue(cited["evidence_candidates"])
            self.assertIn("50%", cited["evidence_candidates"][0]["quote"])
            self.assertEqual(hashlib.sha256(manuscript.read_bytes()).hexdigest(), manuscript_hash)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)
            self.assertTrue((root / "review-one" / "claim-evidence.md").exists())

    def test_markdown_numeric_citation_maps_by_reference_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manuscript = root / "paper.md"
            manuscript.write_text(
                "# Results\n\nResidual drift decreased by 20% [1].\n\n# References\n\n"
                "[1] Smith, J. (2021). Residual drift response of self-centering frames.\n",
                encoding="utf-8",
            )
            refs = write_references(root / "references.json", [reference_entry()])
            source = root / "source.md"
            source.write_text(long_source_text(result="Residual drift decreased by 20% under the protocol."), encoding="utf-8")
            source_map = write_source_map(
                root / "source-map.json",
                [{"citation_key": "Smith2021", "path": source.name}],
            )
            data = cs.prepare_claim_evidence(
                manuscript,
                root / "review",
                references_json=refs,
                source_map=source_map,
                scope="all",
            )
            self.assertEqual(len(data["claims"]), 1)
            self.assertEqual(
                data["claims"][0]["citation"]["mapping_method"],
                "numeric-reference-order",
            )
            self.assertEqual(data["claims"][0]["citation"]["keys"], ["Smith2021"])

    def test_open_access_url_is_not_requested_without_explicit_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manuscript = root / "paper.tex"
            manuscript.write_text("A reduction was reported \\cite{Smith2021}.\n", encoding="utf-8")
            refs = write_references(root / "references.json", [reference_entry()])
            source_map = write_source_map(
                root / "source-map.json",
                [
                    {
                        "citation_key": "Smith2021",
                        "url": "https://example.invalid/open-paper.pdf",
                        "access": "open-access",
                    }
                ],
            )
            with patch.object(cs.urllib.request, "urlopen") as urlopen:
                data = cs.prepare_claim_evidence(
                    manuscript,
                    root / "review",
                    references_json=refs,
                    source_map=source_map,
                    scope="all",
                )
            urlopen.assert_not_called()
            source = data["claims"][0]["references"][0]
            self.assertEqual(source["source_access"]["status"], "unavailable")
            self.assertEqual(
                source["source_match"]["reason"],
                "open_access_download_not_authorized",
            )

    def test_explicit_source_map_rejects_detected_doi_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manuscript = root / "paper.tex"
            manuscript.write_text("A reduction was reported \\cite{Smith2021}.\n", encoding="utf-8")
            refs = write_references(root / "references.json", [reference_entry()])
            source = root / "wrong.txt"
            source.write_text(long_source_text(doi="10.1000/different"), encoding="utf-8")
            source_map = write_source_map(
                root / "source-map.json",
                [{"citation_key": "Smith2021", "path": source.name}],
            )
            data = cs.prepare_claim_evidence(
                manuscript,
                root / "review",
                references_json=refs,
                source_map=source_map,
                scope="all",
            )
            mapped = data["claims"][0]["references"][0]
            self.assertEqual(mapped["source_match"]["status"], "conflict")
            self.assertEqual(mapped["evidence_candidates"], [])

    def test_pdf_source_preserves_page_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf = Path(temp_dir) / "source.pdf"
            pdf.write_bytes(b"%PDF-1.7\nimmutable\n%%EOF")
            page_one = "Background " + "structural response " * 30
            page_two = "Results. Residual drift decreased by 50% in the tested frame. " * 8
            with patch.object(cs.references, "read_pdf_text", return_value=page_one + "\f" + page_two):
                document = cs.extract_source_document(
                    pdf, origin="source-map", access="user-provided"
                )
            self.assertTrue(any(item["location"].get("page") == 2 for item in document.passages))
            candidates, _ = cs.rank_evidence(
                "Residual drift decreased by 50%", document.passages, 3
            )
            self.assertEqual(candidates[0]["location"]["page"], 2)

    def test_quantity_unit_conversion_is_visible_in_score(self):
        passages = [
            {
                "text": "The maximum displacement was measured as 0.1 m during the test.",
                "location": {"page": 4},
            },
            {
                "text": "The frame geometry and material properties were documented.",
                "location": {"page": 2},
            },
        ]
        candidates, retrieval = cs.rank_evidence(
            "The maximum displacement reached 100 mm", passages, 2
        )
        self.assertEqual(candidates[0]["location"]["page"], 4)
        self.assertEqual(candidates[0]["score_components"]["quantity_match"], 1.0)
        self.assertEqual(retrieval["algorithm"], "local-bm25-term-quantity-v1")
        self.assertTrue(retrieval["absence_is_not_non_support"])

    def test_prepare_refuses_to_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manuscript = root / "paper.tex"
            manuscript.write_text("A reduction was reported \\cite{Smith2021}.\n", encoding="utf-8")
            refs = write_references(root / "references.json", [reference_entry()])
            output = root / "review"
            cs.prepare_claim_evidence(
                manuscript, output, references_json=refs, scope="all"
            )
            first = (output / "claim-evidence.json").read_text(encoding="utf-8")
            with self.assertRaisesRegex(cs.ClaimSupportError, "已存在"):
                cs.prepare_claim_evidence(
                    manuscript, output, references_json=refs, scope="all"
                )
            self.assertEqual((output / "claim-evidence.json").read_text(encoding="utf-8"), first)


class FinalizeTests(unittest.TestCase):
    def make_prepared(self, root: Path, *, with_source=True):
        manuscript = root / "paper.tex"
        manuscript.write_text(
            "Self-centering frames reduced residual drift by 50\\% \\cite{Smith2021}.\n",
            encoding="utf-8",
        )
        refs = write_references(root / "references.json", [reference_entry()])
        source_map = None
        if with_source:
            source = root / "Smith2021.txt"
            source.write_text(long_source_text(), encoding="utf-8")
            source_map = write_source_map(
                root / "source-map.json",
                [{"citation_key": "Smith2021", "path": source.name}],
            )
        review = root / "review"
        evidence = cs.prepare_claim_evidence(
            manuscript,
            review,
            references_json=refs,
            source_map=source_map,
            scope="all",
        )
        return review, evidence

    def write_decisions(self, path: Path, evidence: dict, **overrides):
        claim = evidence["claims"][0]
        source = claim["references"][0]
        decision = {
            "claim_id": claim["id"],
            "citation_key": source["citation_key"],
            "verdict": "supports",
            "confidence": 0.92,
            "rationale": "来源结果段直接报告相同体系中的残余漂移降低。",
            "evidence_ranks": [1],
            "dimension_matches": {
                "system": "match",
                "outcome": "match",
                "magnitude": "match",
            },
            "reviewer": "unit-test-reviewer",
        }
        decision.update(overrides)
        path.write_text(json.dumps({"decisions": [decision]}), encoding="utf-8")
        return path

    def test_finalize_supports_and_embeds_selected_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, evidence = self.make_prepared(root)
            decisions = self.write_decisions(review / "claim-decisions.json", evidence)
            data = cs.finalize_claim_support(
                review / "claim-evidence.json", decisions, review
            )
            assessed = data["claims"][0]["references"][0]
            self.assertEqual(assessed["verdict"], "supports")
            self.assertTrue(assessed["selected_evidence"])
            self.assertEqual(data["summary"]["formal_finding_count"], 0)
            self.assertTrue((review / "claim-support.json").exists())
            report = (review / "claim-support-report.md").read_text(encoding="utf-8")
            self.assertIn("支持", report)
            self.assertIn("50%", report)

    def test_partial_support_creates_formal_finding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, evidence = self.make_prepared(root)
            decisions = self.write_decisions(
                review / "claim-decisions.json",
                evidence,
                verdict="partially_supports",
                confidence=0.86,
                rationale="来源仅支持受测单榀框架，不能推广到所有自复位结构。",
                dimension_matches={
                    "system": "partial",
                    "outcome": "match",
                    "scope": "mismatch",
                },
                suggested_revision="将结论限定为受测框架与加载协议。",
            )
            data = cs.finalize_claim_support(
                review / "claim-evidence.json", decisions, review
            )
            self.assertEqual(data["summary"]["formal_finding_count"], 1)
            self.assertEqual(
                data["formal_findings"][0]["check_id"],
                "citation-partially-supports-claim",
            )

    def test_does_not_support_requires_explicit_mismatch_dimension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, evidence = self.make_prepared(root)
            decisions = self.write_decisions(
                review / "claim-decisions.json",
                evidence,
                verdict="does_not_support",
                confidence=0.90,
                rationale="检索结果不够相似，因此直接判定来源不支持。",
                dimension_matches={"system": "match", "outcome": "unclear"},
            )
            with self.assertRaisesRegex(cs.ClaimSupportError, "冲突维度"):
                cs.finalize_claim_support(
                    review / "claim-evidence.json", decisions, review
                )

    def test_missing_fulltext_can_finalize_only_as_unable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, evidence = self.make_prepared(root, with_source=False)
            decisions = self.write_decisions(
                review / "claim-decisions.json",
                evidence,
                verdict="unable_to_verify",
                confidence=0.98,
                rationale="用户未提供来源全文，无法检查该文献是否支持附近主张。",
                evidence_ranks=[],
                dimension_matches={},
            )
            data = cs.finalize_claim_support(
                review / "claim-evidence.json", decisions, review
            )
            self.assertEqual(
                data["claims"][0]["overall_verdict"], "unable_to_verify"
            )

    def test_missing_fulltext_cannot_be_called_non_support(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, evidence = self.make_prepared(root, with_source=False)
            decisions = self.write_decisions(
                review / "claim-decisions.json",
                evidence,
                verdict="does_not_support",
                confidence=0.90,
                rationale="没有检索到候选片段，所以认为来源不支持主张。",
                evidence_ranks=[],
                dimension_matches={"evidence": "mismatch"},
            )
            with self.assertRaisesRegex(cs.ClaimSupportError, "没有足够全文证据"):
                cs.finalize_claim_support(
                    review / "claim-evidence.json", decisions, review
                )

    def test_finalize_requires_one_decision_for_every_claim_reference_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, _ = self.make_prepared(root)
            decisions = review / "claim-decisions.json"
            decisions.write_text(json.dumps({"decisions": []}), encoding="utf-8")
            with self.assertRaisesRegex(cs.ClaimSupportError, "缺少 1 条决策"):
                cs.finalize_claim_support(
                    review / "claim-evidence.json", decisions, review
                )

    def test_finalize_refuses_to_overwrite_previous_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review, evidence = self.make_prepared(root)
            decisions = self.write_decisions(review / "claim-decisions.json", evidence)
            cs.finalize_claim_support(review / "claim-evidence.json", decisions, review)
            first = (review / "claim-support.json").read_text(encoding="utf-8")
            with self.assertRaisesRegex(cs.ClaimSupportError, "已存在"):
                cs.finalize_claim_support(
                    review / "claim-evidence.json", decisions, review
                )
            self.assertEqual((review / "claim-support.json").read_text(encoding="utf-8"), first)


if __name__ == "__main__":
    unittest.main()
