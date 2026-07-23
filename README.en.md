<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong> · <a href="./README.ja.md">日本語</a>
</p>

# Paper Auditor

Paper Auditor is a careful second reader before submission. Give it a manuscript and it remembers how you defined an abbreviation, checks the number in the abstract against the conclusion, and follows important citations back to the source text.

> The abstract says 2.0%. Why does the conclusion say 3.0%?
>
> This paper exists, but does it actually support the claim made here?
>
> This abbreviation was already defined. Why has the full term returned?
>
> This experiment is complete. Why is the sentence still in the present tense?

It follows the paper from sentence-level writing to evidence and consistency across the full manuscript. A confirmed finding comes with a source location, evidence, severity, and a practical suggestion. When evidence is insufficient, it records what could not be verified instead of guessing. Your manuscript stays untouched by default.

The current personal rules are tuned for structural and earthquake engineering, seismic resilience, and self-centering or rocking systems. They include style benchmarks drawn from representative papers in EESD, Engineering Structures, and the ASCE Journal of Structural Engineering. Inputs can be Word, LaTeX/BibTeX, PDF, Markdown, or plain text.

## Quick start

### 1. Install it in Codex

Windows PowerShell:

```powershell
git clone https://github.com/JIE-jiee/paper-auditor.git "$env:USERPROFILE\.codex\skills\paper-auditor"
```

macOS / Linux:

```bash
git clone https://github.com/JIE-jiee/paper-auditor.git "$HOME/.codex/skills/paper-auditor"
```

Open a new Codex task after installation.

### 2. Give Codex this request

```text
Use $paper-auditor in deep mode to review
"<absolute-path-to-manuscript-or-folder>".

The target journal is Engineering Structures.
Preserve the manuscript and write the results to a new review directory.
Focus on tense, abbreviations, key values, citation support,
figures and tables, and the logic of the full paper.
```

Replace the path with your `.docx`, `.tex`, `.pdf`, or manuscript folder. If you have a `.bib` file, compiled PDF, figure data, appendices, or lawfully obtained copies of cited sources, point Codex to those too. More complete material allows a more complete review.

It will inventory the available material, read the manuscript, put the most important findings first, and write the report. You decide whether anything is edited. It changes a copy only when you explicitly ask.

## What it asks while reading

### First, make the language hold together

Is this sentence describing a completed experiment or a conclusion that still holds? The personal tense policy uses the past tense for completed research work, the present tense for general conclusions and the performance of the proposed model or system, and the past tense for completed development, calibration, and testing actions.

It also checks grammar, US or UK spelling, terminology, notation, units, component names, and hyphenation. The abstract and main text have separate abbreviation scopes. Each scope needs its own first-use definition, followed by the abbreviation. Repeated definitions, case drift, and a return to the full term are reported.

### Then, watch for numbers that disagree

It tracks whether formula symbols are defined, whether subscripts change meaning, whether dimensions and unit conversions work, and whether stated percentages can be reproduced. Key values are compared across the abstract, body, tables, and conclusions.

When a figure is clear enough, it can also compare a plotted peak with the prose. An uncertain plot reading stays a manual check; it is never presented as a confirmed error.

### Ask one more question about every important citation

The first check matches in-text citations to the reference list. When metadata queries are authorized and available, it also verifies titles, authors, venues, years, DOIs, and correction or retraction status.

The second check matters more: a real paper may still be used for a claim it never made. When lawful source text is available, Paper Auditor follows each chain from manuscript claim to citation location to the cited passage. The outcome is `supports`, `partially_supports`, `does_not_support`, or `unable_to_verify`. Sources in a citation cluster are judged one at a time.

### Look back at figures, equations, and engineering standards

Figure, table, and equation numbering is checked together with first callouts, LaTeX labels, cross-references, and bibliography keys. The review also asks whether the direction, magnitude, and comparison visible in a figure or table really match the prose.

For ASCE, ACI, AISC, Eurocode, GB, and JGJ references, it first checks the complete designation and edition. Provision, equation, and applicability review continues only when the exact edition is available and its processing is permitted. A newer edition is not silently substituted for the edition that governed the study.

### Finally, step back and read the whole argument

Do the objectives, methods, results, limitations, and conclusions connect? Has a novelty claim changed scope? Does the conclusion outrun the evidence? Has a specimen, boundary condition, failure mode, or central viewpoint changed between sections?

This pass requires the full paper. A concern without a reproducible location goes into questions for the author, not into the formal findings.

## Choose a review mode

| Mode | When to use it |
| --- | --- |
| `fast` | Before sharing a draft; catches clear language, abbreviation, terminology, and in-text/reference-list consistency issues |
| `deep` | Before submission; adds logic, visuals, claim support, quantitative checks, and engineering standards |
| `targeted` | For one requested area, such as abbreviations only or references only |

Choose `deep` when you are unsure. Use `targeted` when you want a narrow check; the review will not quietly expand its scope.

## What you receive

Most users need two files:

- `review-report.md`: the readable report. Blocker and Major findings come first, with source anchors, short quotations, evidence, and actionable suggestions where possible.
- `findings.json`: structured results for tracking, filtering, or later automation.

A deep review also keeps separate records for references, claim support, quantities, standards, and review coverage. You do not need to open every file; the main report gathers the items that need your attention.

If an input changes, the review becomes `stale`. If a required pass was not run or was evidence-limited, the review becomes `incomplete`. Unresolved priority claims, standards tasks, or quantitative candidates can separately set submission readiness to `manual_confirmation_required`. A clean check and a missing check are never treated as the same thing.

## Make it yours

This Skill is meant to carry personal writing rules. You can teach it:

- your preferred English variant, default mode, severity, and privacy choices in [`references/personal-profile.json`](references/personal-profile.json);
- preferred terms, forbidden wording, abbreviations, and aliases in [`references/terminology.tsv`](references/terminology.tsv);
- recurring symbols, dimensions, and first-definition requirements in [`references/quantity-profile.tsv`](references/quantity-profile.tsv);
- journal style and domain reasoning rules in [`references/journal-benchmarks.md`](references/journal-benchmarks.md) and [`references/domain-style.md`](references/domain-style.md).

Run it on real manuscripts first. Record which findings you accept, which you reject, and which are manuscript-specific exceptions. Write back only the rules that recur and prove useful. See [`references/personalization-guide.md`](references/personalization-guide.md) for the workflow.

## It also knows when to stop

- Online verification sends only a DOI or minimal title, author, and year metadata by default. Unpublished full text and figures are not sent to external services without permission.
- `not_found` means that no reliable match was found. It is not proof that a reference was fabricated.
- Without the cited source text or equally direct evidence, claim support can only be `unable_to_verify`.
- A local standard still needs a rights-attested source map before provision-level processing. Entries marked `permission-required`, including ASCE and ACI, also need a publisher-permission reference.
- Editable source is better for language and cross-reference checks. PDF review depends on extraction quality, layout, and figure legibility.
- The tool improves coverage and traceability. Authors, domain experts, and journal editors retain the final judgment.

<details>
<summary>Advanced use: scripts, complete artifacts, and tests</summary>

Most users only need to invoke `$paper-auditor` in Codex. Read [`SKILL.md`](SKILL.md) first if you want to control the workflow yourself.

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

Formula, unit, and numeric consistency:

```powershell
python "<skill-root>\scripts\quantitative_checks.py" "<manuscript.tex>" `
  --quantity-profile "<skill-root>\references\quantity-profile.tsv" `
  --output "<new-review-dir>\quantitative.json"
```

Engineering-standard ledger:

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" `
  --output-dir "<new-standard-review-dir>"
```

A complete `deep` review uses a shared evidence spine to record input hashes, evidence anchors, pass coverage, and final adjudication. See [`references/evidence-spine.md`](references/evidence-spine.md) for the contract, [`references/claim-support.md`](references/claim-support.md) for claim-to-source review, and [`references/standards-verification.md`](references/standards-verification.md) for standards rights and verification.

In addition to the main report, the workflow can produce `citation-report.md`, `references.json`, `claim-evidence.json`, `claim-support.json`, `quantitative.json`, `standards.json`, `artifact-manifest.json`, `evidence-ledger.json`, and coverage records. `--force` may replace an existing report, but it cannot overwrite the input manuscript or a BibTeX file that was read.

Run the regression suite:

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

The current version has 131 regression tests. Thirty-one negative cases cover boundaries such as forged coverage, wrong-source binding, false locators, output aliases, and standards rights gates. The core scripts use only the Python standard library. `pdftotext` is optional for PDF extraction.

</details>
