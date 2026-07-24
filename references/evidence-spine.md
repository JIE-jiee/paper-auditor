# Evidence spine

Use the evidence spine for every `draft` or `deep` review, for multi-pass `targeted` reviews, and whenever a final report combines deterministic and semantic findings. It prevents stale outputs, unanchored findings, and unexecuted review dimensions from being presented as a clean manuscript or a finished writing-stage review.

## Outputs

`prepare` creates three private review artifacts:

- `artifact-manifest.json`: every manuscript source and declared review dependency with a SHA-256 hash;
- `evidence-ledger.json`: content-addressed manuscript spans with stable `EVD-*` IDs;
- `coverage.json`: all review passes initialized as `not_run`.

`finalize` creates the compatible public-facing projection:

- `findings.json`;
- `review-report.md`;
- `final-evidence-ledger.json`, which adds content-addressed cited-source or standard-source passages actually used by adjudicated findings.
- when claim logic provides a valid ledger-bound map, the same files also project the paper spine card, traceability rows, satisfied/unresolved functional connections, questions for the author, and dependency-ordered writing tasks;
- when the draft deterministic pass provides valid anchored `planned_items`, the same files project them as unfinished writing work rather than formal findings.

Keep the spine files in the private review directory. The default excerpt ledger contains unpublished manuscript text. `--text-mode hash-only` removes excerpts only from the base manuscript ledger; pass results, `findings.json`, `review-report.md`, and the final external-evidence ledger can still contain short quotations. Keep the original manuscript locally available for anchor validation, and do not share the review package blindly.

## 1. Prepare the spine

Run before any pass that will contribute to the final report:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep `
  --output-dir "<review-root>\spine" `
  --artifact "bibliography=<references.bib>" `
  --artifact "profile=<skill-root>\references\personal-profile.json" `
  --artifact "terminology=<skill-root>\references\terminology.tsv" `
  --artifact "quantity_profile=<skill-root>\references\quantity-profile.tsv" `
  --artifact "standards_registry=<skill-root>\references\standards-registry.json" `
  --rendered-artifact "<compiled-or-rendered.pdf>"
```

Declare every file whose change could alter a result. Supported `--artifact ROLE=PATH` roles are:

- `bibliography`, `appendix`, `figure`, `table_data`, and `supplement`;
- `profile`, `terminology`, `quantity_profile`, and `standards_registry`;
- `cited_source_map` for an explicit citation-key-to-local-file identity binding;
- lawful local `cited_source` evidence.
A `cited_source` uses its filename stem as the default citation key. If the filename differs from the key used in the manuscript, declare both the source and the existing `claim_support.py` source map:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode targeted --required-pass claim_support `
  --output-dir "<review-root>\spine" `
  --artifact "cited_source=<local-paper.txt>" `
  --artifact "cited_source_map=<source-map.json>"
```

The map itself is hashed as a manifest dependency. Each local `citation_key` binding must resolve to an exactly declared `cited_source`; one key cannot name multiple files. `finalize` always intersects this identity with the declared source path and SHA-256 before accepting a source passage.


Never pass a standard full text as a bare `standard_source` artifact. Use the same fail-closed rights gate as the standards verifier:

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep `
  --output-dir "<review-root>\spine" `
  --standards-source-map "<rights-attested-source-map.json>" `
  --standards-registry "<skill-root>\references\standards-registry.json"
```

Each source-map row must use `processing_mode: local-deterministic` and `rights_attested: true`. A registry entry marked `permission-required`, including bundled ASCE and ACI entries, also needs a non-empty `permission_reference`. The gate runs before the standard file is opened or hashed. The manifest retains authorization provenance without copying the permission text. Do not also declare the same registry with `--artifact standards_registry=...` in this command.

Do not add copyrighted or unpublished files to the Skill repository. The manifest records local paths and hashes only inside the review output.

For `targeted` mode, add one or more `--required-pass` values. Valid pass IDs are:

- `deterministic_text`;
- `language_tense`;
- `abbreviation_terminology`;
- `quantitative`;
- `claim_logic`;
- `citation_integrity`;
- `claim_support`;
- `engineering_standards`;
- `visual`.

`draft` mode requires `deterministic_text`, `language_tense`, `abbreviation_terminology`, `quantitative`, and `claim_logic`. Citation, claim-support, standards, and rendered-visual passes remain optional unless the current draft or user request needs them. A later `deep` review still requires the complete deep pass set.

`deterministic_text`, `language_tense`, `abbreviation_terminology`, and `claim_logic` always apply when their mode requires them and cannot be recorded as `not_applicable`. A genuinely empty quantitative, citation, claim-support, standards, or visual scope may use `not_applicable` only with a current, source-bound zero-item inventory and rationale.

An unwritten downstream section is represented inside the paper spine as `planned` or `not_yet_written`; it never makes the whole claim-logic pass not applicable.

Run the deterministic checker with `--manuscript-stage draft` for a writing-stage review. Its `planned_items` exception is intentionally narrow: only locally explicit, occurrence-bound future or in-progress figure/table/label targets are eligible. `record-pass` reparses each quote, requires the exact target kind and identifier at an occurrence that satisfies the same local planning rule, and rejects unknown check IDs, malformed or unanchored items, and any planned item recorded into a non-draft spine.

Planned items do not change readiness to `revision_required` or `manual_confirmation_required`. They remain visible in the final report, while a clean reviewed partial manuscript stays `draft_in_progress`.

## 2. Produce pass results

Run each existing checker in a separate directory. Do not merge its JSON manually into the final report.

Semantic pass results must bind themselves to the ledger:

```json
{
  "schema_version": "0.1.0",
  "pass_id": "claim_logic",
  "provenance": {
    "ledger_fingerprint": "<value from evidence-ledger.json>",
    "input_fingerprint": "<value from artifact-manifest.json>"
  },
  "sources": [{"source": "<manifest source>", "sha256": "<current manifest sha256>"}],
  "findings": [],
  "summary": {"review_completed": true}
}
```

Every `completed` or `not_applicable` result must carry a native non-empty string `schema_version`, a native non-empty exact `pass_id`, and a current source/provenance binding. If a semantic `completed` result has no findings, its summary must state `"review_completed": true`; an empty or explicitly false summary is not execution evidence.


For either a `draft` or `deep` claim/logic review, first create and validate the reviewer-authored map with `manuscript_map.py`. The validator output remains nested inside an independently authored semantic-review envelope:

The `claim_logic` result uses this shape. The embedded map is abbreviated below; actual node and edge reviews must match the complete validator output exactly.

```json
{
  "schema_version": "0.1.0",
  "pass_id": "claim_logic",
  "semantic_audit_status": "completed",
  "provenance": {"ledger_fingerprint": "<current>", "input_fingerprint": "<current>"},
  "sources": [{"source": "<manifest source>", "sha256": "<current manifest sha256>"}],
  "findings": [],
  "manuscript_map_validation": {
    "artifact_type": "manuscript_map_validation",
    "validation_scope": "structure_and_evidence_binding",
    "status": "valid",
    "argument_status": "unresolved",
    "contract_gaps": [],
    "provenance": {"ledger_fingerprint": "<current>", "input_fingerprint": "<current>"},
    "manuscript_map": {"nodes": [{"id": "OBJ-001"}], "edges": [{"id": "EDGE-001"}]},
    "traceability_rows": []
  },
  "semantic_review": {
    "scope": "available draft",
    "reviewed_by": "logic-reviewer-1",
    "input_fingerprint": "<current>",
    "ledger_fingerprint": "<current>",
    "node_reviews": [{"node_id": "OBJ-001", "assessment": "satisfied", "rationale": "Reviewed in context."}],
    "edge_reviews": [{"edge_id": "EDGE-001", "assessment": "not_yet_written", "rationale": "The result section is planned."}],
    "contract_gap_reviews": []
  },
  "questions_for_author": [],
  "next_writing_tasks": []
}
```

Pass the same non-empty identity through `record-pass --reviewer`; it must equal `semantic_review.reviewed_by`. The review scope and both fingerprints must be current.

`node_reviews` and `edge_reviews` must cover every embedded node and edge exactly once. Each item needs a valid `assessment` (`satisfied`, `unresolved`, `contradicted`, `not_yet_written`, or `not_applicable`) and a non-empty rationale. Each `contract_gap` must also be reviewed exactly once by index, code, and path, with a non-satisfied assessment and rationale.

The map's top-level `status` controls whether its contract and evidence binding are legal enough to enter the spine. `argument_status` and `contract_gaps` state whether the manuscript argument closes; an unresolved complete map cannot receive `ready_given_evidence`.

In `draft` and `deep` modes, `claim_logic` cannot be `not_applicable`. `record-pass` rejects a completed result without this map and semantic checklist, with a structure-only or stale map, with mismatched reviewer or fingerprints, or without exact node/edge/gap coverage. Finalization performs the same validation again. The raw structural-validator output can never be recorded as semantic review. `questions_for_author` and `next_writing_tasks` are validated work items; they are neither formal defects nor `manual_checks`.

Include the actual manifest-backed manuscript files under `sources`, even when the result also carries native ledger fingerprints. This makes the reviewed source set explicit and avoids `result_without_source_manifest` warnings.

Every formal finding must retain the existing finding schema and an exact manuscript `location` and `quote`. The adjudicator always derives minimum capabilities from the pass and check type. A producer-declared `required_capabilities` list can add requirements but cannot remove those minimums.

For a semantic Blocker or Major, also include:

```json
{
  "alternative_explanations": [
    {
      "explanation": "The difference may come from rounding.",
      "status": "ruled_out",
      "evidence_ids": ["EVD-..."]
    }
  ],
  "independent_recheck": {
    "status": "confirmed",
    "reviewer": "independent-reviewer-id",
    "rationale": "The current source and calculation reproduce the conflict.",
    "ledger_fingerprint": "<current ledger fingerprint>"
  }
}
```

Use `status: contested` when the independent reviewer finds material counterevidence. A plausible alternative also makes the finding contested. Keep the proposed severity unchanged; contested status controls readiness, not technical impact.

## 3. Record coverage

Record each pass into a new coverage file. Use the newest coverage file as the input for the next command:

```powershell
python "<skill-root>\scripts\evidence_spine.py" record-pass `
  "<previous-coverage.json>" "<evidence-ledger.json>" `
  --output "<next-coverage.json>" `
  --pass-id deterministic_text `
  --status completed `
  --result "<deterministic-review>\findings.json"
```

If an older semantic producer cannot write a native ledger fingerprint, use `--attest-ledger-read --reviewer <independent-id>` only when that reviewer actually read the stated ledger version. The result must still carry a current source/input SHA-256 that matches a declared manifest dependency.

Pass status meanings:

- `completed`: the requested review was performed; the result may still contain `unable-to-verify` items;
- `not_applicable`: a completed inventory proves the dimension does not occur; requires both `--result` and `--rationale`;
- `insufficient_evidence`: the review cannot be completed with the available evidence;
- `failed`: the pass attempted to run but failed;
- `not_run`: initial state; never treat it as no problem.

A `not_applicable` result must include a machine-verifiable empty inventory:

```json
{
  "schema_version": "0.1.0",
  "pass_id": "claim_support",
  "provenance": {"ledger_fingerprint": "<current>", "input_fingerprint": "<current>"},
  "sources": [{"source": "<manifest source>", "sha256": "<current manifest sha256>"}],
  "inventory": {
    "scope": "in-text citations in the complete manuscript",
    "item_count": 0,
    "items": []
  }
}
```

This is an internal-consistency and current-input contract, not a cryptographic signature. A trusted local operator who rewrites both a structurally valid result and its coverage record can create a new valid review state. Stronger authorship guarantees would require a versioned producer inventory contract with typed selectors and source IDs, or signed attestations.

Record newly established evidence capabilities at the same time:

```powershell
--capability "reference_metadata=available"
--capability "cited_full_text=available"
```

Capabilities are orthogonal, not a single quality score:

- `manuscript_text`;
- `editable_source`;
- `rendered_pages`;
- `reference_metadata`;
- `cited_full_text`;
- `standard_text`;
- `figure_table_data`.

Use `available`, `partial`, or `missing`. `partial` never satisfies a formal finding that requires the capability. For file-backed capabilities such as rendered pages, cited full text, standard text, and table data, the manifest is an upper bound: `--capability available` cannot create evidence that was not declared and hashed.

## 4. Finalize

After every required pass is recorded, run:

```powershell
python "<skill-root>\scripts\evidence_spine.py" finalize `
  "<artifact-manifest.json>" `
  "<evidence-ledger.json>" `
  "<latest-coverage.json>" `
  --output-dir "<new-final-review-dir>"
```

The adjudicator applies fail-closed rules:

1. Reconstruct the required pass set from the selected mode; a producer-edited `required: false` cannot turn a draft or deep review into a clean result, and an always-applicable core pass cannot be changed to `not_applicable`.
2. Recompute all declared input hashes and the root-manuscript binding. A changed, substituted, or missing input makes the report `stale`.
3. Reload every actual producer-result JSON and rederive its pass identity, source/provenance binding, execution evidence, schema, counts, warnings, and inventory. Compare cached coverage metadata with that reconstruction instead of trusting it; reject any empty, changed, mislabelled, category-incompatible, stale, or differently bound result.
4. Reparse every draft planned item's exact callout or LaTeX reference and its local future/in-progress wording, then bind the quote to current ledger evidence.
5. Require every formal finding's quote and location to resolve to current ledger evidence, including every `related_locations` anchor; producer-supplied evidence IDs must fall inside those locator windows.
6. Move insufficiently supported proposals to `manual_checks`; preserve their proposed impact severity and cap adjudicated confidence below `0.60`.
7. Bind cited passages to a specific citation source and validate their real line/page locator; bind every non-metadata standard finding to exact authorized standard text; require rendered pages for visual findings.
8. Require structured alternatives and a genuinely independent current-ledger recheck for semantic Blocker/Major findings.
9. Preserve `unable_to_verify`, unresolved standard tasks, and quantitative review candidates in `manual_checks` instead of silently dropping them.
10. Revalidate every embedded manuscript map and its named semantic-review checklist against the current ledger; project author questions and writing tasks without promoting them to findings.
11. Never return `ready_given_evidence` for a complete map whose `argument_status` is unresolved; accepted formal defects produce `revision_required`, otherwise the unresolved argument requires manual confirmation.
12. Report `incomplete` whenever a required pass is `not_run`, `failed`, `insufficient_evidence`, missing, or stale.
13. Refuse every output or temporary-output path that aliases the manuscript, a declared dependency, an input ledger/coverage/manifest, or a pass result—even when `--force` is used.
Report-level statuses are author-side workflow states:

- `review_status`: `complete`, `incomplete`, or `stale`;
- `submission_readiness`: `ready_given_evidence`, `revision_required`, `manual_confirmation_required`, or draft-only `draft_in_progress`.

`draft_in_progress` means the required review of the current partial draft completed without an accepted defect or unresolved manual check. It never asserts that the manuscript is complete or ready to submit.

Never translate these into an authorship, fraud, or misconduct judgment.
