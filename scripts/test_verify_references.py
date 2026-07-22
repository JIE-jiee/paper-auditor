import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_references as vr


def crossref_payload(
    *,
    doi="10.1000/example",
    title="Seismic response of a self-centering frame",
    authors=None,
    year=2024,
    updates=None,
):
    message = {
        "DOI": doi,
        "title": [title],
        "author": authors
        or [
            {"given": "Ada", "family": "Lovelace"},
            {"given": "James", "family": "Clerk"},
        ],
        "issued": {"date-parts": [[year]]},
        "container-title": ["Engineering Structures"],
        "URL": f"https://doi.org/{doi}",
    }
    if updates is not None:
        message["updated-by"] = updates
    return {"status": "ok", "message": message}


class FakeTransport:
    def __init__(self, handler):
        self.handler = handler
        self.urls = []

    def __call__(self, url, headers, timeout):
        self.urls.append(url)
        return self.handler(url, headers, timeout)


def minimal_data(input_path, source_files=None):
    return {
        "schema_version": vr.SCHEMA_VERSION,
        "generated_at": "2026-07-22T00:00:00+00:00",
        "input": {
            "path": str(input_path),
            "entry_count": 0,
            "source_files": [str(path) for path in (source_files or [input_path])],
        },
        "mode": "offline",
        "summary": {status: 0 for status in vr.STATUS_EXPLANATIONS},
        "entries": [],
        "extraction_diagnostics": [],
    }


class ExtractionTests(unittest.TestCase):
    def test_status_vocabulary_and_doi_normalization(self):
        self.assertEqual(
            set(vr.STATUS_EXPLANATIONS),
            {
                "verified",
                "verified_with_warnings",
                "identifier_conflict",
                "ambiguous",
                "not_found",
                "verification_unavailable",
                "retracted_or_updated",
            },
        )
        self.assertEqual(
            vr.normalize_doi("https://doi.org/10.1061/(ASCE)0733-9445(2001)127:2(113)."),
            "10.1061/(asce)0733-9445(2001)127:2(113)",
        )

    def test_bibtex_and_text_extraction(self):
        bib = r"""@article{lovelace2024,
 title={Seismic response of a {Self-Centering} frame},
 author={Lovelace, Ada and Clerk, James}, year={2024},
 journal={Engineering Structures}, doi={10.1000/Example}}
"""
        entry = vr.parse_bibtex(bib, "refs.bib")[0]
        self.assertEqual(entry.doi, "10.1000/example")
        self.assertEqual(entry.authors, ["Lovelace, Ada", "Clerk, James"])
        text = """References
[1] Lovelace, A. (2024). Seismic response of a self-centering frame. https://doi.org/10.1000/example
[2] Clerk, J. (2022). Controlled rocking wall mechanics. Journal of Structural Engineering.
"""
        entries = vr.parse_text_references(text, "paper.txt")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1].year, "2022")

    def test_tex_project_subdirectories_are_allowed_and_merged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bib").mkdir()
            (root / "references").mkdir()
            tex = root / "paper.tex"
            tex.write_text(
                "\\bibliography{bib/refs}\n"
                "\\addbibresource{references/library.bib}\n",
                encoding="utf-8",
            )
            (root / "bib" / "refs.bib").write_text(
                "@article{x,title={First paper},year={2023},doi={10.1000/one}}",
                encoding="utf-8",
            )
            (root / "references" / "library.bib").write_text(
                "@article{y,title={Second paper},year={2024},doi={10.1000/two}}",
                encoding="utf-8",
            )
            entries, diagnostics = vr.extract_entries_with_diagnostics(tex)
            self.assertEqual({entry.doi for entry in entries}, {"10.1000/one", "10.1000/two"})
            self.assertEqual(diagnostics, [])
            data = vr.verify_file(tex, offline=True)
            self.assertEqual(
                {Path(path).name for path in data["input"]["source_files"]},
                {"paper.tex", "refs.bib", "library.bib"},
            )

    def test_tex_unsafe_paths_are_diagnostics_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tex = root / "paper.tex"
            tex.write_text(
                "% \\bibliography{commented}\n"
                "\\bibliography{../outside,refs*}\n"
                "\\addbibresource{https://example.invalid/refs.bib}\n"
                "\\addbibresource{\\jobname.bib}\n",
                encoding="utf-8",
            )
            entries, diagnostics = vr.extract_entries_with_diagnostics(tex)
            self.assertEqual(entries, [])
            codes = {item["code"] for item in diagnostics}
            self.assertIn("bibliography-outside-project-root", codes)
            self.assertIn("unsafe-bibliography-reference", codes)
            self.assertNotIn("commented", " ".join(item["reference"] for item in diagnostics))

    def test_pdf_uses_pdftotext_stdout_with_60s_timeout_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf = Path(temp_dir) / "paper.pdf"
            original = b"%PDF-1.7\nimmutable source bytes\n%%EOF"
            pdf.write_bytes(original)
            extracted = (
                "References\n"
                "[1] Lovelace, A. (2024). Seismic response of a self-centering frame. "
                "https://doi.org/10.1000/example\n"
            ).encode("utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout=extracted, stderr=b"")
            with patch.object(vr.shutil, "which", return_value="pdftotext") as which_mock, patch.object(
                vr.subprocess, "run", return_value=completed
            ) as run_mock:
                entries, diagnostics = vr.extract_entries_with_diagnostics(pdf)
            self.assertEqual(entries[0].doi, "10.1000/example")
            self.assertEqual(diagnostics, [])
            self.assertEqual(pdf.read_bytes(), original)
            which_mock.assert_called_once_with("pdftotext")
            command = run_mock.call_args.args[0]
            self.assertEqual(command[-1], "-")
            self.assertIn(str(pdf.resolve()), command)
            self.assertEqual(run_mock.call_args.kwargs["timeout"], 60)

    def test_pdf_missing_tool_timeout_and_failure_are_clear(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf = Path(temp_dir) / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            with patch.object(vr.shutil, "which", return_value=None):
                with self.assertRaisesRegex(ValueError, "pdftotext"):
                    vr.extract_entries(pdf)
            with patch.object(vr.shutil, "which", return_value="pdftotext"), patch.object(
                vr.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd="pdftotext", timeout=60),
            ):
                with self.assertRaisesRegex(ValueError, "60"):
                    vr.extract_entries(pdf)
            failed = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"bad PDF")
            with patch.object(vr.shutil, "which", return_value="pdftotext"), patch.object(
                vr.subprocess, "run", return_value=failed
            ):
                with self.assertRaisesRegex(ValueError, "退出码 1"):
                    vr.extract_entries(pdf)
            self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), hashlib.sha256(b"%PDF-test").hexdigest())


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.entry = vr.BibliographicEntry(
            key="lovelace2024",
            doi="10.1000/example",
            title="Seismic response of a self-centering frame",
            authors=["Lovelace, Ada", "Clerk, James"],
            year="2024",
            source="refs.bib",
            line=1,
        )

    def test_crossref_verified_and_query_is_doi_only(self):
        def handler(url, _headers, _timeout):
            self.assertIn("10.1000%2Fexample", url)
            self.assertNotIn("unpublished specimen secret phrase", url)
            return vr.FetchResponse(200, crossref_payload(), url=url)

        fake = FakeTransport(handler)
        result = vr.verify_entry(self.entry, fake)
        self.assertEqual((result["status"], result["reason"]), ("verified", "metadata_match"))
        self.assertEqual(len(fake.urls), 1)
        self.assertTrue(result["queries"][0]["response_sha256"])

    def test_datacite_fallback_and_status_distinctions(self):
        def handler(url, _headers, _timeout):
            if "crossref" in url:
                return vr.FetchResponse(404, {}, url=url)
            return vr.FetchResponse(
                200,
                {
                    "data": {
                        "id": "10.1000/example",
                        "attributes": {
                            "doi": "10.1000/example",
                            "titles": [{"title": "Seismic response of a self-centering frame"}],
                            "creators": [
                                {"name": "Lovelace, Ada"},
                                {"name": "Clerk, James"},
                            ],
                            "publicationYear": 2024,
                        },
                    }
                },
                url=url,
            )

        self.assertEqual(vr.verify_entry(self.entry, FakeTransport(handler))["status"], "verified")
        mismatch = FakeTransport(
            lambda url, h, t: vr.FetchResponse(
                200,
                crossref_payload(
                    title="A completely unrelated biomedical trial",
                    authors=[{"given": "Other", "family": "Person"}],
                    year=2018,
                ),
                url=url,
            )
        )
        self.assertEqual(vr.verify_entry(self.entry, mismatch)["status"], "identifier_conflict")
        year_warning = FakeTransport(
            lambda url, h, t: vr.FetchResponse(200, crossref_payload(year=2023), url=url)
        )
        self.assertEqual(
            vr.verify_entry(self.entry, year_warning)["status"], "verified_with_warnings"
        )

    def test_not_found_network_offline_and_metadata_reasons(self):
        missing = FakeTransport(lambda url, h, t: vr.FetchResponse(404, {}, url=url))
        self.assertEqual(
            (vr.verify_entry(self.entry, missing)["status"], vr.verify_entry(self.entry, missing)["reason"]),
            ("not_found", "no_record_found"),
        )

        def fail(*_args):
            raise vr.NetworkFailure("timeout")

        network = vr.verify_entry(self.entry, FakeTransport(fail))
        self.assertEqual((network["status"], network["reason"]), ("verification_unavailable", "network_error"))
        offline = vr.verify_entry(self.entry, fail, offline=True)
        self.assertEqual((offline["status"], offline["reason"]), ("verification_unavailable", "offline"))
        short = vr.verify_entry(vr.BibliographicEntry(title="short"))
        self.assertEqual(short["reason"], "metadata_insufficient")


class OutputSafetyTests(unittest.TestCase):
    def test_existing_output_is_refused_without_partial_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bib"
            source.write_text("source", encoding="utf-8")
            output = root / "review"
            output.mkdir()
            existing = output / "references.json"
            existing.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "--force"):
                vr.write_outputs(minimal_data(source), output)
            self.assertEqual(existing.read_text(encoding="utf-8"), "sentinel")
            self.assertFalse((output / "citation-report.md").exists())

    def test_force_overwrites_old_reports_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bib"
            source.write_text("source", encoding="utf-8")
            output = root / "review"
            output.mkdir()
            (output / "references.json").write_text("old-json", encoding="utf-8")
            (output / "citation-report.md").write_text("old-report", encoding="utf-8")
            vr.write_outputs(minimal_data(source), output, force=True)
            self.assertNotEqual((output / "references.json").read_text(encoding="utf-8"), "old-json")
            self.assertIn("参考文献元数据核验报告", (output / "citation-report.md").read_text(encoding="utf-8"))
            self.assertEqual(source.read_text(encoding="utf-8"), "source")

    def test_force_cannot_overwrite_main_input_or_tex_bib_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            main_input = root / "references.json"
            main_input.write_text("main-source", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "输入源"):
                vr.write_outputs(minimal_data(main_input), root, force=True)
            self.assertEqual(main_input.read_text(encoding="utf-8"), "main-source")

            tex = root / "paper.tex"
            tex.write_text("paper", encoding="utf-8")
            bib_source = root / "citation-report.md"
            bib_source.write_text("bib-source", encoding="utf-8")
            data = minimal_data(tex, [tex, bib_source])
            with self.assertRaisesRegex(ValueError, "输入源"):
                vr.write_outputs(data, root, force=True)
            self.assertEqual(bib_source.read_text(encoding="utf-8"), "bib-source")

    def test_cli_requires_force_for_repeat_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bib = root / "refs.bib"
            bib.write_text(
                "@article{x,title={A sufficiently long seismic title},doi={10.1000/x}}",
                encoding="utf-8",
            )
            output = root / "review"
            args = [str(bib), "--output-dir", str(output), "--offline"]
            self.assertEqual(vr.main(args), 0)
            first = (output / "references.json").read_text(encoding="utf-8")
            self.assertEqual(vr.main(args), 2)
            self.assertEqual((output / "references.json").read_text(encoding="utf-8"), first)
            self.assertEqual(vr.main(args + ["--force"]), 0)
            self.assertEqual(bib.read_text(encoding="utf-8").startswith("@article"), True)


if __name__ == "__main__":
    unittest.main()
