---
name: paper-auditor
description: Plan and audit scholarly manuscripts with a writing-stage paper spine, cross-section traceability, and evidence-led checks for language and tense, abbreviations and terminology, figure/table/equation callouts, citation integrity and authenticity, claim-to-source support, formula/symbol/unit/value consistency, engineering-standard editions/clauses/applicability, technical logic, claim consistency, evidence provenance, and review completeness. Use while outlining or drafting, for section-level or pre-submission review, manuscript quality control, reviewer-style critique, targeted checks of Word (.docx), LaTeX (.tex/.bib), PDF, Markdown, or plain-text papers, or when personalizing review rules, especially in structural and earthquake engineering, seismic resilience, and self-centering or rocking systems.
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
- Read `references/manuscript-architecture.md` for `draft` mode, section-level review, paper-spine planning, or cross-section logic tracing.
- Read `references/journal-benchmarks.md` when the user names EESD, Engineering Structures, ASCE, or asks for journal-style review.
- Read `references/personalization-guide.md` when the user asks to add, remove, or change personal review rules.
- Read `references/tooling-reference.md` only when the user asks how the Skill was designed or wants optional open-source integrations.
- Read `references/evidence-spine.md` before a `draft` or `deep` review, a multi-pass `targeted` review, or any final merge of deterministic and semantic findings.

Treat the profile as an editable baseline, not universal truth. Prefer an explicit user instruction or a named journal's current author guidance over the baseline. Some profile fields configure the deterministic scripts; others guide the semantic and journal passes performed by the reviewing agent.

## Choose the mode

Use an explicit mode requested by the user. Otherwise read `default_mode` from `references/personal-profile.json`; the shipped profile initially uses `deep`.

- Use `draft` while planning or writing. Review only available text, maintain the intended paper spine, and distinguish `planned` or `not_yet_written` work from an evidenced defect.
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
4. Resolve every bundled script path relative to the directory containing this `SKILL.md`; do not assume that the current working directory is the Skill directory. On Windows, substitute the absolute Skill root and quote every path containing spaces. If Windows PowerShell renders Chinese CLI text incorrectly, invoke Python as `python -X utf8`:

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" --output-dir "<new-review-dir>"
```

Pass `--profile` or `--terms` only when using non-default configuration. In `draft` mode, also pass `--manuscript-stage draft`; otherwise keep the default `complete`. Use a new output directory. If a prior report must be replaced, use `--force` only after confirming that the existing report may be overwritten. Use the structured JSON as evidence, not as the final judgment.

Before a `draft` or `deep` review, or any review whose final report combines multiple passes, initialize the shared evidence spine and a reviewer-authored paper spine. Use one complete set of commands for the selected mode.

For a writing-stage review:

```powershell
# Draft manuscript
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" --mode draft --output-dir "<new-review-root>\spine"
python "<skill-root>\scripts\manuscript_map.py" init "<new-review-root>\manuscript-map.json" --stage draft
python "<skill-root>\scripts\manuscript_map.py" validate "<new-review-root>\manuscript-map.json" --ledger "<new-review-root>\spine\evidence-ledger.json" --completion draft --output-dir "<new-review-root>\manuscript-map-review"
```

For a finished manuscript:

```powershell
# Complete manuscript for deep review
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" --mode deep --output-dir "<new-review-root>\spine"
python "<skill-root>\scripts\manuscript_map.py" init "<new-review-root>\manuscript-map.json" --stage complete
python "<skill-root>\scripts\manuscript_map.py" validate "<new-review-root>\manuscript-map.json" --ledger "<new-review-root>\spine\evidence-ledger.json" --completion complete --output-dir "<new-review-root>\manuscript-map-review"
```

If the user has only an idea in chat and no manuscript or project-brief file, discuss the plan without claiming an evidence-backed completed review. To start the evidence spine, first preserve the user-approved brief as a new input file; never overwrite an existing manuscript.

Populate the card, nodes, edges, statuses, and current `evidence_ids` from the actual manuscript and author decisions; never infer them from keyword overlap. Validate every later map revision against the current ledger.

Declare every bibliography, appendix, rendered PDF, profile, terminology file, quantity profile, standards registry, local cited source, cited-source map, and figure/table data file that can affect the review. Use `--artifact ROLE=PATH` and `--rendered-artifact` as specified in `references/evidence-spine.md`. A cited source's filename stem is its default citation identity; when that differs from the manuscript citation key, declare the exact local binding as a `cited_source_map`. Never declare a bare `standard_source`; use `--standards-source-map` and the standards registry so rights, processing mode, and any required publisher permission are checked before the file is opened or hashed. Keep the generated manifest, ledger, and coverage files private with the review outputs.

All contributing passes must use the same `ledger_fingerprint`. Record each pass through `evidence_spine.py record-pass`. `deterministic_text`, `language_tense`, `abbreviation_terminology`, and `claim_logic` always apply when required and cannot be `not_applicable`. Another pass may be `not_applicable` only when its contract permits it and a current source-bound inventory has a non-empty scope, `item_count: 0`, an empty `items` list, and a rationale. `not_run`, `failed`, `insufficient_evidence`, and stale results can never mean “no problem.”

## Run the audit

### 1. Deterministic pass

Check abbreviations, preferred/forbidden terminology, US/UK spelling, unit typography, captions and callouts, LaTeX labels/references/citations, and bibliography use. Treat the abstract and main text as separate abbreviation scopes: require a first-use definition in each scope and, when the profile enables it, flag a later return to the learned full term after that definition. Confirm parser warnings before treating absence as a manuscript defect.

With `--manuscript-stage draft`, a missing plain-text callout or LaTeX label is moved to `planned_items` only when the same local clause explicitly says that the target is being prepared/finalized or will be added, reported, or compared. Preserve those items as writing work, not formal findings. Do not generalize this exception to ambiguous future language, unrelated callouts on the same line, or complete manuscripts.

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

In `draft` mode, read all material currently available and state the reviewed scope; do not claim whole-manuscript consistency. In `deep` mode, read the complete manuscript before finalizing findings. Use the shared evidence ledger and register the manuscript spans supporting every semantic proposal.

Create or update the reviewer-authored paper spine described in `references/manuscript-architecture.md`. Map functional nodes rather than heading names, and trace both directions across `gap → (research question | objective | hypothesis) → method → result ↔ figure/table → interpretation → conclusion`. A combined Results and Discussion section or custom engineering section is valid when its functions remain traceable.

Check:

- abstract–body parity for objectives, methods, principal results, comparison conditions, scope, and conclusion strength;
- objectives without capable methods, outcome-producing methods without results, and emphasized results without declared methods;
- whether each important figure or table identifies the entity, condition, variables, units, statistic, baseline, panels, and uncertainty needed to support the nearby claim;
- whether title, discussion, and conclusion claims remain inside the tested system, loading or hazard, parameter range, statistic, baseline, and stated limitations;
- whether numerical values, specimen descriptions, boundary conditions, failure modes, novelty claims, causal language, and central viewpoints remain consistent.

Use stable `check_id` values where applicable: `title-body-scope-mismatch`, `abstract-body-untraceable-claim`, `objective-method-gap`, `method-result-gap`, `result-method-gap`, `conclusion-result-gap`, `discussion-new-evidence`, and `visual-not-self-contained`. These identifiers do not lower the evidence threshold. A formal broken-link finding still requires reproducible anchors for every affected node and the exact identity dimensions that should match.

In `draft` mode, keep intended but unwritten work as `planned` or `not_yet_written`. Put ambiguity, author intent, unavailable future evidence, and unresolved alternatives in `questions_for_author`; do not assign defect severity. Put dependency-ordered work in `next_writing_tasks`.

The completed `claim_logic` pass result must set `semantic_audit_status: completed`. Embed the complete ledger-bound validator output under `manuscript_map_validation` and add a `semantic_review` object. Its non-empty `reviewed_by` must exactly match the `record-pass --reviewer` identity; its scope and input/ledger fingerprints must be current. Review every map node and edge exactly once with an assessment and rationale, and review every `contract_gap` exactly once by index, code, and path. Keep `questions_for_author` and `next_writing_tasks` beside this checklist. The validator states that it did not perform semantic review and cannot substitute for the named, exhaustive outer review.

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

Inspect rendered PDF or Word pages in `deep` mode. In `draft` mode, inspect only figures and tables that currently exist. An explicitly local future callout produced by the deterministic pass remains a `planned_item` and becomes `draft_planned_items` only after final source anchoring; a reviewer-authored visual action belongs in the separate `next_writing_tasks` list. Verify evidence self-containment, legibility, panel labels, captions, entities, conditions, symbols, units, statistics, baselines, legends, numbering, sequential callouts, and agreement between visual trends and prose. Do not infer unreadable values. Label OCR or extraction uncertainty.

## Produce the report

Preserve every pass result in its own directory. When the evidence spine is active, record all completed, not-applicable, failed, and evidence-limited passes into a new coverage file, then run:

Every `completed` or `not_applicable` result must declare its exact `pass_id`, a native non-empty string `schema_version`, and a current source/provenance binding. A zero-finding semantic result must explicitly state `summary.review_completed: true`. Finalization reloads the actual producer JSON and rederives its identity, execution evidence, counts, inventory, and binding; cached coverage metadata is compared with that reconstruction, not treated as authoritative.

```powershell
python "<skill-root>\scripts\evidence_spine.py" finalize "<artifact-manifest.json>" "<evidence-ledger.json>" "<latest-coverage.json>" --output-dir "<new-final-review-dir>"
```

Use the resulting `review-report.md` and `findings.json` as the final projection. Do not manually concatenate producer JSON. A map with `status: valid` is projected as the paper spine card, traceability table, satisfied/unresolved functional connections, `argument_status`, and any `contract_gaps`; only `argument_status: closed` means a complete evidence-bound chain. Anchored `draft_planned_items`, `questions_for_author`, and `next_writing_tasks` remain separate from both formal findings and `manual_checks`. Preserve evidence candidates, review tasks, unable-to-verify results, and rejected proposals under their appropriate inventories or `manual_checks`; unresolved priority claims, blocked standard tasks, and quantitative candidates require `manual_confirmation_required`, but never promote them to defects merely to fill the report.

A report may say the review is complete only when every required pass is `completed`, or a pass that explicitly permits `not_applicable` has an evidence-backed zero-item inventory, and all producer hashes match the current manifest and ledger. If a required pass is absent or stale, report `incomplete` or `stale` even when there are no formal findings. A complete manuscript whose `argument_status` is unresolved can never receive `ready_given_evidence`: accepted formal defects produce `revision_required`, otherwise author confirmation is required. In `draft` mode, `complete` means the current writing-stage review completed; it never means submission-ready. A clean partial draft uses `submission_readiness: draft_in_progress`.

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
