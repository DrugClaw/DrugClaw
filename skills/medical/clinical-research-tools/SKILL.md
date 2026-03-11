---
name: clinical-research-tools
description: Clinical research workflow guide for protocol design, endpoint selection, evidence grading, reporting-guideline selection, statistical planning, and clinical-trial evidence synthesis. Use when the user asks to design or review human-subjects research, trial analyses, observational studies, study protocols, CSRs, or clinical evidence summaries without requesting patient-specific diagnosis or treatment decisions.
---

# Clinical Research Tools

Use this skill for group-level human research work, not bedside care.

Typical triggers:
- choose between RCT, cohort, case-control, cross-sectional, diagnostic, or single-arm designs
- define primary and secondary endpoints, estimands, eligibility criteria, or subgroup analyses
- select the right reporting guideline such as CONSORT, STROBE, PRISMA, STARD, TRIPOD, SPIRIT, or CARE
- draft protocol, SAP, CSR, or evidence-summary outlines
- review bias, confounding, missing data, and sample-size assumptions
- prepare trial or real-world-evidence summaries for drug-discovery programs

## Working Rules

1. Keep the task at the study or cohort level.
2. Separate confirmed study facts from proposed design choices.
3. State assumptions behind endpoint, power, and statistical-model choices.
4. Call out data leakage, immortal-time bias, selection bias, and confounding whenever relevant.
5. Do not present DrugClaw as giving medical advice, treatment recommendations, or diagnostic decisions.

## Study Design Map

Use this quick routing:
- `RCT`: intervention efficacy, causal inference, registration-ready protocols
- `Prospective cohort`: prognosis, exposure-outcome tracking, real-world evidence
- `Retrospective cohort`: registry or EHR analyses with explicit confounding control
- `Case-control`: rare outcomes or exploratory risk-factor work
- `Cross-sectional`: prevalence, survey snapshots, baseline association work
- `Diagnostic accuracy`: sensitivity, specificity, ROC, calibration, decision curves
- `Prediction model`: risk scores, survival models, treatment-response models with external validation plans

## Reporting Guideline Map

Choose and state the governing framework early:
- `CONSORT`: randomized trials
- `SPIRIT`: trial protocols
- `STROBE`: observational studies
- `PRISMA`: systematic reviews and meta-analysis
- `STARD`: diagnostic accuracy studies
- `TRIPOD`: prediction models
- `CARE`: case reports
- `ICH E3`: clinical study reports

## Protocol Workflow

For protocol or study-design requests:
1. Define population, intervention or exposure, comparator, outcome, and timeframe.
2. State inclusion and exclusion criteria.
3. Define primary endpoint, key secondary endpoints, and censoring rules.
4. Choose analysis populations: ITT, mITT, per-protocol, safety.
5. Describe missing-data handling and sensitivity analyses.
6. State sample-size assumptions clearly: alpha, power, effect size, event rate, dropout.
7. Specify monitoring, ethics, registration, and data-governance requirements.

## Statistical Planning Checklist

Always address:
- endpoint type: binary, continuous, count, time-to-event
- stratification variables and subgroup policy
- multiplicity control
- covariate adjustment policy
- temporal leakage and look-ahead bias
- external validation or temporal validation when building prediction models
- calibration, not only discrimination, for predictive work

## Evidence Synthesis

For evidence summaries:
- identify study type and evidence level
- note patient population, line of therapy, biomarker context, and comparator
- distinguish efficacy, safety, and external-validity conclusions
- state what remains uncertain
- use cautious language for indirect or observational evidence

## Outputs

Good outputs usually include:
- one-page design summary or protocol skeleton
- endpoint table
- statistical analysis outline
- bias and limitation section
- reporting-guideline checklist

## Related Skills

For ClinicalTrials.gov, openFDA, or OpenAlex lookups, activate `pharma-db-tools`.
For cohort tables, biosignals, or DICOM datasets, activate `medical-data-tools`.
For citation cleanup, evidence matrices, or structured review drafting, activate `literature-review-tools`.
For hypothesis tests, regression, or effect-size reporting, activate `stat-modeling-tools`.
For Kaplan-Meier, log-rank, or Cox workflows, activate `survival-analysis-tools`.
For manuscript critique, hypothesis framing, or reproducibility checklists, activate `scientific-workflow-tools`.
For molecular, variant, pathway, or structure work, activate `bio-tools`, `bio-db-tools`, `chem-tools`, or `docking-tools` as appropriate.
