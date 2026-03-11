---
name: scientific-visualization-tools
description: Scientific visualization workflow guide for publication-ready static figures with seaborn or matplotlib and interactive figures with Plotly. Use when the user asks for scientific plots, cohort or assay figures, publication graphics, dashboards, or reusable plotting scripts for research datasets.
source: drugclaw
updated_at: "2026-03-11"
---

# Scientific Visualization Tools

Use this skill when the user needs a figure artifact rather than only a numeric summary.

Typical triggers:
- publication-ready scatter, box, violin, bar, or heatmap figures
- interactive HTML charts for exploratory research data review
- small reusable plotting scripts for assay, omics, or cohort tables
- consistent styling across scientific plots

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pandas", "matplotlib", "seaborn", "plotly"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If key plotting modules are missing, recommend the optional `drug-sandbox` image documented in `docs/operations/science-runtime.md`.

## Bundled Assets

- `templates/publication_plot.py`
- `templates/interactive_plot.py`

## Preferred Workflow

1. Decide first whether the output should be static publication art or interactive exploration.
2. Keep the plotting script parameterized by column names rather than hardcoding one dataset.
3. Save the figure and a small JSON summary of what was plotted.
4. Do not use interactive charts where a paper-ready static figure is required.
5. Do not claim statistical meaning from a plot unless the underlying analysis is also reported.

## Static Publication Plots

```bash
python3 templates/publication_plot.py \
  --input figures/assay.csv \
  --kind box \
  --x-column arm \
  --y-column response \
  --color-column arm \
  --output figures/assay_box.png \
  --summary figures/assay_box.json
```

Supported baseline kinds:
- `scatter`
- `line`
- `box`
- `violin`
- `bar`
- `heatmap`

## Interactive Plotly Charts

```bash
python3 templates/interactive_plot.py \
  --input figures/cohort.csv \
  --kind scatter \
  --x-column age \
  --y-column biomarker \
  --color-column response \
  --output figures/cohort_scatter.html \
  --summary figures/cohort_scatter.json
```

Use this for exploratory review, dashboards, and lightweight sharing.

## Related Skills

For statistical inference behind a plot, activate `stat-modeling-tools`.
For Kaplan-Meier and time-to-event figures, activate `survival-analysis-tools`.
For broader scientific-writing and manuscript-structure work, activate `scientific-workflow-tools`.
