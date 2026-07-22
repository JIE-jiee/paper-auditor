import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from audit_manuscript import (
    AuditError,
    PDFTEXT_TIMEOUT_SECONDS,
    _markdown_prose_view,
    _pdf_text,
    _tex_structure_view,
    build_parser,
    run_audit,
)


class AuditManuscriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def audit_text(self, name, text):
        manuscript = self.root / name
        manuscript.write_text(text, encoding="utf-8")
        output = self.root / f"{Path(name).stem}-review"
        result = run_audit(manuscript, output)
        self.assertTrue((output / "findings.json").is_file())
        self.assertTrue((output / "review-report.md").is_file())
        loaded = json.loads((output / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual(result["findings"], loaded["findings"])
        return manuscript, output, result

    def write_profile(self, name, changes):
        profile_path = Path(__file__).resolve().parent.parent / "references" / "personal-profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(profile.get(key), dict):
                profile[key].update(value)
            else:
                profile[key] = value
        destination = self.root / name
        destination.write_text(json.dumps(profile), encoding="utf-8")
        return destination

    def test_abbreviation_abstract_and_body_are_separate_scopes(self):
        _, _, result = self.audit_text(
            "scopes.txt",
            """Abstract
A self-centering (SC) frame was tested. SC reduced residual drift.

Introduction
SC frames have been studied extensively. The SC response is discussed here.
""",
        )
        first_use = [
            finding
            for finding in result["findings"]
            if finding["check_id"] == "abbreviation-first-use"
            and "SC" in finding["observation"]
        ]
        self.assertEqual(1, len(first_use))
        self.assertEqual("body", first_use[0]["location"]["scope"])
        self.assertEqual("Introduction", first_use[0]["location"]["section"])

    def test_preferred_term_does_not_trigger_shorter_alias(self):
        _, _, result = self.audit_text(
            "preferred.md",
            """# Results
The interstory drift ratio remained below the limit.
The reported interstory drift ratio was 0.02.
""",
        )
        variants = [
            item for item in result["findings"] if item["check_id"] == "terminology-variant"
        ]
        self.assertEqual([], variants)
        ledger = result["inventories"]["terminology"]["interstory drift ratio"]
        self.assertEqual(2, ledger["interstory drift ratio"])
        self.assertNotIn("interstory drift", ledger)

    def test_abbreviation_definition_can_wrap_across_latex_lines(self):
        _, _, result = self.audit_text(
            "wrapped.tex",
            r"""\section{Results}
The response was characterized using peak floor
acceleration (PFA). PFA was recorded at each story. PFA governed the comparison.
""",
        )
        first_use = [
            item
            for item in result["findings"]
            if item["check_id"] == "abbreviation-first-use" and "PFA" in item["observation"]
        ]
        self.assertEqual([], first_use)
        definitions = result["inventories"]["abbreviations"]["PFA"]["definitions"]
        self.assertIn("peak floor acceleration", definitions)

    def test_terminology_alias_and_forbidden_term(self):
        _, _, result = self.audit_text(
            "terms.md",
            """# Methods
The post tensioned frame used a self-resetting mechanism.
""",
        )
        checks = {finding["check_id"] for finding in result["findings"]}
        self.assertIn("terminology-variant", checks)
        self.assertIn("terminology-forbidden", checks)
        forbidden = next(
            finding
            for finding in result["findings"]
            if finding["check_id"] == "terminology-forbidden"
        )
        self.assertFalse(forbidden["auto_fixable"])

    def test_figure_table_and_equation_callout_inventory(self):
        _, _, result = self.audit_text(
            "crossrefs.txt",
            """Introduction
Figure 1 shows the test setup. Table 2 lists the specimens. Equation (3) gives the response.

Fig. 1. Test setup.
Table 1. Material properties.
Eq. (1). Governing relationship.
""",
        )
        missing = [
            finding
            for finding in result["findings"]
            if finding["check_id"] == "crossref-callout-missing-target"
        ]
        unused = [
            finding
            for finding in result["findings"]
            if finding["check_id"] == "crossref-target-not-called"
        ]
        self.assertTrue(any("table 2" in item["observation"] for item in missing))
        self.assertTrue(any("table 1" in item["observation"] for item in unused))
        self.assertTrue(any("equation 3" in item["observation"] for item in missing))
        self.assertTrue(any("equation 1" in item["observation"] for item in unused))
        self.assertNotIn(
            "figure 1",
            " ".join(item["observation"] for item in missing).casefold(),
        )

    def test_latex_labels_citations_and_bibtex_keys(self):
        tex = self.root / "paper.tex"
        bib = self.root / "refs.bib"
        tex.write_text(
            r"""\documentclass{article}
\begin{document}
See Fig.~\ref{fig:ok} and \ref{fig:missing}.
Prior work is discussed by \cite{Known,Missing}.
\begin{figure}
\caption{A test.}\label{fig:ok}
\end{figure}
\label{fig:unused}
\bibliography{refs}
\end{document}
""",
            encoding="utf-8",
        )
        bib.write_text(
            r"""@article{Known,
  author = {A. Author},
  title = {Known work},
  year = {2020}
}
@article{Unused,
  author = {B. Author},
  title = {Unused work},
  year = {2021}
}
""",
            encoding="utf-8",
        )
        result = run_audit(tex, self.root / "tex-review")
        checks = {finding["check_id"] for finding in result["findings"]}
        self.assertIn("latex-reference-missing-label", checks)
        self.assertIn("latex-citation-missing-bib-key", checks)
        self.assertIn("latex-unused-label", checks)
        self.assertIn("bibtex-unused-entry", checks)
        missing_keys = " ".join(
            finding["observation"]
            for finding in result["findings"]
            if finding["check_id"] == "latex-citation-missing-bib-key"
        )
        self.assertIn("Missing", missing_keys)

    def test_missing_bibliography_is_a_diagnostic_not_a_fabricated_defect(self):
        _, _, result = self.audit_text(
            "no-bib.tex",
            r"""\documentclass{article}
\begin{document}
Prior work is cited here \cite{Unknown}.
\end{document}
""",
        )
        diagnostic_codes = {item["code"] for item in result["diagnostics"]}
        finding_checks = {item["check_id"] for item in result["findings"]}
        self.assertIn("bibliography-not-found", diagnostic_codes)
        self.assertNotIn("latex-citation-missing-bib-key", finding_checks)

    def test_latex_structure_ignores_comments_literal_code_and_verb(self):
        tex = self.root / "structure.tex"
        bib = self.root / "refs.bib"
        source = r"""\documentclass{article}
% \input{missing-comment}\label{comment-label}\ref{comment-ref}\cite{CommentKey}
\begin{document}
\verb|\include{missing-verb}\label{verb-label}\ref{verb-ref}\cite{VerbKey}|
\begin{verbatim}
\include{missing-verbatim}\label{literal-label}\ref{literal-ref}\cite{LiteralKey}
\end{verbatim}
\begin{lstlisting}
\label{listing-label}\ref{listing-ref}\cite{ListingKey}
\end{lstlisting}
\begin{minted}{tex}
\label{minted-label}\ref{minted-ref}\cite{MintedKey}
\end{minted}
\label{real-label}\ref{real-label}\cite{Known}
\bibliography{refs}
\end{document}
"""
        tex.write_text(source, encoding="utf-8")
        bib.write_text(
            "@article{Known, author={A. Author}, title={Known}, year={2020}}\n",
            encoding="utf-8",
        )
        structure = _tex_structure_view(source)
        self.assertEqual(len(source), len(structure))
        self.assertEqual(
            [index for index, char in enumerate(source) if char == "\n"],
            [index for index, char in enumerate(structure) if char == "\n"],
        )
        self.assertIn(r"\label{real-label}", structure)
        self.assertNotIn("comment-label", structure)
        self.assertNotIn("literal-label", structure)
        result = run_audit(tex, self.root / "structure-review")
        forbidden_checks = {
            "latex-reference-missing-label",
            "latex-citation-missing-bib-key",
            "latex-unused-label",
        }
        self.assertFalse(forbidden_checks & {item["check_id"] for item in result["findings"]})
        self.assertNotIn(
            "tex-include-missing", {item["code"] for item in result["diagnostics"]}
        )

    def test_markdown_code_and_comments_are_not_prose(self):
        source = """# Methods
```text
self-resetting XYZ reached 10MPa; Table 9 is shown.
```
Inline `post tensioned ABC at 20kN` is code.
<!-- self-resetting DEF reached 30MPa -->
The response remained stable.
"""
        view = _markdown_prose_view(source)
        self.assertEqual(len(source), len(view))
        self.assertEqual(
            [index for index, char in enumerate(source) if char == "\n"],
            [index for index, char in enumerate(view) if char == "\n"],
        )
        _, _, result = self.audit_text("code.md", source)
        blocked_categories = {"abbreviation", "terminology", "unit", "cross-reference"}
        self.assertFalse(blocked_categories & {item["category"] for item in result["findings"]})

    def test_reference_titles_are_excluded_from_prose_rules(self):
        _, _, result = self.audit_text(
            "references.md",
            """# Results
The response remained stable.

# References
Smith, A. Behaviour of XYZ self-resetting frames at 10MPa; see Table 9.
""",
        )
        self.assertEqual([], result["findings"])

    def test_configured_mixed_case_abbreviation_uses_first_token(self):
        _, _, result = self.audit_text(
            "cor.txt",
            """Abstract
The coefficient of restitution (CoR) was measured. CoR controlled rebound.

Introduction
CoR governed the impact response. CoR was varied parametrically.
""",
        )
        first_use = [
            item
            for item in result["findings"]
            if item["check_id"] == "abbreviation-first-use" and "CoR" in item["observation"]
        ]
        self.assertEqual(1, len(first_use))
        self.assertEqual("body", first_use[0]["location"]["scope"])

    def test_pdftotext_timeout_is_a_diagnostic(self):
        diagnostics = []
        with patch("audit_manuscript.shutil.which", return_value="pdftotext"), patch(
            "audit_manuscript.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pdftotext", PDFTEXT_TIMEOUT_SECONDS),
        ):
            text, pages = _pdf_text(self.root / "slow.pdf", diagnostics, "slow.pdf")
        self.assertEqual("", text)
        self.assertEqual({}, pages)
        self.assertIn("pdf-extraction-timeout", {item["code"] for item in diagnostics})

    def test_existing_outputs_require_explicit_force(self):
        manuscript = self.root / "overwrite.md"
        manuscript.write_text("# Results\nThe force reached 20kN.\n", encoding="utf-8")
        output = self.root / "overwrite-review"
        output.mkdir()
        findings_path = output / "findings.json"
        report_path = output / "review-report.md"
        findings_path.write_text("do-not-overwrite", encoding="utf-8")
        report_path.write_text("do-not-overwrite", encoding="utf-8")
        with self.assertRaises(AuditError):
            run_audit(manuscript, output)
        self.assertEqual("do-not-overwrite", findings_path.read_text(encoding="utf-8"))
        self.assertEqual("do-not-overwrite", report_path.read_text(encoding="utf-8"))
        result = run_audit(manuscript, output, force=True)
        self.assertEqual(
            result["findings"],
            json.loads(findings_path.read_text(encoding="utf-8"))["findings"],
        )
        arguments = build_parser().parse_args([str(manuscript), "--force"])
        self.assertTrue(arguments.force)

    def test_severity_override_is_applied(self):
        manuscript = self.root / "severity.md"
        manuscript.write_text("# Results\nThe force reached 20kN.\n", encoding="utf-8")
        profile = self.write_profile(
            "major-profile.json",
            {"severity_overrides": {"unit-spacing": "Major"}},
        )
        result = run_audit(
            manuscript, self.root / "severity-review", profile_path=profile
        )
        finding = next(
            item for item in result["findings"] if item["check_id"] == "unit-spacing"
        )
        self.assertEqual("Major", finding["severity"])

    def test_invalid_severity_override_fails_before_writing(self):
        manuscript = self.root / "invalid-severity.md"
        manuscript.write_text("# Results\nThe force reached 20kN.\n", encoding="utf-8")
        profile = self.write_profile(
            "invalid-profile.json",
            {"severity_overrides": {"unit-spacing": "Critical"}},
        )
        output = self.root / "invalid-severity-review"
        with self.assertRaisesRegex(AuditError, "severity_overrides"):
            run_audit(manuscript, output, profile_path=profile)
        self.assertFalse((output / "findings.json").exists())
        self.assertFalse((output / "review-report.md").exists())

    def test_hardcoded_latex_cross_reference_check_can_be_disabled(self):
        manuscript = self.root / "hardcoded.tex"
        manuscript.write_text(
            r"""\section{Results}
The response is shown in Fig. 1.
""",
            encoding="utf-8",
        )
        profile = self.write_profile(
            "no-hardcoded-profile.json",
            {"checks": {"hardcoded_latex_cross_references": False}},
        )
        result = run_audit(
            manuscript, self.root / "hardcoded-review", profile_path=profile
        )
        self.assertNotIn(
            "latex-hardcoded-cross-reference",
            {item["check_id"] for item in result["findings"]},
        )

    def test_abbreviation_scopes_can_be_merged_by_profile(self):
        manuscript = self.root / "merged-scopes.txt"
        manuscript.write_text(
            """Abstract
A self-centering (SC) frame was tested. SC reduced residual drift.

Introduction
SC frames were analyzed. SC response was stable.
""",
            encoding="utf-8",
        )
        profile = self.write_profile(
            "merged-profile.json",
            {"abbreviations": {"require_definition_in_abstract_and_main_text": False}},
        )
        result = run_audit(
            manuscript, self.root / "merged-review", profile_path=profile
        )
        self.assertFalse(
            any(
                item["check_id"] == "abbreviation-first-use"
                and "SC" in item["observation"]
                for item in result["findings"]
            )
        )

    def test_docx_is_read_without_modifying_source(self):
        manuscript = self.root / "paper.docx"
        document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Methods</w:t></w:r></w:p>
    <w:p><w:r><w:t>The peak stress was 10MPa.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
        with zipfile.ZipFile(manuscript, "w") as archive:
            archive.writestr("word/document.xml", document_xml)
        before = manuscript.read_bytes()
        result = run_audit(manuscript, self.root / "docx-review")
        self.assertEqual(before, manuscript.read_bytes())
        unit_findings = [
            finding for finding in result["findings"] if finding["check_id"] == "unit-spacing"
        ]
        self.assertEqual(1, len(unit_findings))
        self.assertEqual(2, unit_findings[0]["location"]["paragraph"])

    def test_source_is_unchanged_and_finding_ids_are_stable(self):
        manuscript = self.root / "stable.md"
        manuscript.write_bytes(b"# Results\nThe force reached 20kN.\n")
        before = manuscript.read_bytes()
        first = run_audit(manuscript, self.root / "review-one")
        second = run_audit(manuscript, self.root / "review-two")
        self.assertEqual(before, manuscript.read_bytes())
        self.assertEqual(
            [finding["id"] for finding in first["findings"]],
            [finding["id"] for finding in second["findings"]],
        )


if __name__ == "__main__":
    unittest.main()
