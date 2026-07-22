# Personalization guide

This Skill is intentionally opinionated only where the current owner profile is
known. Personal rules should remain explicit, editable, and traceable.

## What to edit

- Edit `personal-profile.json` to change the default review mode, manuscript
  language, privacy policy, journal priority, abbreviation whitelist, and style
  preferences.
- Edit `terminology.tsv` to add a preferred expression, accepted aliases,
  forbidden expressions, or an approved abbreviation. Keep technically distinct
  concepts on separate rows and use the notes field to prevent unsafe automatic
  replacement.
- Use `severity_overrides` only for deterministic checks. Map an exact `check_id`
  to `Blocker`, `Major`, `Minor`, or `Info`, for example:

```json
{
  "severity_overrides": {
    "english-variant": "Info",
    "latex-reference-missing-label": "Major"
  }
}
```

Invalid severity names are configuration errors; they must not be silently used.

## Which settings act where

The deterministic CLI enforces the abbreviation whitelist and use threshold,
separate abstract/body definition switch, terminology table, English variant,
number-unit and percent spacing, unused label/BibTeX checks, hard-coded LaTeX
cross-reference switch, and severity overrides.

The reviewing agent uses `default_mode`, journal priority, preferred figure and
equation tokens, title-abbreviation preference, domain list, and document types
during semantic, visual, and journal-specific passes. These fields are not all
standalone regex checks because their correctness depends on article type and
context.

## Recommended customization cycle

1. Audit one manuscript without editing the source.
2. Mark each finding as accepted, rejected, or manuscript-specific.
3. Promote only recurring accepted preferences into the profile or terminology
   table.
4. Add recurring false positives to the abbreviation whitelist or a future
   suppression list with a reason.
5. Recheck journal rules before submission because author guidance changes.

## Information worth adding later

- exact target journal and article type;
- preferred US or UK spelling;
- recurring specimen and model identifiers that should not be treated as
  abbreviations;
- the author's notation conventions and approved symbol ledger;
- preferred translations and English forms for laboratory-specific terms;
- reference manager and citation style;
- thresholds for residual drift, convergence, model error, or other metrics that
  are meaningful only within a particular research program.

Do not store unpublished manuscript text, credentials, or subscription-only paper
full text in the Skill. Store rules, metadata, DOI links, and derived terminology
cards instead.
