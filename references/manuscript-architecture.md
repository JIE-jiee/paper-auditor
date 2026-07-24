# Manuscript architecture and drafting

Use this reference when the user wants help while writing, asks for a section-level review, or needs the manuscript's argument traced across sections. Treat it as an engineering manuscript architecture check, not as a universal IMRAD template.

## Choose the manuscript state

- **Draft mode (`draft`)**: review only the material that exists, maintain the intended argument, and identify the next evidence or writing task. A section that has not yet been written is `not_yet_written`, not defective.
- **Review mode**: audit the submitted scope as a manuscript that is intended to be complete. A missing or contradictory link may become a formal finding when the relevant source locations and evidence meet `review-rubric.md`.
- For a section-only draft, inspect its local contract and all available upstream links. Do not claim whole-manuscript consistency until the full manuscript has been read.

Record the manuscript state, target journal, article type, available sections, and whether Results and Discussion are separate, combined, or distributed across engineering case-study chapters. Current journal guidance and explicit user instructions take precedence.

## Build the manuscript spine card

Create one compact **manuscript spine card** before judging architecture. Preserve the author's intended central message separately from what the current text actually supports.

| Field | Record |
|---|---|
| Research problem | The engineering decision, uncertainty, or phenomenon being addressed |
| Knowledge gap | What remains unknown, insufficiently tested, inconsistent, or unusable, and for which system and conditions |
| Research question, objective, or hypothesis | What the study asks, promises to determine, develop, compare, or validate, or explicitly predicts |
| Scope envelope | Structural system, material, specimens or data, loading or hazard, parameter range, analysis level, statistic, baseline, and important exclusions |
| Method blocks | Experiments, models, simulations, datasets, comparisons, calibration, validation, and uncertainty treatment |
| Principal evidence | Results, equations, tables, figures, and reproducible calculations that answer the objective |
| Interpretations | What the results mean, including alternative explanations and limitations |
| Conclusions | The bounded claims that remain after applying the scope and limitations |
| Target reader | The knowledge the intended engineering reader may reasonably be assumed to have |

Use `unknown` when the manuscript does not establish a field. In draft mode, convert important unknowns into questions or next-writing tasks; do not fill them from model inference.

## Use functional nodes, not heading names

Assign stable local IDs to the manuscript's rhetorical functions:

- `GAP-*`: a bounded knowledge or practice gap;
- `RQ-*`, `OBJ-*`, or `HYP-*`: a research question, objective, or hypothesis used as the declared study entry;
- `MTH-*`: a method capable of addressing an objective;
- `RES-*`: an observed or calculated result;
- `VIS-*`: a human-facing ID prefix for a figure, table, equation, or other displayed evidence. JSON maps use `role: figure_table`; `role: visual` is accepted as a validation alias and treated as `figure_table` without rewriting the submitted map. Do not confuse this node role with the `visual` review pass or the `figure_table_data` evidence capability;
- `INT-*`: an interpretation of one or more results;
- `CON-*`: a conclusion or recommendation.

Trace the principal chain in both directions:

```text
GAP → (RQ | OBJ | HYP) → MTH → RES ↔ VIS → INT → CON
```

`VIS` is optional when the evidence is adequately reported in anchored prose or an equation. A paper may have several connected chains. Require a shared central problem or explainable relationship between them; do not force unrelated objectives into one artificial claim.

For every node record its normalized statement, manuscript anchor, scope qualifiers, incoming and outgoing links. In the machine-readable map, node status is `planned`, `not_yet_written`, `drafted`, `verified`, `needs_review`, or `not_applicable`; edge status is `planned`, `not_yet_written`, `mapped`, `verified`, `needs_review`, or `not_applicable`. A visual that supports a result is encoded as `figure_table --evidences--> result`; the human-facing `RES ↔ VIS` notation means the result-to-visual relationship must be traceable in both reading directions, not that both graph directions are required.

The validator separates contract legality from argument closure. Top-level `status: valid` means the map schema, identifiers, relations, evidence references, and ledger binding are legal enough to enter the review. `argument_status: closed` is stricter: in a complete manuscript every core node and edge is `verified`, carries current evidence IDs, and forms the role-specific chain. Missing links, unfinished states, or absent evidence appear under `contract_gaps` and produce `argument_status: unresolved` while the map can remain structurally `valid`; edges that point to nonexistent nodes, illegal relations, unknown evidence IDs, and stale ledgers still make it `invalid`.

Each declared research question, objective, or hypothesis needs its own gap and method connection; each outcome-producing method, emphasized result, interpretation, and conclusion needs its role-specific counterpart. `drafted`, `mapped`, or `needs_review` remains useful in `draft` mode but cannot close a complete argument.

These statuses describe writing and evidence-binding progress, not whether a scientific claim is true. Put the semantic relationship in the reviewer-authored edge rationale and any evidence-backed finding. A link is semantic, not merely two sections using similar words.

Check forward and reverse traceability:

- every central gap leads to a declared research question, objective, or hypothesis;
- every declared research question, objective, or hypothesis has a method that can answer or test it;
- every outcome-producing method has a reported result, or an explicit reason why no result is expected;
- every emphasized result has a declared method, metric, condition, and baseline where comparison is claimed;
- every material interpretation identifies the result it interprets;
- every major conclusion traces back to evidence and remains inside the scope envelope;
- every emphasized result is handled consistently in the abstract, discussion, and conclusion when those functions are present.

Treat setup, instrumentation, data cleaning, convergence checks, and quality-control procedures as **enabling methods**. By default, record them as support, qualifiers, or evidence inside the outcome-producing `MTH-*` node rather than as separate core method nodes. Give one its own `MTH-*` node only when it produces a separately reviewed outcome; enabling procedures still need enough reported evidence to establish validity, but they do not automatically require a standalone headline result.

## Apply functional section contracts

These contracts describe what a passage does. They do not require fixed headings, paragraph counts, sentence counts, or writing order.

| Function | Contract |
|---|---|
| Title | Identify the actual subject and defensible scope. A directional or performance claim in the title must be supported by the manuscript. Do not require every title to state a result. |
| Abstract | Faithfully compress the objective, central method, principal result, essential comparison conditions, and bounded conclusion. It may omit detail but must not introduce a new result, population, baseline, level of certainty, or scope. |
| Introduction | Establish relevant context, a bounded gap, and the objective or hypothesis. Their order may vary, but the connection must be intelligible and supported where external knowledge is invoked. |
| Methods | Define the design, entities, conditions, metrics, baselines, calculations, validation, and assumptions needed to understand and reproduce the claimed evidence. |
| Results | Report observations and calculations with their entities, conditions, units, statistics, and uncertainty where relevant. Interpretation may coexist when the journal or article structure combines Results and Discussion. |
| Discussion | Explain what the results support, compare like with like, consider plausible alternatives, state limitations, and bound generalization. It must not depend on unreported study evidence. |
| Conclusion | Answer the objective using results already established, preserve material limitations, and distinguish demonstrated findings from recommendations or future work. |
| Figures and tables | Present interpretable evidence with enough identity, conditions, notation, units, statistical meaning, and panel or legend information that a disciplinary reader need not guess what is being compared. |

Custom engineering sections such as model formulation, experimental program, parametric study, validation, design implications, and case studies may satisfy several contracts. Map passages to functions before reporting a missing conventional section.

## Check abstract–body parity

Map each material abstract statement to body evidence:

- objective and studied system;
- method or data basis;
- principal qualitative and quantitative results;
- comparison baseline, loading or hazard level, parameter range, and statistic;
- limitations that materially change interpretation;
- conclusion strength and applicability.

Exact wording and order need not match. A compressed abstract may omit secondary methods and results. Raise a cross-location conflict only when both statements refer to the same metric, entity, condition, statistic, baseline, and compatible unit. Apply the quantitative identity rules in `domain-style.md`.

An abstract-only number or claim is not automatically false. If no body anchor can be found in a manuscript intended to be complete, record the search scope and treat the missing support according to the evidence threshold below.

## Check Methods–Results in both directions

Create a row for each outcome-producing method and each emphasized result:

| Method or result ID | Entity and condition | Metric or outcome | Expected counterpart | Located counterpart | Status |
|---|---|---|---|---|---|

Check that:

- the method can produce the reported metric under the stated conditions;
- specimen, model, dataset, load case, baseline, sample size, and statistic agree;
- calibration and validation evidence are not silently exchanged;
- a parametric, sensitivity, uncertainty, or robustness method has a corresponding outcome when it supports a claim;
- an emphasized result does not rely on an undeclared analysis, exclusion rule, or post hoc metric.

Do not require Results to follow Methods in the same order. Do not require a separate result for routine software, formatting, or enabling procedures.

## Check figures and tables as evidence

A figure or table is evidence-self-contained when a disciplinary reader can identify, without guessing:

- the entity, case, specimen, model, or dataset;
- axes, variables, symbols, units, normalization, and sign convention;
- panels, legends, line or marker encodings, and comparison baseline;
- load, hazard, boundary, or analysis condition needed to interpret the comparison;
- whether values are mean, median, percentile, envelope, maximum, a single response, or another statistic;
- uncertainty indicators and sample size when they are material to the claim.

Then verify that the visual supports the direction, magnitude, ranking, failure mode, or comparison stated in the text. Use rendered pages for visual findings and table or figure data for exact numeric claims when available. Do not infer unreadable values or require captions to repeat the entire Methods section.

Duplication between prose and a visual is not automatically an error. Report it only when it creates a conflict, hides the central evidence, or violates explicit journal guidance.

## Bound interpretation, conclusion, and title claims

Carry the scope envelope through every `INT-*` and `CON-*` node. Check for:

- causal language unsupported by the study design;
- generalization beyond tested structural systems, materials, geometries, records, hazards, parameters, or jurisdictions;
- a comparison whose baseline, statistic, or loading condition changes;
- limitations acknowledged earlier but omitted when the claim is restated;
- recommendations presented as demonstrated performance;
- new substantive study evidence introduced only in the discussion or conclusion;
- title terms such as `superior`, `damage-free`, `resilient`, `validated`, or directional performance claims that exceed the traced evidence.

Synthesis in the discussion or conclusion is allowed; exact repetition of Results is not required. A citation or technical qualification in a conclusion is not prohibited unless the target journal says so.

## Separate findings from questions

Use the severity, confidence, evidence classes, and finding schema in `review-rubric.md`. Architecture findings additionally require:

- a reproducible anchor for every affected node;
- related anchors for each claimed broken or contradictory link;
- the exact identity dimensions used to decide that two statements should match;
- a short explanation of the missing, contradictory, or overextended link;
- current evidence IDs when the evidence spine is active.

Use a **formal finding** only when the relevant manuscript scope is available and one of these is established:

- two traceable nodes materially contradict each other;
- a central claim lacks an upstream method or result after a documented complete-scope search;
- an abstract, title, discussion, or conclusion claim materially exceeds its traced evidence;
- a visual or result cannot support the stated comparison under the declared conditions.

Blocker and Major semantic findings require an independent recheck and structured alternative explanations under `evidence-spine.md`. Absence of a conventional heading, preference for another paragraph order, or a model-only judgment about what the author intended is not a formal defect.

Use these stable `check_id` values when the corresponding relationship is established:

- `title-body-scope-mismatch`;
- `abstract-body-untraceable-claim`;
- `objective-method-gap`;
- `method-result-gap`;
- `result-method-gap`;
- `conclusion-result-gap`;
- `discussion-new-evidence`;
- `visual-not-self-contained`.


Use **questions for the author** when:

- the manuscript is partial or the downstream section is `not_yet_written`;
- the intended objective, scope, baseline, or relationship between chains is ambiguous;
- a plausible engineering explanation cannot be ruled out from available evidence;
- the concern depends on unavailable data, a future section, or author intent;
- the proposed change is a writing strategy or reader preference rather than an established error.

Each question should identify the affected node or link, explain why the answer matters, and request the specific evidence or decision needed. Do not assign defect severity to a question.

## Keep the rules engineering- and journal-aware

- Accept separate Results and Discussion, combined Results and Discussion, and custom engineering section structures.
- Apply tense by rhetorical function using `review-rubric.md`; do not assign one tense to an entire section.
- Standards, software documentation, datasets, manufacturer specifications, technical reports, and authoritative web sources may be legitimate engineering evidence. Judge authority, provenance, edition, and applicability instead of banning a source type.
- Product, instrument, material, and software names may be necessary for reproducibility. Require adequate identity when material; do not prohibit commercial names mechanically.
- Do not import patient, clinical endpoint, consent, or medical reporting requirements unless the actual study type makes them relevant.
- Do not enforce IMRAD headings, a fixed writing sequence, title length, paragraph counts, active voice, a ban on interpretation in Results, or a ban on citations in the abstract or conclusion as universal rules.
- Treat writing guides as heuristics. Treat explicit target-journal requirements, engineering standards, and direct manuscript evidence as the controlling sources.

## Draft-mode output

For writing-stage help, return:

1. the current manuscript spine card;
2. the traceability matrix with `not_yet_written` distinguished from `missing`;
3. satisfied and unresolved functional contracts;
4. formal findings supported by existing text;
5. source-anchored deterministic `draft_planned_items`, projected from producer `planned_items` only after final validation;
6. questions for the author;
7. reviewer-authored, dependency-ordered `next_writing_tasks`, kept separate from deterministic planned items.

Do not present a partial draft as submission-ready, and do not turn every unresolved planning choice into an error.
