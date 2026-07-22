# Journal benchmarks for structural and earthquake engineering

Checked on: **2026-07-22**

This reference calibrates reviews for *Earthquake Engineering & Structural Dynamics* (EESD), *Engineering Structures*, and the ASCE *Journal of Structural Engineering* (JSE), with emphasis on earthquake resilience, self-centering, and rocking systems. It is not a substitute for the submission portal or the latest author instructions.

## Evidence levels and conflict handling

Apply a rule only at the level supported by its source. Record the level, source URL, and verification date in any journal-style finding.

| Level | Meaning | How the Skill may use it |
| --- | --- | --- |
| `venue-explicit` | A current instruction published for the named journal, article type, or submission portal. | Treat a clear, non-conflicting requirement as a journal compliance rule. Recheck the live page before submission. |
| `publisher-general` | A publisher-wide manual or preparation guide that is not unique to the named journal. | Apply only when the venue-specific instructions are silent, and never let it override a venue-specific rule. |
| `corpus-derived` | A writing, terminology, or argument pattern inferred from the representative papers below. | Use to calibrate questions and suggestions. Do not report it as a mandatory journal rule. |
| `personal-preference` | The user's profile, terminology table, and preferred house style. | Use as the default editing preference after higher-level requirements. Report conflicts as consistency or preference issues, not universal errors. |

The priority order is: an explicit instruction from the user for the current manuscript, current `venue-explicit` guidance, applicable `publisher-general` guidance, `corpus-derived` calibration, then `personal-preference`. If two current venue instructions conflict, do not silently choose one. State the conflict, prefer the option that satisfies both where possible, and mark any unresolved point `needs-review`.

## Limits, selection basis, and copyright

- The papers below are a **human-curated calibration set**, not an official citation ranking, exhaustive literature review, or claim that these are the objectively “best” papers.
- Selection balances foundational concepts, experimental or analytical rigor, system-level performance, nonstructural consequences, and recent methodological development in the user's subject area.
- A published paper is an example of scholarly practice, **not a normative style specification**. Its spelling, terminology, structure, or claim strength does not override current author instructions.
- Preserve article titles and reference metadata exactly when auditing a bibliography. Do not “correct” a cited title to match the manuscript's house style.
- Do not package, redistribute, or embed copyrighted full texts in this Skill. Store only bibliographic metadata, short analytical notes, and links. Obtain and read full text through lawful institutional, publisher, author, or open-access routes when claim-level verification is needed.

## Earthquake Engineering & Structural Dynamics (EESD)

### Official sources

- Journal page: [EESD, Wiley Online Library](https://onlinelibrary.wiley.com/journal/10969845) — checked 2026-07-22.
- Journal-specific author instructions: [EESD Author Guidelines](https://onlinelibrary.wiley.com/page/journal/10969845/homepage/forauthors.html) — checked 2026-07-22.
- Topic relevance, not a style rule: [Call for Papers: Self-Centering and Rocking Structures](https://onlinelibrary.wiley.com/page/journal/10969845/call-for-papers/si-2025-000526) — checked 2026-07-22.
- Publisher-wide fallback: [Wiley Journals Style Manual](https://authorservices.wiley.com/asset/Wiley-Journals-Style-Manual.pdf) — checked 2026-07-22; classify as `publisher-general`.

### Venue-explicit checks

The current EESD author page supports the following checks:

- The title should be short and informative and should not contain abbreviations.
- A separate novelty file is required and must describe the new contributions in a bulleted list of fewer than 100 words.
- A co-author consent file is required; a sole author supplies an acknowledgement of that requirement.
- The main file may be Word or LaTeX. A LaTeX submission also requires a compiled PDF for peer review and all supporting source files must be uploaded with the indicated designations.
- The main document should include authors and affiliations, acknowledgements, an abstract, keywords, the main body, references, titled/footnoted tables, and figures with legends. Figure legends are required beneath each uploaded image and as a complete list in the text.
- The author page states an abstract limit of 250 words in its manuscript-style section and expects a data availability statement.
- References are numbered in order of appearance and in-text citations use consecutive Arabic superscript numerals under the current page. Confirm this again against the submission template before final formatting.

#### Known EESD keyword contradiction

The same live author page contained two incompatible limits on 2026-07-22:

- the “Your main document file should include” checklist says **up to seven keywords**;
- the later “Manuscript Style” section says **up to six keywords**.

The Skill must handle this conservatively:

- zero to six keywords: compatible with both displayed limits;
- exactly seven: do **not** issue a confirmed defect; report `needs-review` and ask the author to confirm the submission portal or editorial office;
- more than seven: report a confirmed count issue against both displayed limits;
- never present either six or seven as an undisputed universal EESD limit without noting the checked date and page conflict.

### Corpus-derived calibration

Across the curated EESD papers, strong argumentation commonly separates the physical mechanism, model assumptions, experimental or numerical protocol, response metrics, and limits of inference. For this topic, the Skill should look for a traceable chain from restoring force and energy dissipation to uplift/gap opening, higher-mode response, residual drift, component damage, and repairability. That chain is a review aid, not a prescribed section structure.

### Representative papers (5)

#### 1. Marriott, Pampanin, and Palermo (2009)

- **Authors:** Dion Marriott; Stefano Pampanin; Alessandro Palermo.
- **Title:** “Quasi-static and pseudo-dynamic testing of unbonded post-tensioned rocking bridge piers with external replaceable dissipaters.”
- **DOI:** [10.1002/eqe.857](https://doi.org/10.1002/eqe.857)
- **Why selected:** A foundational bridge-scale example that combines quasi-static and pseudo-dynamic evidence, an unbonded post-tensioned restoring mechanism, external replaceable dissipaters, and comparison with a monolithic benchmark.
- **Terminology and argument pattern to learn:** Define `rocking`, `post-tensioned`, `dissipater`, `re-centring`, and `residual deformation` through mechanics and measured response. State specimen scale, loading protocol, comparison baseline, damage observations, and replacement scope before making downtime or resilience claims.

#### 2. Wiebe, Christopoulos, Tremblay, and Leclerc (2013)

- **Authors:** Lydell Wiebe; Constantin Christopoulos; Robert Tremblay; Martin Leclerc.
- **Title:** “Mechanisms to limit higher mode effects in a controlled rocking steel frame. 1: Concept, modelling, and low-amplitude shake table testing.”
- **DOI:** [10.1002/eqe.2259](https://doi.org/10.1002/eqe.2259)
- **Why selected:** It makes a difficult system-level issue—higher-mode amplification—explicit and links a mitigation concept to modelling and physical testing.
- **Terminology and argument pattern to learn:** Distinguish first-mode rocking response from higher-mode member-force and acceleration effects. Present the sequence `observed problem → proposed mechanism → model prediction → bounded test evidence`; do not generalize low-amplitude tests to collapse performance.

#### 3. Eatherton and Hajjar (2014)

- **Authors:** Matthew R. Eatherton; Jerome F. Hajjar.
- **Title:** “Hybrid simulation testing of a self-centering rocking steel braced frame system.”
- **DOI:** [10.1002/eqe.2419](https://doi.org/10.1002/eqe.2419)
- **Why selected:** A clear hybrid-simulation example that couples a physical rocking frame with computational substructures and examines self-centering, fuse behavior, and residual drift under strong excitation.
- **Terminology and argument pattern to learn:** Identify which response is physical and which is simulated, define interface variables and boundary conditions, and trace inelasticity to replaceable fuses. Strong phrases such as `virtually no residual drift` must retain the tested ground motions, model scope, and measurement threshold.

#### 4. Buccella, Wiebe, Konstantinidis, and Steele (2021)

- **Authors:** Nathan Buccella; Lydell Wiebe; Dimitrios Konstantinidis; Taylor Steele.
- **Title:** “Demands on nonstructural components in buildings with controlled rocking braced frames.”
- **DOI:** [10.1002/eqe.3385](https://doi.org/10.1002/eqe.3385)
- **Why selected:** It tests whether desirable structural behavior transfers to nonstructural performance and exposes a consequential trade-off: elastic primary members can coexist with larger nonstructural demands.
- **Terminology and argument pattern to learn:** Keep `structural damage`, `nonstructural demand`, `floor acceleration`, `sliding`, `rocking`, and `higher-mode response` distinct. Name the reference system and use cascading-analysis inputs and component categories before drawing whole-building resilience conclusions.

#### 5. Vlachakis, Colombo, Giouvanidis, and Lourenço (2026)

- **Authors:** Georgios Vlachakis; Carla Colombo; Anastasios I. Giouvanidis; Paulo B. Lourenço.
- **Title:** “Generalised Kinematic Single-Impact and Multi-Impact Models for Rocking Structures.”
- **DOI:** [10.1002/eqe.70130](https://doi.org/10.1002/eqe.70130)
- **Why selected:** A recent mechanics-focused treatment of single and consecutive impacts, energy loss, coefficient of restitution, and calibration/validation against an extensive free-rocking test program.
- **Terminology and argument pattern to learn:** Distinguish smooth rocking motion from impact events, kinematic from energetic coefficients of restitution, and calibration from validation. State no-sliding, contact, rigidity, and energy-consistency assumptions before comparing predictive performance.

## Engineering Structures

### Official sources

- Journal page: [Engineering Structures, ScienceDirect](https://www.sciencedirect.com/journal/engineering-structures) — checked 2026-07-22.
- Journal-specific preparation page: [Guide for Authors](https://www.sciencedirect.com/journal/engineering-structures/publish/guide-for-authors) — checked 2026-07-22.
- Publisher-wide fallback: [Elsevier Researcher Academy: preparing your paper](https://researcheracademy.elsevier.com/writing-research/preparing-manuscript) — checked 2026-07-22; classify as `publisher-general` and use only when the journal guide is silent.

### Venue-explicit checks

The current Engineering Structures guide supports the following deterministic checks:

- Every reference cited in the text must appear in the reference list, and every reference-list entry must be cited in the text.
- Each figure must have a caption consisting of a brief title and a description. Figure and table callouts must agree with their numbered objects and appear in a readable sequence.
- Appendices use separate numbering, including forms such as `Eq. (A.1)`, `Table A.1`, and `Fig. A.1`; do not merge appendix labels into the main sequence.
- Keywords are supplied in English. Recheck the live article-type instructions for current number and formatting requirements instead of inferring them from a published paper.

Treat general Elsevier conventions on units, artwork, file formats, and declarations as `publisher-general` unless the Engineering Structures guide states the same requirement directly. Submission-system instructions and article-type requirements may change independently of the visible article corpus.

### Corpus-derived calibration

The selected papers span macroelement mechanics, parametric performance comparison, preliminary system development, bridge-pier experiments, and full-scale connection tests. Use them to expect a disciplined progression from system definition and mechanics to variables, validation, response measures, and limitations. Do not demand a single vocabulary or experimental format across all five study types.

### Representative papers (5)

#### 1. Roh and Reinhorn (2009)

- **Authors:** Hwasung Roh; Andrei M. Reinhorn.
- **Title:** “Analytical modeling of rocking elements.”
- **DOI:** [10.1016/j.engstruct.2009.01.014](https://doi.org/10.1016/j.engstruct.2009.01.014)
- **Why selected:** A foundational macro-modeling paper for contact-controlled rocking elements that addresses stiffness and strength changes before full rocking and compares formulations with finite-element results.
- **Terminology and argument pattern to learn:** Separate decompression, partial contact, rocking initiation, and overturning. Explain how contact stress, cracking, yielding, crushing, confinement, and prestressing affect stiffness and lateral resistance before claiming computational efficiency.

#### 2. Karavasilis and Seo (2011)

- **Authors:** Theodore L. Karavasilis; Choung-Yeol Seo.
- **Title:** “Seismic structural and non-structural performance evaluation of highly damped self-centering and conventional systems.”
- **DOI:** [10.1016/j.engstruct.2011.04.001](https://doi.org/10.1016/j.engstruct.2011.04.001)
- **Why selected:** It directly compares structural and nonstructural consequences of self-centering and conventional hysteretic systems with supplemental viscous damping.
- **Terminology and argument pattern to learn:** Define flag-shaped and bilinear elastoplastic models, damping and strength ratios, and statistical summaries. Keep peak displacement, residual displacement, and total acceleration as distinct performance measures rather than collapsing them into a single “better performance” claim.

#### 3. Blebo and Roke (2015)

- **Authors:** Felix C. Blebo; David A. Roke.
- **Title:** “Seismic-resistant self-centering rocking core system.”
- **DOI:** [10.1016/j.engstruct.2015.07.016](https://doi.org/10.1016/j.engstruct.2015.07.016)
- **Why selected:** A concise system-development paper linking geometry, vertical post-tensioning, friction bearings, preliminary design, pushover analysis, and nonlinear dynamic response.
- **Terminology and argument pattern to learn:** Define `self-centering rocking core` as a specific configuration, not a synonym for all controlled-rocking frames. Preserve the authors' bounded language—such as `preliminary` and `expected behavior`—when the evidence is numerical and prototype-specific.

#### 4. Han, Jia, Xu, Zhou, and Du (2019)

- **Authors:** Qiang Han; Zhenlei Jia; Kun Xu; Yulong Zhou; Xiuli Du.
- **Title:** “Hysteretic behavior investigation of self-centering double-column rocking piers for seismic resilience.”
- **DOI:** [10.1016/j.engstruct.2019.03.024](https://doi.org/10.1016/j.engstruct.2019.03.024)
- **Why selected:** It links a practical bridge-bent configuration to scaled cyclic tests, multiple replaceable dissipater types, and an improved force-displacement model that accounts for compression-zone depth.
- **Terminology and argument pattern to learn:** Report specimen scale, tendon state, dissipater type, loading protocol, neutral-axis or compression-depth assumption, physical damage, residual response, and analytical–experimental agreement. Do not equate replaceability of one device with verified rapid recovery of the whole bridge.

#### 5. Zhang, Wu, Zhang, and Liu (2025)

- **Authors:** Feng-Liang Zhang; Bian Wu; Min Zhang; Yang Liu.
- **Title:** “Experimental study of friction damping connections for prefabricated self-centering rocking structural elements.”
- **DOI:** [10.1016/j.engstruct.2024.119357](https://doi.org/10.1016/j.engstruct.2024.119357)
- **Why selected:** A recent full-scale connection and subassembly study that reports friction behavior, flag-shaped response, and a design-relevant initial damping moment ratio.
- **Terminology and argument pattern to learn:** Distinguish static and kinetic friction coefficients, surface pressure, loading frequency, connection force, initial damping moment ratio, energy dissipation, and self-centering capability. Keep recommended parameter ranges tied to the tested interface, subassembly, and protocol.

## ASCE Journal of Structural Engineering (JSE)

### Official sources

- Journal and current preparation guidance: [ASCE Preparing Your Manuscript](https://ascelibrary.org/author-center/preparing-manuscript) — checked 2026-07-22.
- Journal collection used as a selection signal: [JSE Editor's Choice Collection](https://ascelibrary.org/jsendh/st_editors_choice_collection) — checked 2026-07-22.
- Journal award record used as a selection signal: [JSE Best Paper Awards](https://ascelibrary.org/jsendh/best_paper_awards) — checked 2026-07-22.
- Publisher-wide fallback: other ASCE Author Center and style resources are `publisher-general` unless the JSE preparation page or active template makes them journal-specific.

### Venue-explicit checks

The current ASCE preparation guidance supports the following checks for JSE manuscripts, subject to article-type exceptions shown in the live portal:

- Use author–date in-text citations and arrange the reference list alphabetically. Every in-text citation must have a matching reference, and every reference-list entry must be cited.
- Cite figures in numerical sequence. Figure captions begin with a form such as `Fig. 1.` and remain concise; table, equation, and appendix references must agree with their objects.
- Use SI units as the primary system and keep spacing, capitalization, symbol definitions, and notation consistent. A journal-approved dual-unit presentation is an exception, not a reason to mix systems silently.
- Main section headings are normally unnumbered word headings under the current ASCE style. Do not flag numbering inside an imported standard, equation sequence, or author-supplied outline without checking the template.
- The abstract limit is 300 words under the current general preparation guidance.
- Where the article type requires or accepts a Practical Applications section, target 150–200 words, write for practitioners, and avoid unexplained jargon and abbreviations.
- Include the required Data Availability Statement, even when the appropriate statement is that data cannot be shared or are not available.

Before issuing a compliance finding, distinguish the current JSE template from older published layout and from other ASCE journals. Historical articles below are evidence of scholarship, not proof of the 2026 production style.

### Corpus-derived calibration

The curated JSE sequence moves from posttensioned steel connections and self-centering walls to controlled-rocking system design, higher-mode capacity design, and accessible masonry-wall energy dissipation. Use it to test whether a manuscript connects component mechanics to system objectives, protects nominally elastic members through an explicit capacity hierarchy, and demonstrates rather than merely asserts replaceability or repairability.

### Representative papers (6)

#### 1. Ricles, Sause, Garlock, and Zhao (2001)

- **Authors:** James M. Ricles; Richard Sause; Maria M. Garlock; Chen Zhao.
- **Title:** “Posttensioned Seismic-Resistant Connections for Steel Frames.”
- **DOI:** [10.1061/(ASCE)0733-9445(2001)127:2(113)](https://doi.org/10.1061/%28ASCE%290733-9445%282001%29127:2%28113%29)
- **Why selected:** A foundational steel-frame connection paper that frames posttensioning as a restoring mechanism and develops the connection-level basis for later self-centering systems.
- **Terminology and argument pattern to learn:** Identify tendon force, gap opening, connection moment, decompression, energy dissipation, and residual response separately. Link analytical idealization to connection behavior before extending conclusions to a complete frame.

#### 2. Christopoulos, Filiatrault, Uang, and Folz (2002)

- **Authors:** Constantin Christopoulos; André Filiatrault; Chia-Ming Uang; Bryan Folz.
- **Title:** “Posttensioned Energy Dissipating Connections for Moment-Resisting Steel Frames.”
- **DOI:** [10.1061/(ASCE)0733-9445(2002)128:9(1111)](https://doi.org/10.1061/%28ASCE%290733-9445%282002%29128:9%281111%29)
- **Why selected:** A complementary foundational treatment that explicitly combines posttensioned recentering with replaceable or concentrated energy-dissipating behavior in moment frames.
- **Terminology and argument pattern to learn:** Separate restoring and dissipating components in the force path; define flag-shaped response with parameters rather than appearance alone. Preserve the experimental boundary conditions and connection scale in performance claims.

#### 3. Restrepo and Rahman (2007)

- **Authors:** José I. Restrepo; Amar Rahman.
- **Title:** “Seismic Performance of Self-Centering Structural Walls Incorporating Energy Dissipators.”
- **DOI:** [10.1061/(ASCE)0733-9445(2007)133:11(1560)](https://doi.org/10.1061/%28ASCE%290733-9445%282007%29133:11%281560%29)
- **Why selected:** It extends the self-centering and supplemental-dissipation logic to wall systems and provides a bridge between connection mechanics and wall-level seismic performance.
- **Terminology and argument pattern to learn:** Distinguish wall rocking or joint opening, tendon restoring force, dissipator demand, stiffness, strength, energy dissipation, and residual displacement. Tie any low-damage claim to the observed wall and dissipator limit states.

#### 4. Eatherton, Ma, Krawinkler, Mar, Billington, Hajjar, and Deierlein (2014)

- **Authors:** Matthew R. Eatherton; Xiang Ma; Helmut Krawinkler; David Mar; Sarah Billington; Jerome F. Hajjar; Gregory G. Deierlein.
- **Title:** “Design Concepts for Controlled Rocking of Self-Centering Steel-Braced Frames.”
- **DOI:** [10.1061/(ASCE)ST.1943-541X.0001047](https://doi.org/10.1061/%28ASCE%29ST.1943-541X.0001047)
- **Why selected:** A widely used system-level design reference that makes the restoring mechanism, replaceable fuses, frame rocking, and capacity-protection objective explicit.
- **Terminology and argument pattern to learn:** Trace the design chain from target rocking response through posttensioning and energy dissipation to member-force demands and protected limit states. Do not use `self-centering`, `controlled rocking`, and `damage-free` as interchangeable labels.

#### 5. Martin, Deierlein, and Ma (2019)

- **Authors:** Amory Martin; Gregory G. Deierlein; Xiang Ma.
- **Title:** “Capacity Design Procedure for Rocking Braced Frames Using Modified Modal Superposition Method.”
- **DOI:** [10.1061/(ASCE)ST.1943-541X.0002329](https://doi.org/10.1061/%28ASCE%29ST.1943-541X.0002329)
- **Why selected:** An ASCE JSE Editor's Choice paper that develops a design-oriented method for higher-mode force demands rather than relying only on first-mode or pushover intuition.
- **Terminology and argument pattern to learn:** Define modal contributions, force combination, capacity-protected members, design demand, and validation set. Show how the modified method changes the governing demand and where its calibration range ends.

#### 6. East, Yassin, Ezzeldin, and Wiebe (2023)

- **Authors:** Matthew East; Ahmed Yassin; Mohamed Ezzeldin; Lydell Wiebe.
- **Title:** “Development of Controlled Rocking Masonry Walls with Energy Dissipation Accessible in a Steel Base.”
- **DOI:** [10.1061/JSENDH.STENG-11944](https://doi.org/10.1061/JSENDH.STENG-11944)
- **Why selected:** Recognized in the official JSE Best Paper Awards for structural hazards, it emphasizes not only controlled rocking and energy dissipation but also physical accessibility of the dissipating mechanism.
- **Terminology and argument pattern to learn:** Distinguish accessibility, replaceability, repairability, and demonstrated replacement. Trace wall behavior through the steel base, rocking interface, dissipator deformation, masonry demand, and residual response before making recovery claims.

## Cross-venue rules and exceptions for the Skill

### `posttensioned` is a controlled variant, not a universal error

The benchmark corpus itself contains `Posttensioned` in the titles of the 2001 and 2002 ASCE papers and `post-tensioned` in the 2009 EESD paper. Other sources use `post-tensioning`. Therefore:

- do not encode `posttensioned → post-tensioned` as an unconditional correction;
- preserve the exact spelling in article titles, reference lists, quotations, names of standards, and established system names;
- within new manuscript prose, flag mixed forms for the same grammatical role and referent as a consistency issue, not a technical inaccuracy;
- follow a current named-journal rule if it explicitly selects a form; otherwise use the manuscript's dominant intentional form or the user's `personal-preference`;
- do not merge the adjective `post-tensioned` and the process/noun `post-tensioning` merely to make strings identical.

### Hard checks versus reviewer prompts

The Skill may turn the following into deterministic findings only when the source and manuscript context are clear:

- bidirectional citation/reference mismatches;
- duplicate, missing, or out-of-sequence object labels;
- a count or formatting requirement stated unambiguously by the current named venue;
- inconsistent symbol, unit, abbreviation, or terminology use for the same referent;
- a venue-specific required file or section that is absent from a complete submission package.

The following remain semantic reviewer prompts unless direct evidence confirms them:

- whether a mechanism is genuinely self-centering or merely has small residual displacement in the tested cases;
- whether a replaceable device makes the whole structure repairable or rapidly recoverable;
- whether a model is sufficiently validated outside its calibration set;
- whether a causal or superiority claim is justified by the study design;
- whether terminology in a representative paper is preferable for the current manuscript.

### Minimum provenance for a journal-style finding

Include `journal`, `rule_level`, `source_url`, `checked_at`, `manuscript_anchor`, `observation`, and `exception_considered`. If the finding relies on a corpus pattern, name the paper and label the result `corpus-derived`; never write “the journal requires” on that basis alone.
