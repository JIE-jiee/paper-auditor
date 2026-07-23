---
name: paper-auditor
description: Audit scholarly manuscripts for language and tense issues, abbreviation and terminology consistency, figure/table/equation callouts, citation-reference integrity and authenticity, claim-to-source support, formula/symbol/unit/value consistency, engineering-standard editions/clauses/applicability, technical logic, claim consistency, evidence provenance, and review completeness. Use for pre-submission review, manuscript quality control, reviewer-style critique, targeted checks of Word (.docx), LaTeX (.tex/.bib), PDF, Markdown, or plain-text papers, or when personalizing and updating manuscript-review rules, especially in structural and earthquake engineering, seismic resilience, and self-centering or rocking systems.
---

# Paper Auditor

Audit the manuscript as an evidence-led reviewer. Preserve the source by default. Separate deterministic defects from semantic concerns and external verification results.

## Load the profile

Read `references/personal-profile.json` and `references/terminology.tsv` before reviewing. Read only the additional reference needed for the task:

- Read `references/review-rubric.md` for severity, confidence, evidence, tense, logic, and report rules.
- Read `references/citation-verification.md` before checking references or claims against external sources.
- Read `references/claim-support.md` before judging whether a cited source supports the nearby manuscript claim.
- Read `references/domain-style.md` for structural and earthquake engineering terminology and reasoning checks.
- Read `references/standards-verification.md` before checking engineering-standard editions, clauses, formulas, or applicability.
- Read `references/journal-benchmarks.md` when the user names EESD, Engineering Structures, ASCE, or asks for journal-style review.
- Read `references/personalization-guide.md` when the user asks to add, remove, or change personal review rules.
- Read `references/tooling-reference.md` only when the user asks how the Skill was designed or wants optional open-source integrations.
- Read `references/evidence-spine.md` before a `deep` review, a multi-pass `targeted` review, or any final merge of deterministic and semantic findings.

Treat the profile as an editable baseline, not universal truth. Prefer an explicit user instruction or a named journal's current author guidance over the baseline. Some profile fields configure the deterministic scripts; others guide the semantic and journal passes performed by the reviewing agent.

## Choose the mode

Use an explicit mode requested by the user. Otherwise read `default_mode` from `references/personal-profile.json`; the shipped profile initially uses `deep`.

- Use `fast` for deterministic checks plus a focused editorial scan.
- Use `deep` for a full pre-submission audit. Add semantic, visual, and bibliographic verification passes.
- Use `targeted` when the user requests only one category. Do not silently expand to a full review.

Ask before sending unpublished full text or figures to an external service. Metadata-only DOI/title/author queries are allowed by the default profile. Never expose API keys or manuscript contents in logs.

## Prepare the manuscript

1. Inventory every source file, bibliography, appendix, figure, table, supplement, and compiled PDF.
2. Prefer editable source for textual and cross-reference checks:
   - For Word, preserve paragraph/table anchors and inspect the rendered document when layout matters.
   - For LaTeX, identify the main file, follow `\input` and `\include`, locate `.bib` files, and compile when safe and useful.
   - For PDF, record extraction quality and use page numbers or bounding boxes. Treat PDF-only location and structure findings with lower confidence.
3. Work on a copy when a command may modify files. Do not overwrite the manuscript.
4. Resolve every bundled script path relative to the directory containing this `SKILL.md`; do not assume that the current working directory is the Skill directory. On Windows, substitute the absolute Skill root and quote every path containing spaces:

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" --output-dir "<new-review-dir>"
```

Pass `--profile` or `--terms` only when using non-default configuration. Use a new output directory. If a prior report must be replaced, use `--force` only after confirming that the existing report may be overwritten. Use the structured JSON as evidence, not as the final judgment.

Before a `deep` review or any review whose final report combines multiple passes, initialize the shared evidence spine:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" --mode deep --output-dir "<new-review-root>\spine"
```

Declare every bibliography, appendix, rendered PDF, profile, terminology file, quantity profile, standards registry, local cited source, cited-source map, and figure/table data file that can affect the review. Use `--artifact ROLE=PATH` and `--rendered-artifact` as specified in `references/evidence-spine.md`. A cited source's filename stem is its default citation identity; when that differs from the manuscript citation key, declare the exact local binding as a `cited_source_map`. Never declare a bare `standard_source`; use `--standards-source-map` and the standards registry so rights, processing mode, and any required publisher permission are checked before the file is opened or hashed. Keep the generated manifest, ledger, and coverage files private with the review outputs.

All contributing passes must use the same `ledger_fingerprint`. Record each pass through `evidence_spine.py record-pass`; a `not_applicable` result requires a current inventory with a non-empty scope, `item_count: 0`, an empty `items` list, and a rationale. `not_run`, `failed`, `insufficient_evidence`, and stale results can never mean “no problem.”

## Run the audit

### 1. Deterministic pass

Check abbreviations, preferred/forbidden terminology, US/UK spelling, unit typography, captions and callouts, LaTeX labels/references/citations, and bibliography use. Treat the abstract and main text as separate abbreviation scopes: require a first-use definition in each scope and, when the profile enables it, flag a later return to the learned full term after that definition. Confirm parser warnings before treating absence as a manuscript defect.

### 2. Language and tense pass

Review sentence-level grammar and section-level tense in context. Apply the owner profile by default: completed research work uses the past tense, general conclusions use the present tense, and statements about the proposed model/system's performance use the present tense; completed model development, calibration, and testing actions remain past. Do not enforce a single tense mechanically. Distinguish established knowledge, actions completed in the study, descriptions of figures/tables, and conclusions that remain true. Report a tense issue only when the local choice is grammatically wrong or the shift obscures the timeline or claim.

### 3. Terminology and notation pass

Build a ledger for important concepts, symbols, units, abbreviations, component names, and hyphenation. Distinguish intentional technical differences from accidental synonyms. Flag a term as technically wrong only when supported by the manuscript's definition, the personal glossary, a named standard, or authoritative literature.

### 4. Formula, unit, and numeric pass

For UTF-8 LaTeX, Markdown, or plain text, run the local quantitative checker:

```powershell
python "<skill-root>\scripts\quantitative_checks.py" "<manuscript>" --quantity-profile "<skill-root>\references\quantity-profile.tsv" --output "<new-review-dir>\quantitative.json"
```

Use the output to build ledgers for symbols, definitions, units, repeated quantities, percentages, and cross-section values. Recompute explicit percentages and unit conversions. Compare key values across abstract, methods, results, figures/tables, and conclusions. Treat profile-backed dimension conflicts and directly reproducible calculations as formal findings. Keep unresolved formulas, weak cross-section matches, and figure-peak extraction as review candidates until semantic or visual evidence confirms them. For Word or PDF, perform the same checks from anchored extraction and rendered pages; do not pretend the UTF-8 checker parsed those formats.

### 5. Claim and logic pass

Read the complete manuscript before finalizing findings. Use the shared evidence ledger and register the manuscript spans supporting every semantic proposal. Build a compact central-claim view spanning title, abstract, introduction, methods, results, discussion, and conclusions. Check:

- whether objectives, methods, results, and conclusions align;
- whether novelty claims are supported and consistently scoped;
- whether numerical values, specimen descriptions, boundary conditions, and failure modes agree across sections;
- whether causal language exceeds the study design or evidence;
- whether limitations stated earlier disappear from the conclusion;
- whether figures and tables support the direction, magnitude, and comparison described in text.

In `deep` mode, delegate independent language/terminology, logic/claims, citations, and figures/tables passes when parallel review materially helps. Give a separate reviewer only the raw manuscript and this skill; do not reveal expected defects. For every Blocker or Major semantic finding, record structured alternative explanations and an independent recheck against the current ledger fingerprint. The proposer and rechecker must be different reviewers. Mark material counterevidence as `contested`; never silently erase or reduce the proposed technical impact.

### 6. Citation and claim-support pass

First check in-text citations against the reference list. Then, when online verification is authorized, resolve the script from the Skill root and run:

```powershell
python "<skill-root>\scripts\verify_references.py" "<bibliography-or-manuscript>" --output-dir "<new-review-dir>"
```

The verifier accepts `.bib`, `.tex`, `.md`, `.txt`, `.docx`, and PDF when `pdftotext` is available. Use a new output directory; add `--force` only after confirming that existing citation reports may be overwritten.

Never equate `not_found` with fabrication. Separate:

1. existence of a work;
2. accuracy of title, authors, year, venue, and identifier;
3. retraction, correction, withdrawal, or expression-of-concern status;
4. whether the cited source actually supports the manuscript's nearby claim.

Require the source text or equally direct evidence for item 4.

For important or disputed claims, prepare a source-by-source evidence chain from the manuscript claim to each cited work:

```powershell
python "<skill-root>\scripts\claim_support.py" prepare "<manuscript>" --references-json "<citation-review-dir>\references.json" --sources-dir "<lawful-local-paper-sources>" --output-dir "<new-claim-evidence-dir>" --scope priority
```

Review the returned candidate passages, record one decision for every claim-reference pair in `claim-decisions.json` as specified by `references/claim-support.md`, then finalize:

```powershell
python "<skill-root>\scripts\claim_support.py" finalize "<claim-evidence-dir>\claim-evidence.json" "<claim-decisions.json>" --output-dir "<new-claim-result-dir>"
```

Use only `supports`, `partially_supports`, `does_not_support`, or `unable_to_verify`. A citation cluster must be assessed source by source. Missing full text can only produce `unable_to_verify`; `does_not_support` requires direct mismatch or contradiction evidence from the cited source. Do not enable open-access downloading unless the user explicitly authorizes it.

### 7. Engineering-standard pass

When standards are mentioned, first build a metadata-only edition and locator ledger:

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" --output-dir "<new-standard-review-dir>"
```

Check complete designation, edition, amendments/errata, and mixed editions. A newer registry publication does not automatically govern the study. Clause, equation, table, figure, and applicability findings require the exact edition and direct evidence. Full-text processing is blocked unless an explicit `--source-map` passes the rights policy in `references/standards-verification.md`; ASCE and ACI entries also require a recorded publisher-permission reference. Never reconstruct standard text from memory or secondary guides.

### 8. Visual pass

Inspect the rendered PDF or rendered Word pages in `deep` mode. Verify legibility, panel labels, captions, symbols, units, legends, numbering, sequential callouts, and agreement between visual trends and prose. Do not infer unreadable values. Label OCR or extraction uncertainty.

## Produce the report

Preserve every pass result in its own directory. When the evidence spine is active, record all completed, not-applicable, failed, and evidence-limited passes into a new coverage file, then run:

```powershell
python "<skill-root>\scripts\evidence_spine.py" finalize "<artifact-manifest.json>" "<evidence-ledger.json>" "<latest-coverage.json>" --output-dir "<new-final-review-dir>"
```

Use the resulting `review-report.md` and `findings.json` as the final projection. Do not manually concatenate producer JSON. Preserve evidence candidates, review tasks, unable-to-verify results, and rejected proposals under their appropriate inventories or `manual_checks`; unresolved priority claims, blocked standard tasks, and quantitative candidates require `manual_confirmation_required`, but never promote them to defects merely to fill the report.

A report may say the review is complete only when every required pass is `completed` or has evidence-backed `not_applicable` status and all producer hashes match the current manifest and ledger. If a required pass is absent or stale, report `incomplete` or `stale` even when there are no formal findings.

For every formal finding include:

- stable ID and check category;
- severity and confidence as separate fields;
- status (`confirmed`, `likely`, `needs-review`, or `unable-to-verify`);
- source anchor and short quotation;
- one or more current `evidence_ids` from the shared ledger;
- related source anchors and a reproducible calculation when a cross-location or numeric conflict is involved;
- observation, expected state, reason, and concrete suggestion;
- evidence source and verification date when external facts are involved;
- whether a safe automatic fix is possible.

Do not issue a formal finding without a reproducible location. Put unanchored concerns in a short "questions for the author" section. Deduplicate overlapping script and semantic findings. Lead with Blocker and Major issues, then provide inventories for abbreviations, terminology, figures/tables, and references.

Offer edits only after reporting. Apply changes only when the user explicitly asks, using a new file, tracked changes, or a reviewable patch.
