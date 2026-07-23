# Engineering-standard verification

Use this workflow when a manuscript cites, quotes, applies, or compares a structural-engineering standard.

## Preserve four separate questions

1. Is the standard designation complete and internally consistent?
2. Is the cited edition the edition intended by the study, governing code, jurisdiction, or experiment date?
3. Does the referenced clause, table, figure, or equation exist in that exact edition?
4. Do the manuscript's formula, interpretation, and application remain within the clause's scope and assumptions?

The bundled registry can help with question 1 and can identify a newer publication for review. It cannot decide the governing edition. Questions 3 and 4 require the exact standard text or equally direct official evidence.

## Workflow

1. Run `scripts/verify_standards.py` on the manuscript to build a standards ledger.
2. Resolve every incomplete designation. Preserve distinctions such as `GB` versus `GB/T`, `JGJ` versus `JGJ/T`, and an EN base text versus a National Annex.
3. If the manuscript uses an older edition, identify the governing building code, jurisdiction, project date, test protocol, or comparison purpose before raising a defect.
4. Remain metadata-only unless the user explicitly authorizes local deterministic processing through a `--source-map`. A discoverable file is not permission to process its contents.
5. For clause-level review, supply the exact edition through a rights-attested `--source-map`. Never package that copy with this Skill.
6. Read the returned clause excerpt in context. Compare definitions, variables, units, limits, exceptions, commentary status, and referenced clauses.
7. For formulas, compare the full expression, symbol definitions, unit system, coefficients, limits, and edition-specific amendments. A matching equation number alone is insufficient.
8. For applicability, record the structural system, material, hazard, design category, analysis method, limit state, and jurisdiction. Phrase an unresolved scope question as a question for the author.

## Full-text rights gate

- `--standards-dir` may discover candidate filenames, but it never authorizes reading. The result remains `rights-attestation-required` until an explicit source-map entry is supplied.
- Every source-map entry used for full-text processing must set `processing_mode` to `local-deterministic` and `rights_attested` to `true`.
- The bundled registry marks ASCE and ACI publications as `permission-required`. Those entries also need a non-empty `permission_reference`; otherwise the verifier returns `publisher-permission-required` and does not open the file.
- A rights attestation is the user's factual record, not legal advice or automated license validation. Confirm that the stated permission covers the intended processing.
- Reports retain only the source basename, content hash after authorized reading, and short located evidence. They do not expose an absolute source path or copy the standard.

## Formal finding boundary

- Treat a missing edition or inconsistent designation as a formal reproducibility finding when it has a source anchor.
- Treat an older-than-registry publication as `needs-review`, never automatically as wrong.
- Treat a clause not found in extracted text as `unable-to-verify` until extraction quality and amendments are checked.
- Issue a Major or Blocker scope/formula finding only from the exact standard text or direct official evidence, with the cited edition and clause recorded.
- Do not infer copyrighted clause text from memory, a search snippet, or a secondary design guide.

## User-supplied source map

Use an explicit map when filenames do not identify the edition reliably:

```json
{
  "schema_version": "0.2.0",
  "sources": [
    {
      "designation": "ASCE/SEI 7-22",
      "path": "standards/ASCE_7-22.pdf",
      "processing_mode": "local-deterministic",
      "rights_attested": true,
      "permission_reference": "Publisher permission record retained by the user"
    },
    {
      "designation": "ANSI/AISC 341-22",
      "path": "standards/AISC_341-22.pdf",
      "processing_mode": "local-deterministic",
      "rights_attested": true
    }
  ]
}
```

Only entries that pass the registry policy are read locally. The verifier records a hash and does not copy or upload the files.
