# Review rubric

## Severity

- **Blocker**: A high-confidence issue that can invalidate a central result, misidentify a source, reverse a quantitative conclusion, or create a serious submission-integrity problem.
- **Major**: An issue that materially affects technical interpretation, reproducibility, argument validity, or the connection between evidence and conclusions.
- **Minor**: A localized language, terminology, abbreviation, cross-reference, or presentation defect with a clear correction.
- **Info**: A preference, optimization, or low-evidence concern that deserves author review but is not established as an error.

Do not raise severity merely because a finding sounds important. Combine severity with a separate confidence value.

## Confidence and evidence

- `0.95-1.00`: directly reproducible from source, compilation, deterministic rule, or authoritative identifier record.
- `0.80-0.94`: strong contextual evidence with one plausible alternative.
- `0.60-0.79`: meaningful concern requiring author confirmation.
- `<0.60`: do not list as a formal defect; ask a question or omit it.

Evidence classes:

- **A**: manuscript source, rendered artifact, user profile, or deterministic output;
- **B**: publisher, DOI registration agency, standard, or cited full text;
- **C**: abstract or secondary scholarly index;
- **D**: model inference only.

Blocker and Major semantic findings require independent rechecking and at least one A or B source.

## Tense policy

Treat tense as discourse-dependent:

- use present tense for established knowledge, paper organization, mathematical relationships, and what a displayed figure or table shows;
- use past tense for actions completed in the reported study and specific observed test events;
- use present perfect for a research trend extending to the present when appropriate;
- allow results and discussion to alternate between past observations and present interpretation;
- flag unexplained switching within the same rhetorical function, not every mixed tense.

Do not rewrite all Methods or Results sentences to one tense without checking meaning.

## Consistency policy

Build ledgers for abbreviations, terminology, symbols, units, specimens, load cases, numerical results, figures/tables, and central claims. Treat different terms as an error only if the document intends the same referent. Preserve meaningful distinctions such as capacity versus demand, displacement versus drift ratio, residual deformation versus residual drift, and recentering force versus restoring force.

## Logic and claims

For each central claim, identify the manuscript location, scope, supporting method/result, assumptions, and limitations. Check both directions:

- every major conclusion should have a traceable result;
- every emphasized result should be interpreted consistently in the abstract/discussion/conclusion.

Flag unsupported causal language, silent population or hazard generalization, comparison across non-equivalent baselines, circular novelty arguments, and conclusions that exceed tested parameters. Phrase debatable matters as questions.

## Report schema

Each `findings.json` item must contain:

```json
{
  "id": "ABBR-001",
  "check_id": "abbreviation-first-use",
  "severity": "Minor",
  "confidence": 0.98,
  "status": "confirmed",
  "location": {"source": "paper.tex", "line": 42, "section": "Introduction"},
  "quote": "...",
  "observation": "...",
  "expected": "...",
  "reason": "...",
  "evidence": [{"class": "A", "source": "manuscript"}],
  "suggested_fix": "...",
  "auto_fixable": false
}
```

Keep quotations short. Never invent a page, line, paragraph, DOI, or source.
