import json
import tempfile
import unittest
from pathlib import Path

from quantitative_checks import (
    QuantityProfileEntry,
    analyze_quantitative_text,
    load_quantity_profile,
    main as quantitative_main,
    normalize_unit,
)


def profile_entry(
    symbol,
    *,
    aliases=(),
    dimension="",
    canonical_unit="",
    require_definition=False,
):
    return QuantityProfileEntry(
        canonical_symbol=symbol,
        aliases=tuple(aliases),
        meaning="test quantity",
        dimension=dimension,
        canonical_unit=canonical_unit,
        scope="global",
        require_definition=require_definition,
    )


class QuantitativeChecksTests(unittest.TestCase):
    def check_ids(self, result):
        return {item["check_id"] for item in result["findings"]}

    def candidate_types(self, result):
        return {item["type"] for item in result["review_candidates"]}

    def test_unit_normalization_and_explicit_conversion(self):
        self.assertEqual("force", normalize_unit("kN").dimension)
        self.assertEqual("stress", normalize_unit("N/mm^{2}").dimension)
        result = analyze_quantitative_text(
            "The calibration used 1000 N = 1 kN.",
            source="paper.txt",
        )
        self.assertNotIn("unit-conversion-mismatch", self.check_ids(result))

        mismatch = analyze_quantitative_text(
            "The calibration used 1000 N = 2 kN.",
            source="paper.txt",
        )
        finding = next(
            item
            for item in mismatch["findings"]
            if item["check_id"] == "unit-conversion-mismatch"
        )
        self.assertEqual(1000, finding["calculation"]["left_normalized"])
        self.assertEqual(2000, finding["calculation"]["right_normalized"])
        self.assertEqual(1, len(finding["related_locations"]))

    def test_incompatible_equivalence_dimensions_are_reported(self):
        result = analyze_quantitative_text(
            "The manuscript states 10 kN = 10 mm.", source="paper.txt"
        )
        self.assertIn("unit-equivalence-dimension-mismatch", self.check_ids(result))

    def test_from_to_percentage_is_recomputed(self):
        result = analyze_quantitative_text(
            "The resistance increased from 10 kN to 12 kN by 10%.",
            source="paper.txt",
        )
        finding = next(
            item
            for item in result["findings"]
            if item["check_id"] == "percentage-change-mismatch"
        )
        self.assertAlmostEqual(20.0, finding["calculation"]["actual_percentage"])

        correct = analyze_quantitative_text(
            "The resistance increased from 10 kN to 12 kN by 20%.",
            source="paper.txt",
        )
        self.assertNotIn("percentage-change-mismatch", self.check_ids(correct))

    def test_configured_symbol_alias_and_required_definition(self):
        result = analyze_quantitative_text(
            r"""\section{Results}
The response was measured as $u_r = 10 \mathrm{mm}$ and $u_r$ remained small.
""",
            source="paper.tex",
            quantity_profile=[
                profile_entry(
                    r"u_{res}",
                    aliases=("u_r",),
                    dimension="length",
                    canonical_unit="mm",
                    require_definition=True,
                )
            ],
        )
        checks = self.check_ids(result)
        self.assertIn("symbol-noncanonical-form", checks)
        self.assertIn("symbol-first-use", checks)
        self.assertTrue(any(item["canonical"] == "u_res" for item in result["symbols"]))

    def test_unconfigured_symbol_becomes_candidate_and_sum_index_is_local(self):
        result = analyze_quantitative_text(
            r"""\section{Methods}
$F$ was recorded. The normalized response is $F/2$.
\begin{equation}
S = \sum_{i=1}^{n} x_i
\end{equation}
""",
            source="paper.tex",
        )
        self.assertIn("symbol-definition-review", self.candidate_types(result))
        self.assertFalse(any(item["canonical"] == "i" for item in result["symbols"]))

    def test_profile_backed_dimension_mismatch_is_formal(self):
        result = analyze_quantitative_text(
            r"""\section{Results}
The measured value was $F = 10 \mathrm{mm}$.
""",
            source="paper.tex",
            quantity_profile=[
                profile_entry("F", dimension="force", canonical_unit="kN")
            ],
        )
        self.assertIn("quantity-unit-dimension-mismatch", self.check_ids(result))

    def test_cross_section_symbol_conflict_and_rounding_tolerance(self):
        entry = profile_entry("F", dimension="force", canonical_unit="kN")
        conflict = analyze_quantitative_text(
            r"""\begin{abstract}
$F = 10.0 \mathrm{kN}$.
\end{abstract}
\section{Conclusions}
$F = 12.0 \mathrm{kN}$.
""",
            source="paper.tex",
            quantity_profile=[entry],
        )
        finding = next(
            item
            for item in conflict["findings"]
            if item["check_id"] == "cross-section-value-conflict"
        )
        self.assertEqual(1, len(finding["related_locations"]))

        rounded = analyze_quantitative_text(
            r"""\begin{abstract}
$F = 10.00 \mathrm{kN}$.
\end{abstract}
\section{Conclusions}
$F = 10.04 \mathrm{kN}$.
""",
            source="paper.tex",
            quantity_profile=[entry],
        )
        self.assertNotIn("cross-section-value-conflict", self.check_ids(rounded))

    def test_weak_cross_section_match_is_review_candidate(self):
        result = analyze_quantitative_text(
            """Abstract
The peak drift was 1.5%.

Conclusions
The peak drift was 2.5%.
""",
            source="paper.txt",
        )
        self.assertNotIn("cross-section-value-conflict", self.check_ids(result))
        self.assertIn("cross-section-value-review", self.candidate_types(result))

    def test_figure_peak_and_unresolved_formula_are_candidates(self):
        result = analyze_quantitative_text(
            r"""\section{Results}
Fig.~\ref{fig:drift} shows a peak drift of 2.0%.
\begin{figure}
\includegraphics{figures/drift.pdf}
\caption{Drift response.}\label{fig:drift}
\end{figure}
\begin{equation}
F = k u
\end{equation}
""",
            source="paper.tex",
            quantity_profile=[
                profile_entry("F", dimension="force", canonical_unit="kN")
            ],
        )
        types = self.candidate_types(result)
        self.assertIn("figure-peak-review", types)
        self.assertIn("formula-dimension-review", types)
        figure = next(
            item for item in result["review_candidates"] if item["type"] == "figure-peak-review"
        )
        self.assertEqual("figures/drift.pdf", figure["figure_path"])
        self.assertEqual("fig:drift", figure["figure_label"])
        json.dumps(result, ensure_ascii=False)

    def test_quantity_profile_loader_accepts_comments_and_validates_dimensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir) / "quantities.tsv"
            profile.write_text(
                "# local manuscript registry\n"
                "canonical_symbol\taliases\tmeaning\tdimension\tcanonical_unit\tscope\trequire_definition\n"
                "F\tP\tforce\tforce\tkN\tglobal\ttrue\n",
                encoding="utf-8",
            )
            loaded = load_quantity_profile(profile)
            self.assertEqual("F", loaded[0].canonical_symbol)
            self.assertEqual(("P",), loaded[0].aliases)
            self.assertTrue(loaded[0].require_definition)

    def test_cli_creates_a_new_output_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manuscript = root / "paper.md"
            manuscript.write_text(
                "Results\nThe peak drift was 2.0%.\n",
                encoding="utf-8",
            )
            output = root / "new-review" / "quantitative.json"

            exit_code = quantitative_main(
                [str(manuscript), "--output", str(output)]
            )

            self.assertEqual(0, exit_code)
            self.assertTrue(output.is_file())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(str(manuscript.resolve()), payload["input"]["path"])


if __name__ == "__main__":
    unittest.main()
