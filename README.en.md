<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong> · <a href="./README.ja.md">日本語</a>
</p>

# Paper Auditor

A customizable Codex Skill for evidence-led, pre-submission manuscript review. It is tuned for structural and earthquake engineering, seismic resilience, and self-centering or rocking systems, while its personal profile and terminology rules can be adapted to other research fields.

## What it checks

- Grammar and English variants;
- Past tense for completed study work; present tense for general conclusions and proposed-model performance;
- Separate first-use definitions in the abstract and main text, followed by consistent abbreviation use;
- Terminology, notation, units, hyphenation, and component names;
- Figure, table, and equation numbering, callouts, and semantic agreement;
- LaTeX labels, cross-references, citations, and bibliography keys;
- In-text citations against the reference list;
- Bibliographic existence, metadata accuracy, and retraction or correction status;
- Whether the cited full text supports the manuscript claim, with separate support, partial-support, non-support, and unable-to-verify outcomes;
- Formula symbols, first definitions, scope, dimensions, unit conversions, percentages, and key-value consistency across sections;
- Complete designations, editions, provision locators, formulas, and applicability for ASCE, ACI, AISC, Eurocodes, GB, and JGJ standards;
- Alignment among objectives, methods, results, limitations, conclusions, and claims;
- Whether visual evidence actually supports the trends, magnitudes, and comparisons stated in the prose.
- Whether inputs, evidence anchors, review passes, and the final report use the same version; unexecuted or evidence-limited passes cannot masquerade as no issue.

Supported inputs include Word, LaTeX/BibTeX, PDF, Markdown, and plain text. PDF text extraction uses `pdftotext` when needed.

## Review modes

| Mode | Best for |
| --- | --- |
| `fast` | Deterministic checks plus a focused editorial scan |
| `deep` | Full pre-submission review with semantic, logical, visual, and bibliographic passes |
| `targeted` | Only the category requested by the user |

The deterministic scripts provide reproducible checks for formatting, terminology, citations, and cross-references. Full semantic, logical, claim, and visual judgment is performed by Codex through the workflow in `SKILL.md`. Bibliographic metadata verification does not establish whether a source supports a specific claim.

## Four core evidence chains

| Capability | Evidence chain | Boundary |
| --- | --- | --- |
| Citation support | Manuscript claim → citation location → cited-source passage → four-way verdict | Missing full text is `unable_to_verify`, never evidence of non-support |
| Formulas, units, and values | Symbol/definition → unit and dimension → calculation → cross-section, table, and figure reconciliation | Plot estimates, weak matches, and unresolved formulas remain review candidates |
| Engineering standards | Complete designation/edition → provision or equation → limits and exceptions → study applicability | A newer publication is not automatically governing; provision content requires the exact text |
| Review completeness | Input manifest → shared evidence ledger → pass coverage → deterministic adjudication | Changed inputs are `stale`; changed or missing pass results are `incomplete` |

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

Initialize the shared evidence spine before a full review:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep --output-dir "<new-review-root>\spine" `
  --artifact "bibliography=<references.bib>"
```

Use `record-pass` after each pass and `finalize` after coverage is complete. See `references/evidence-spine.md` for the complete contract, capability matrix, and semantic Major/Blocker recheck format.
Standard full text cannot be registered as a bare `standard_source`; use `--standards-source-map` so local-processing mode, rights attestation, and any publisher-permission record required for ASCE/ACI entries are checked first. Unverified claims, blocked standards tasks, and quantitative candidates remain visible in `manual_checks` instead of being silently treated as clean.
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

Prepare and finalize citation-support evidence:

```powershell
python "<skill-root>\scripts\claim_support.py" prepare "<manuscript>" `
  --references-json "<citation-review-dir>\references.json" `
  --sources-dir "<lawful-local-paper-sources>" `
  --output-dir "<new-claim-evidence-dir>" --scope priority

python "<skill-root>\scripts\claim_support.py" finalize `
  "<claim-evidence-dir>\claim-evidence.json" "<claim-decisions.json>" `
  --output-dir "<new-claim-result-dir>"
```

Engineering-standard ledger (metadata-only by default):

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" `
  --output-dir "<new-standard-review-dir>"
```

Standard full text is processed locally only when an explicit `--source-map` passes the rights gate. ASCE and ACI entries also require a recorded publisher-permission reference.

Privacy controls:

```text
--offline          Extract only; make no network requests
--no-title-search  Query by DOI only; do not send title, author, or year
```

## Output

- `review-report.md` — a human-readable review;
- `findings.json` — structured findings with stable IDs, severity, confidence, status, anchors, evidence, and suggested fixes;
- `citation-report.md` and `references.json` — bibliographic verification results in a separate directory.
- `claim-evidence.json` and `claim-support.json` — claim-to-source evidence and final support verdicts;
- `quantitative.json` — symbol, unit, dimension, calculation, repeated-value, and review-candidate records;
- `standards.json` and `standards-report.md` — edition ledgers and provision/applicability review tasks.
- `artifact-manifest.json`, `evidence-ledger.json`, `coverage.json`, and `final-evidence-ledger.json` — input hashes, stable manuscript/external-source evidence IDs, pass status, and stale-report provenance.

The manuscript is preserved by default and reports are written to a separate directory. `--force` may replace existing reports only; it cannot overwrite the input manuscript or a BibTeX source that was read.

## Personalization

| File | Purpose |
| --- | --- |
| `references/personal-profile.json` | Default mode, English variant, severity, and privacy preferences |
| `references/terminology.tsv` | Preferred terms, forbidden terms, abbreviations, and aliases |
| `references/domain-style.md` | Structural and earthquake engineering terminology and reasoning rules |
| `references/claim-support.md` | Citation-support workflow and decision format |
| `references/quantity-profile.tsv` | Personal symbol meanings, dimensions, and definition requirements |
| `references/standards-registry.json` | Standard-edition metadata and full-text processing policy |
| `references/standards-verification.md` | Provision, equation, applicability, and rights-gate workflow |
| `references/journal-benchmarks.md` | Style benchmarks for EESD, Engineering Structures, and ASCE journals |
| `references/personalization-guide.md` | How to update personal rules safely |
| `references/evidence-spine.md` | Shared manifest, evidence ledger, coverage, and final adjudication workflow |

## Privacy and limitations

- Unpublished full text or figures are not sent to external services without permission;
- Default online verification sends only a DOI or minimal title, author, and year metadata;
- `not_found` means that no adequate match was found; it is not proof of fabrication;
- Determining whether a citation supports a nearby claim still requires the source text or equally direct evidence;
- Finding a standard PDF locally does not authorize automated processing; provision review follows explicit rights attestation and publisher-permission gates;
- This tool improves review coverage and traceability, but does not replace the final judgment of authors, domain experts, or journal editors.

## Tests

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

The current version includes 131 regression tests, including 31 negative cases for adversarial boundaries such as forged coverage, wrong-source binding, false locators, output aliases, and rights gates. The core scripts use only the Python standard library; `pdftotext` is an optional dependency for PDF extraction.
