# Citation verification

## Preserve four separate questions

1. Does the cited work exist?
2. Do identifier, title, authors, year, venue, volume, and pages match?
3. Has the work been retracted, corrected, withdrawn, removed, or marked with an expression of concern?
4. Does the cited work support the manuscript's nearby claim?

Metadata can answer only the first three. Require the cited full text or direct publisher evidence for the fourth.

## Verification order

1. Match every in-text citation to one bibliography entry and every bibliography entry back to at least one in-text citation.
2. Normalize DOI, PMID, arXiv ID, ISBN, and URL without changing the stored original.
3. Resolve an existing identifier through its registration agency or authoritative subject database.
4. Compare returned metadata field by field. Treat a resolving DOI with conflicting title/authors as an identifier conflict.
5. For entries without an identifier, retrieve several candidates using title, author, and year. Require a strong score and adequate separation from the runner-up.
6. Check Crossref update metadata and current Retraction Watch production data. Use OpenAlex or Semantic Scholar as corroborating indexes, not automatically independent sources.
7. Open the publisher or Crossmark record for high-risk discrepancies.

Preferred sources are publisher records, Crossref/DataCite, Retraction Watch production data, PubMed for biomedical material, arXiv for preprints, and discipline-specific authoritative repositories. Record URLs, access time, result status, and a response hash when a script performs the query.

## Claim-support verification

Metadata verification and claim-support verification are separate passes. After `verify_references.py` produces `references.json`, follow `references/claim-support.md`:

```powershell
python "<skill-root>\scripts\claim_support.py" prepare "<manuscript>" --references-json "<citation-review-dir>\references.json" --sources-dir "<lawful-local-paper-sources>" --output-dir "<new-claim-evidence-dir>" --scope priority
```

The prepare step locates each citation, separates citation clusters into claim-reference pairs, matches local source text, and ranks short evidence candidates. Retrieval score is only a search aid. Read the passage in context and record a decision for every pair. Then run:

```powershell
python "<skill-root>\scripts\claim_support.py" finalize "<claim-evidence-dir>\claim-evidence.json" "<claim-decisions.json>" --output-dir "<new-claim-result-dir>"
```

Use exactly `supports`, `partially_supports`, `does_not_support`, or `unable_to_verify`. `does_not_support` requires direct mismatch or contradiction evidence from accessible full text. Lack of full text, a low retrieval score, or a missing passage is never evidence of non-support. Preserve the manuscript claim, citation location, source identifier and hash, selected passage location, verdict, rationale, scope/quantity/population/method mismatch dimensions, and verification date.

## Status vocabulary

- `verified`
- `verified_with_warnings`
- `identifier_conflict`
- `ambiguous`
- `not_found`
- `verification_unavailable`
- `retracted_or_updated`

`not_found` means no adequate match was found in the queried sources. It is not proof of fabrication. Books, standards, reports, theses, local-language journals, and grey literature require appropriate catalogues or manual review. Keep network failures and rate limits under `verification_unavailable`.

## Privacy

Send only DOI or the minimum title/author/year string under the default profile. Do not upload the manuscript, citation context, figures, or unpublished claims without explicit permission. Cache results locally when practical, but recheck update/retraction status before submission.
