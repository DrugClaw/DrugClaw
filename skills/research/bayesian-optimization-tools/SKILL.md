---
name: bayesian-optimization-tools
description: Bayesian optimization workflow guide for experiment suggestion, condition tuning, and closed-loop parameter search with Gaussian-process surrogates. Use when the user asks which experiment to try next, how to tune reaction or assay conditions, or how to balance exploration versus exploitation over a bounded numeric search space.
source: drugclaw
updated_at: "2026-03-11"
---

# Bayesian Optimization Tools

Use this skill when the user wants the runtime to recommend the next experiment or parameter set instead of only summarizing past results.

Typical triggers:
- suggest the next assay or reaction condition to try
- tune temperature, pH, concentration, or incubation parameters under limited budget
- optimize model or simulation hyperparameters when evaluations are expensive
- build a closed-loop experiment table from prior results and explicit bounds

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["numpy", "sklearn"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

Do not claim a suggestion run completed if `numpy` or `scikit-learn` is missing.

## Bundled Asset

- `templates/bayesian_optimize.py`

## Preferred Workflow

1. Confirm the objective column and whether the user wants to maximize or minimize it.
2. Confirm the numeric search-space bounds for every parameter.
3. Start from a saved history table or inline JSON records.
4. Export ranked suggestions plus a summary JSON so the next round is reproducible.
5. Treat the output as an experiment-prioritization proposal, not proof that the optimum has been found.

## Quick Start

```bash
python3 templates/bayesian_optimize.py \
  --input experiments.csv \
  --objective-column yield \
  --param-column temperature \
  --param-column ph \
  --bound temperature:20:80 \
  --bound ph:5.5:8.5 \
  --direction maximize \
  --output optimization/next_conditions.csv \
  --summary optimization/next_conditions.json
```

Inline JSON example:

```bash
python3 templates/bayesian_optimize.py \
  --history-json '[{"temperature": 20, "ph": 7.0, "yield": 0.52}, {"temperature": 35, "ph": 6.5, "yield": 0.68}]' \
  --objective-column yield \
  --bound temperature:20:60 \
  --bound ph:5.5:8.0 \
  --direction maximize \
  --suggestions 3 \
  --output optimization/suggestions.csv \
  --summary optimization/suggestions.json
```

## Output Expectations

Good answers should mention:
- the exact objective column and optimization direction
- which parameter bounds were used
- the acquisition policy and exploration weight
- the best observed point so far
- how many ranked suggestions were written
- where the CSV and summary JSON were saved

## Related Skills

For regression or hypothesis testing on finished experiments, activate `stat-modeling-tools`.
For study-planning artifacts or reproducibility checklists, activate `scientific-workflow-tools`.
For chemistry, omics, or docking analyses that generate the objective values, activate the corresponding domain skill.
