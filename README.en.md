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

It does not have to wait until submission. At the start of a project, it can help you build a paper storyline card. Halfway through a draft, it keeps the research gap, objective, method, results, figures, interpretation, and conclusion in view. It does not invent or repair the paper's logic for you; it shows which links are supported and which ones still need work.

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

## Bring it in at any stage of the paper

`draft` is the writing-stage mode. Tell Paper Auditor how far the manuscript has progressed; it maintains the storyline and open evidence needs without treating every unfinished section as a submission defect.

If the text explicitly says that Table 1 is being finalized or Figure 3 will be added, the callout becomes a visible draft plan rather than an instant defect. A different unresolved callout on the same line is still checked.

### Before writing: make the backbone visible

```text
Use $paper-auditor in draft mode as a second reader while I plan this paper.

The topic is "<topic>" and the target journal is "<journal>".
I have a research question, a proposed method, and source material,
but no complete manuscript. If this material exists only in the chat,
first turn it into a new project-brief file and use that file as the input.
Without an input file, keep this as planning conversation rather than claiming
an evidence-backed completed review. Do not write the paper for me.
First build a paper storyline card:
research gap → research question, objective, or hypothesis → method → evidence needed
→ questions the results must answer → interpretation → conclusion boundary.

Show what evidence is missing at each link and suggest a suitable
engineering-paper structure. Allow custom sections such as
Analytical formulation, Numerical model, Experimental program,
and Results and Discussion instead of forcing medical section names.
```

### Halfway through: check whether the story has drifted

```text
Use $paper-auditor in draft mode to review this work in progress:
"<absolute-path-to-manuscript-or-folder>".

Preserve the manuscript. Update the paper storyline card and trace each link:
Does the research gap lead to the objective?
Does each objective have a method, and each method a result?
Which figure or table supports each result?
Do the interpretation and provisional conclusion stay within the evidence?

Mark unfinished material as planned or not_yet_written, not as a formal defect.
End with the three most valuable things to write next.
```

### Complete draft: close the loop before submission

```text
Use $paper-auditor in deep mode to review
"<absolute-path-to-manuscript-or-folder>".

The target journal is "<journal>". Preserve the manuscript.
In addition to language, abbreviations, numbers, citations, visuals,
and engineering standards, build the final paper storyline card and trace:
title and abstract → research gap → research question, objective, or hypothesis → method
→ results and figure/table evidence → interpretation → conclusion.

Focus on abstract claims with no body evidence, results with no stated method,
methods with no corresponding result, and conclusions that outrun the evidence.
Put uncertain concerns in questions for the author instead of guessing.
```

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

A figure or table is evidence here, not decoration. Paper Auditor asks which research question it answers, whether the caption supplies the entity, condition, metric, units, statistic, baseline, and panel meanings, and whether a key statement can be traced back to the visual. If the visual is unreadable or the link is ambiguous, the item stays open for confirmation.

For ASCE, ACI, AISC, Eurocode, GB, and JGJ references, it first checks the complete designation and edition. Provision, equation, and applicability review continues only when the exact edition is available and its processing is permitted. A newer edition is not silently substituted for the edition that governed the study.

### Finally, step back and read the whole argument

Paper Auditor first lays out a storyline card: Does the research gap lead to the objective or hypothesis? Is that objective implemented by a method? Does the method produce a result? Is the result carried by a figure or table and interpreted with appropriate limits? Does the conclusion remain inside the evidence? Important statements in the title and abstract should also trace back to the body.

It does not mark an engineering paper wrong because it lacks literal IMRAD headings. `Analytical formulation`, `Numerical model`, `Experimental program`, `Parametric study`, and a combined `Results and Discussion` section are mapped by the role they actually perform. Ambiguous roles become questions.

For a complete draft, this pass requires the full paper and still leaves final scholarly judgment to the author. Paper Auditor can expose broken links, contradictions, and unsupported claims; it does not claim to understand or repair every piece of academic reasoning automatically. A concern without a reproducible location goes into questions for the author, not into formal findings.

## Choose a working mode

| Mode | When to use it |
| --- | --- |
| `draft` | While planning or writing; maintains the storyline card and turns unfinished links into questions and next tasks without calling the paper submission-ready |
| `fast` | Before sharing a draft; catches clear language, abbreviation, terminology, and in-text/reference-list consistency issues |
| `deep` | Before submission; adds logic, visuals, claim support, quantitative checks, and engineering standards |
| `targeted` | For one requested area, such as abbreviations only or references only |

Use `draft` while writing and `deep` for a complete pre-submission review. Use `targeted` for a narrow check; the review will not quietly expand its scope.

## What you receive

Most users need two files:

- `review-report.md`: the readable report. Blocker and Major findings come first, with source anchors, short quotations, evidence, and actionable suggestions where possible.
- `findings.json`: structured results for tracking, filtering, or later automation.

A deep review also keeps separate records for references, claim support, quantities, standards, and review coverage. You do not need to open every file; the main report gathers the items that need your attention.

In `draft` and complete logic reviews, the main report also brings the storyline card forward: satisfied and unresolved functional links, abstract or conclusion claims without body evidence, unmatched methods and results, and the evidence carried by each important figure or table. Explicitly planned visuals or labels, questions, and next writing tasks remain separate; they are not disguised as manuscript defects.

If an input changes, the review becomes `stale`. If a required pass was not run or was evidence-limited, the review becomes `incomplete`. Unresolved priority claims, standards tasks, or quantitative candidates can set `manual_confirmation_required`. A complete manuscript whose storyline remains `unresolved` can never receive `ready_given_evidence`: accepted formal defects produce `revision_required`; otherwise author confirmation is required. A clean partial draft receives `draft_in_progress`, never “ready to submit.” A clean check and a missing check are never treated as the same thing.

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

In Windows PowerShell 5.1, replace `python` below with `python -X utf8` if Chinese CLI text is garbled.

Deterministic manuscript checks:

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>" `
  --manuscript-stage complete
```

Change `complete` to `draft` for work in progress; explicit future figure/table/label targets then appear under `planned_items`.

Create the evidence spine and storyline map for a `draft` review:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode draft --output-dir "<new-review-root>\spine"
python "<skill-root>\scripts\manuscript_map.py" init `
  "<new-review-root>\manuscript-map.json" --stage draft
python "<skill-root>\scripts\manuscript_map.py" validate `
  "<new-review-root>\manuscript-map.json" `
  --ledger "<new-review-root>\spine\evidence-ledger.json" `
  --completion draft --output-dir "<new-review-root>\manuscript-map-review"
```

Create the evidence spine and storyline map for a complete `deep` review:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep --output-dir "<new-review-root>\spine"
python "<skill-root>\scripts\manuscript_map.py" init `
  "<new-review-root>\manuscript-map.json" --stage complete
python "<skill-root>\scripts\manuscript_map.py" validate `
  "<new-review-root>\manuscript-map.json" `
  --ledger "<new-review-root>\spine\evidence-ledger.json" `
  --completion complete --output-dir "<new-review-root>\manuscript-map-review"
```

In both modes, populate the card, nodes, links, and current `evidence_ids`
from the manuscript and author decisions, not keyword guesses.

Producer `planned_items` become `draft_planned_items` only after final evidence anchoring.
Reviewer-authored `next_writing_tasks` are a separate dependency-ordered list, not duplicates.

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

`draft` and complete `deep` reviews use a shared evidence spine for input hashes, evidence anchors, coverage, and adjudication. See [`references/manuscript-architecture.md`](references/manuscript-architecture.md) for the paper spine, [`references/evidence-spine.md`](references/evidence-spine.md) for the contract, [`references/claim-support.md`](references/claim-support.md) for claim-to-source support, and [`references/standards-verification.md`](references/standards-verification.md) for standards verification.

In addition to the main report, the workflow can produce `manuscript-map-validation.json`, `manuscript-map-traceability.md`, `citation-report.md`, `references.json`, `claim-evidence.json`, `claim-support.json`, `quantitative.json`, `standards.json`, `artifact-manifest.json`, `evidence-ledger.json`, and coverage records. `--force` may replace an existing report, but it cannot overwrite the input manuscript or a BibTeX file that was read.

Run the regression suite:

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

The current version has 196 regression tests, including negative boundaries for core-pass not-applicable bypasses, planned-item impersonation, structural validators posing as semantic review, unmatched spine nodes, forged coverage, stale or manuscript-unbound ledgers, wrong-source binding, false locators, output aliases, and standards rights gates. The core scripts use only the Python standard library. `pdftotext` is optional for PDF extraction.

</details>
