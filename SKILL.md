---
name: paper-auditor
description: Audit scholarly manuscripts for language and tense issues, abbreviation and terminology consistency, figure/table/equation callouts, citation-reference integrity and authenticity, quantitative consistency, technical logic, and claim consistency. Use for pre-submission review, manuscript quality control, reviewer-style critique, targeted checks of Word (.docx), LaTeX (.tex/.bib), PDF, Markdown, or plain-text papers, or when personalizing and updating manuscript-review rules, especially in structural and earthquake engineering, seismic resilience, and self-centering or rocking systems.
---

# Paper Auditor

Audit the manuscript as an evidence-led reviewer. Preserve the source by default. Separate deterministic defects from semantic concerns and external verification results.

## Load the profile

Read `references/personal-profile.json` and `references/terminology.tsv` before reviewing. Read only the additional reference needed for the task:

- Read `references/review-rubric.md` for severity, confidence, evidence, tense, logic, and report rules.
- Read `references/citation-verification.md` before checking references or claims against external sources.
- Read `references/domain-style.md` for structural and earthquake engineering terminology and reasoning checks.
- Read `references/journal-benchmarks.md` when the user names EESD, Engineering Structures, ASCE, or asks for journal-style review.
- Read `references/personalization-guide.md` when the user asks to add, remove, or change personal review rules.
- Read `references/tooling-reference.md` only when the user asks how the Skill was designed or wants optional open-source integrations.

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

## Run the audit

### 1. Deterministic pass

Check abbreviations, preferred/forbidden terminology, US/UK spelling, unit typography, captions and callouts, LaTeX labels/references/citations, and bibliography use. Confirm parser warnings before treating absence as a manuscript defect.

### 2. Language and tense pass

Review sentence-level grammar and section-level tense in context. Do not enforce a single tense mechanically. Distinguish established knowledge, actions completed in the study, descriptions of figures/tables, and conclusions that remain true. Report a tense issue only when the local choice is grammatically wrong or the shift obscures the timeline or claim.

### 3. Terminology and notation pass

Build a ledger for important concepts, symbols, units, abbreviations, component names, and hyphenation. Distinguish intentional technical differences from accidental synonyms. Flag a term as technically wrong only when supported by the manuscript's definition, the personal glossary, a named standard, or authoritative literature.

### 4. Claim and logic pass

Read the complete manuscript before finalizing findings. Build a compact claim ledger spanning title, abstract, introduction, methods, results, discussion, and conclusions. Check:

- whether objectives, methods, results, and conclusions align;
- whether novelty claims are supported and consistently scoped;
- whether numerical values, specimen descriptions, boundary conditions, and failure modes agree across sections;
- whether causal language exceeds the study design or evidence;
- whether limitations stated earlier disappear from the conclusion;
- whether figures and tables support the direction, magnitude, and comparison described in text.

In `deep` mode, delegate independent language/terminology, logic/claims, citations, and figures/tables passes when parallel review materially helps. Give a separate reviewer only the raw manuscript and this skill; do not reveal expected defects. Independently recheck every Blocker or Major semantic finding.

### 5. Citation pass

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

### 6. Visual pass

Inspect the rendered PDF or rendered Word pages in `deep` mode. Verify legibility, panel labels, captions, symbols, units, legends, numbering, sequential callouts, and agreement between visual trends and prose. Do not infer unreadable values. Label OCR or extraction uncertainty.

## Produce the report

Create `review-report.md` and `findings.json` in a separate review directory. Preserve deterministic outputs and add semantic findings using the same schema.

For every formal finding include:

- stable ID and check category;
- severity and confidence as separate fields;
- status (`confirmed`, `likely`, `needs-review`, or `unable-to-verify`);
- source anchor and short quotation;
- observation, expected state, reason, and concrete suggestion;
- evidence source and verification date when external facts are involved;
- whether a safe automatic fix is possible.

Do not issue a formal finding without a reproducible location. Put unanchored concerns in a short "questions for the author" section. Deduplicate overlapping script and semantic findings. Lead with Blocker and Major issues, then provide inventories for abbreviations, terminology, figures/tables, and references.

Offer edits only after reporting. Apply changes only when the user explicitly asks, using a new file, tracked changes, or a reviewable patch.
