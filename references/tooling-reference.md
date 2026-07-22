# Open-source design references

Checked on 2026-07-22. These projects informed the architecture; none is bundled
or required at runtime in version 0.1.

- [Vale](https://github.com/vale-cli/vale): markup-aware, configurable prose
  linting. Adopted idea: separate deterministic, user-configurable style rules
  from semantic editorial judgment and emit structured findings.
- [LTeX+](https://github.com/ltex-plus/ltex-ls-plus): grammar and spelling checks
  for LaTeX, Markdown, and related formats. Adopted idea: ignore markup and
  mathematical syntax before applying prose rules.
- [TeXtidote](https://github.com/sylvainhalle/textidote): LaTeX-oriented spelling,
  grammar, and style checking. Adopted idea: preserve source locations so every
  report item can be reproduced in the editable manuscript.
- [Citation.js](https://github.com/citation-js/citation-js): multi-format citation
  parsing and DOI-oriented bibliographic workflows. Adopted idea: keep parsing,
  metadata resolution, and citation formatting as separate concerns.

The personal Skill adds manuscript-wide claim consistency, domain terminology,
privacy defaults, and evidence grading. Open-source projects remain optional
future integrations rather than hidden dependencies.
