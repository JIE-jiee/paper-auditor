<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong> · <a href="./README.ja.md">日本語</a>
</p>

# Paper Auditor

A customizable Codex Skill for evidence-led, pre-submission manuscript review. It is tuned for structural and earthquake engineering, seismic resilience, and self-centering or rocking systems, while its personal profile and terminology rules can be adapted to other research fields.

## What it checks

- Grammar, context-aware tense, and English variants;
- First-use definitions and consistency of abbreviations;
- Terminology, notation, units, hyphenation, and component names;
- Figure, table, and equation numbering, callouts, and semantic agreement;
- LaTeX labels, cross-references, citations, and bibliography keys;
- In-text citations against the reference list;
- Bibliographic existence, metadata accuracy, and retraction or correction status;
- Numerical consistency across the abstract, main text, tables, figures, and conclusions;
- Alignment among objectives, methods, results, limitations, conclusions, and claims;
- Whether visual evidence actually supports the trends, magnitudes, and comparisons stated in the prose.

Supported inputs include Word, LaTeX/BibTeX, PDF, Markdown, and plain text. PDF text extraction uses `pdftotext` when needed.

## Review modes

| Mode | Best for |
| --- | --- |
| `fast` | Deterministic checks plus a focused editorial scan |
| `deep` | Full pre-submission review with semantic, logical, visual, and bibliographic passes |
| `targeted` | Only the category requested by the user |

The deterministic scripts provide reproducible checks for formatting, terminology, citations, and cross-references. Full semantic, logical, claim, and visual judgment is performed by Codex through the workflow in `SKILL.md`. Bibliographic metadata verification does not establish whether a source supports a specific claim.

## Install as a Codex Skill

Clone the complete repository into your personal Skill directory. Keep the relative layout of `SKILL.md`, `references/`, and `scripts/` unchanged.

Windows PowerShell:

```powershell
git clone https://github.com/JIE-jiee/paper-auditor.git "$env:USERPROFILE\.codex\skills\paper-auditor"
```

macOS / Linux:

```bash
git clone https://github.com/JIE-jiee/paper-auditor.git "$HOME/.codex/skills/paper-auditor"
```

Then start a new Codex task, for example:

```text
Use $paper-auditor in deep mode to review path/to/main.tex.
Preserve the manuscript and write the results to a new review directory.
```

## Command-line quick start

Deterministic manuscript checks:

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>"
```

Bibliographic metadata verification:

```powershell
python "<skill-root>\scripts\verify_references.py" "<bibliography-or-manuscript>" `
  --output-dir "<new-verification-dir>"
```

Privacy controls:

```text
--offline          Extract only; make no network requests
--no-title-search  Query by DOI only; do not send title, author, or year
```

## Output

- `review-report.md` — a human-readable review;
- `findings.json` — structured findings with stable IDs, severity, confidence, status, anchors, evidence, and suggested fixes;
- `citation-report.md` and `references.json` — bibliographic verification results in a separate directory.

The manuscript is preserved by default and reports are written to a separate directory. `--force` may replace existing reports only; it cannot overwrite the input manuscript or a BibTeX source that was read.

## Personalization

| File | Purpose |
| --- | --- |
| `references/personal-profile.json` | Default mode, English variant, severity, and privacy preferences |
| `references/terminology.tsv` | Preferred terms, forbidden terms, abbreviations, and aliases |
| `references/domain-style.md` | Structural and earthquake engineering terminology and reasoning rules |
| `references/journal-benchmarks.md` | Style benchmarks for EESD, Engineering Structures, and ASCE journals |
| `references/personalization-guide.md` | How to update personal rules safely |

## Privacy and limitations

- Unpublished full text or figures are not sent to external services without permission;
- Default online verification sends only a DOI or minimal title, author, and year metadata;
- `not_found` means that no adequate match was found; it is not proof of fabrication;
- Determining whether a citation supports a nearby claim still requires the source text or equally direct evidence;
- This tool improves review coverage and traceability, but does not replace the final judgment of authors, domain experts, or journal editors.

## Tests

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

The current version includes 32 regression tests. The core scripts use only the Python standard library; `pdftotext` is an optional dependency for PDF extraction.
