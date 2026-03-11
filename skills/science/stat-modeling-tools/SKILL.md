---
name: stat-modeling-tools
description: Statistical modeling workflow guide for hypothesis tests, effect-size reporting, statsmodels regression, diagnostics, and structured result export. Use when the user asks for statistical test selection, OLS or logistic regression, coefficient tables, inference, or reproducible statistical summaries for scientific datasets.
source: drugclaw
updated_at: "2026-03-11"
---

# Stat Modeling Tools

Use this skill when the user needs reproducible statistical analysis rather than only visual inspection.

Typical triggers:
- choose or run a hypothesis test on tabular data
- compare two groups or test association between variables
- fit OLS, logistic, or Poisson models with coefficient tables
- inspect residuals, p-values, confidence intervals, or effect sizes
- generate machine-readable statistical summaries for a manuscript or report

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["numpy", "pandas", "scipy", "statsmodels"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If key modules are missing, say so explicitly and recommend the optional `drug-sandbox` image documented in `docs/operations/science-runtime.md`.

## Bundled Assets

- `templates/stat_test_report.py`
- `templates/statsmodels_regression.py`

## Preferred Workflow

1. Identify outcome type first: continuous, binary, count, or categorical contingency table.
2. Run a small deterministic statistical summary before fitting a larger model.
3. Report effect sizes and confidence intervals, not only p-values.
4. Save CSV and JSON outputs so the result is reusable.
5. Keep claim scope tied to the study design. Statistical association is not causal proof.

## Hypothesis Tests

```bash
python3 templates/stat_test_report.py \
  --input stats/assay.csv \
  --test independent_ttest \
  --value-column response \
  --group-column arm \
  --group-a control \
  --group-b treated \
  --output stats/assay_ttest.csv \
  --summary stats/assay_ttest.json
```

Supported baseline tests in the bundled template:
- `independent_ttest`
- `paired_ttest`
- `mannwhitney`
- `chi_square`
- `pearson`
- `spearman`

Use this for quick but explicit statistical reporting.

## Regression With Statsmodels

```bash
python3 templates/statsmodels_regression.py \
  --input stats/cohort.csv \
  --model ols \
  --outcome response \
  --feature age \
  --feature dose \
  --feature biomarker \
  --output stats/ols_coefficients.csv \
  --summary stats/ols_summary.json
```

Supported baseline models in the bundled template:
- `ols`
- `logit`
- `poisson`

Use this for:
- coefficient tables with confidence intervals
- basic inference and model-fit summaries
- prediction export for downstream review

## Working Rules

- Prefer exact test names and explicit group labels.
- Check whether the data are paired before running paired tests.
- For regression, list the exact feature set and reference coding assumptions.
- Do not oversell significance when effect sizes are trivial.
- Distinguish exploratory testing from pre-specified confirmatory analysis.

## Related Skills

For Kaplan-Meier, Cox models, and time-to-event workflows, activate `survival-analysis-tools`.
For static or interactive figures, activate `scientific-visualization-tools`.
For study design, reproducibility planning, or manuscript critique, activate `scientific-workflow-tools` or `clinical-research-tools`.
