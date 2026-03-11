---
name: survival-analysis-tools
description: Survival and time-to-event workflow guide for Kaplan-Meier summaries, log-rank tests, and Cox proportional hazards models with reproducible outputs. Use when the user asks for time-to-event analysis, censored data summaries, hazard ratios, or survival-group comparison for research datasets.
source: drugclaw
updated_at: "2026-03-11"
---

# Survival Analysis Tools

Use this skill when the user needs time-to-event analysis with censoring-aware summaries.

Typical triggers:
- Kaplan-Meier curves or survival probability tables
- log-rank comparison between treatment arms
- Cox proportional hazards regression with hazard ratios
- time-to-event or progression-free survival analysis
- censored cohort summaries for translational or clinical research

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["numpy", "pandas", "statsmodels", "matplotlib"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
try:
    import sksurv
    print("sksurv: optional-ok")
except Exception as exc:
    print(f"sksurv: optional-missing ({exc})")
PY
```

The bundled template runs on the stable `statsmodels` baseline. Advanced machine-learning survival models from `scikit-survival` remain optional and should only be claimed when the environment actually has them.

## Bundled Asset

- `templates/survival_analysis.py`

## Preferred Workflow

1. Confirm the time and event coding first.
2. Generate group-level Kaplan-Meier summaries before fitting adjusted models.
3. Add Cox covariates only after checking the columns and coding logic.
4. Export both tables and a survival plot.
5. Treat hazard ratios as model-based associations, not automatic causal effects.

## Kaplan-Meier And Cox Baseline

```bash
python3 templates/survival_analysis.py \
  --input survival/nsclc.csv \
  --time-column pfs_days \
  --event-column progressed \
  --group-column arm \
  --covariate age \
  --covariate stage_numeric \
  --covariate biomarker_score \
  --plot-output survival/nsclc_km.png \
  --km-output survival/nsclc_km.csv \
  --cox-output survival/nsclc_cox.csv \
  --summary survival/nsclc_summary.json
```

Use this for:
- group-level median survival summaries
- Kaplan-Meier plots
- log-rank p-values when a group column is present
- Cox proportional hazards coefficients and hazard ratios

## Boundary

The bundled baseline does not provide random survival forests, gradient-boosted survival models, or integrated Brier score pipelines out of the box. If the user explicitly needs those, confirm that `scikit-survival` is available first.

## Related Skills

For general hypothesis tests or non-survival regression, activate `stat-modeling-tools`.
For figures beyond the bundled KM plot, activate `scientific-visualization-tools`.
For study-design or endpoint-planning support, activate `clinical-research-tools`.
