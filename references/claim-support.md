# Claim-support verification

Use this workflow to answer one narrow question: **does each cited source support
the manuscript claim attached to that citation?**  Do not merge this question
with bibliographic existence or metadata accuracy.

## Evidence chain

Every assessment must preserve this chain:

```text
manuscript claim
→ reproducible citation location
→ uniquely identified reference
→ accessible source text
→ short source quotation with page/paragraph anchor
→ verdict, confidence, scope comparison, and suggested revision
```

The deterministic preparation stage retrieves evidence candidates.  Candidates
are search results, not conclusions.  A human or reviewing agent must inspect
the candidates and, when necessary, search the complete local source before
recording a decision.

## Source access

Prefer sources in this order:

1. a PDF or text document provided by the user;
2. an open-access publisher or repository file whose URL the user supplied;
3. publisher full text opened directly during manual review.

Read local sources without modifying them.  Open-access downloading is disabled
by default and requires explicit authorization.  Never bypass a paywall, reuse
browser credentials, upload an unpublished manuscript claim to an external
service, or save copyrighted full text inside the Skill.

An explicit `source-map.json` should bind a citation key or DOI to exactly one
local path or open URL:

```json
{
  "schema_version": "0.1.0",
  "sources": [
    {
      "citation_key": "Smith2021",
      "doi": "10.1234/example",
      "path": "cited-papers/Smith2021.pdf",
      "access": "user-provided"
    }
  ]
}
```

Reject an automatic binding when a DOI detected in the source conflicts with
the reference DOI.  Treat closely ranked candidates as ambiguous rather than
guessing.

## Preparing evidence

Run from the Skill root, resolving the script path absolutely when necessary:

```powershell
python "<skill-root>\scripts\claim_support.py" prepare "paper.tex" `
  --references-json "review\references.json" `
  --sources-dir "cited-papers" `
  --source-map "source-map.json" `
  --output-dir "review\claim-support" `
  --scope priority
```

Use `--scope all` to inspect every detected citation.  During writing, narrow a
run with `--section`, `--citation-key`, or `--line-range 80:130`.

Preparation writes `claim-evidence.json` and `claim-evidence.md`.  It ranks local
passages using transparent BM25 text relevance, technical-term coverage, and
exact or converted quantity matches.  It retains short quotations and source
anchors, never the complete source text.

## Assessment dimensions

For each claim–reference pair, compare at least the material dimensions among:

- research object and structural system;
- specimen, population, intervention, or method;
- boundary and loading conditions;
- response quantity and failure mode;
- direction and magnitude;
- causal versus associative wording;
- parameter range and claimed generality;
- standard edition, clause, or time period;
- stated limitations and exceptions.

Split a sentence when one citation is attached to several independent
propositions.  Assess every source in a citation cluster separately.  A source
that supports one clause does not automatically support the other clauses or
the other cited sources.

## Verdicts

### `supports`

Use only when accessible full text directly supports every material dimension
of the claim.  Exact quantities must agree or have a reproducible unit
conversion.  Minimum confidence: `0.80`.

### `partially_supports`

Use when at least one central proposition is directly supported but a material
qualifier, condition, population, magnitude, causal strength, or parallel
proposition is narrower, missing, or different.  Minimum confidence: `0.70`.

### `does_not_support`

Use only when accessible full text provides direct contradiction or establishes
a clear mismatch of object, condition, response, direction, or claimed result.
Select the passage that demonstrates the conflict and identify at least one
`mismatch` or `contradiction` dimension.  Minimum confidence: `0.80`.

**Failure to retrieve a passage is never sufficient for this verdict.**

### `unable_to_verify`

Use when the full text is missing or unreadable, the citation/source binding is
ambiguous, only an abstract is available, extraction coverage is inadequate,
the claim is too vague, or confidence cannot meet another verdict's threshold.
An abstract that appears consistent may be noted, but it does not become a
full-text support finding.

## Decision file

Create `claim-decisions.json` without altering `claim-evidence.json`:

```json
{
  "decisions": [
    {
      "claim_id": "CLM-A13F80",
      "citation_key": "Smith2021",
      "verdict": "partially_supports",
      "confidence": 0.91,
      "rationale": "The source reports reduced residual drift but does not show complete elimination.",
      "evidence_ranks": [1, 3],
      "dimension_matches": {
        "system": "match",
        "outcome": "partial",
        "magnitude": "mismatch",
        "scope": "partial"
      },
      "suggested_revision": "Replace ‘eliminates’ with ‘substantially reduces’ and state the tested range.",
      "severity": "Major",
      "reviewer": "independent citation pass"
    }
  ]
}
```

Allowed dimension values are `match`, `partial`, `mismatch`, `contradiction`,
`unclear`, and `not_applicable`.  Provide exactly one decision for every
claim–reference pair.

Finalize only after reviewing the selected quotations:

```powershell
python "<skill-root>\scripts\claim_support.py" finalize `
  "review\claim-support\claim-evidence.json" `
  "review\claim-support\claim-decisions.json" `
  --output-dir "review\claim-support"
```

The finalizer validates source availability, confidence thresholds, evidence
ranks, and dimension/verdict consistency.  It writes `claim-support.json` and
`claim-support-report.md`.  Only high-confidence non-support or material partial
support becomes a formal finding; support remains an inventory, and unavailable
cases become questions or source requests for the author.

## Severity and reporting

- Use **Blocker** only when a high-confidence unsupported citation invalidates a
  central conclusion or reverses a critical quantitative interpretation, and
  independently recheck it.
- Use **Major** when the mismatch materially affects technical interpretation,
  novelty, scope, or reproducibility.
- Use **Minor** when the source supports the substance but attribution wording
  needs a narrow qualification.
- Never raise severity merely because a source is unavailable.

Keep quotations short.  Never invent a page, passage, DOI, source match, or
verdict.  Preserve `unable_to_verify` when the evidence chain is incomplete.
