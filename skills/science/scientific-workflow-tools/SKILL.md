---
name: scientific-workflow-tools
description: Research-method workflow guide for hypothesis framing, peer-review style critique, reproducibility planning, study-design checks, and scientific-writing structure. Use when the user asks for manuscript critique, research-gap framing, hypothesis generation, reproducibility checklists, or study-planning support that should stay on the research side rather than patient-care decisions.
source: drugclaw
updated_at: "2026-03-11"
---

# Scientific Workflow Tools

Use this skill when the user needs higher-level research method support rather than raw database lookup or computation.

Typical triggers:
- generate or compare mechanistic hypotheses from observations
- review a manuscript draft for rigor, missing controls, or overstated claims
- build a reproducibility checklist before submission or release
- structure a scientific report, review, or response-to-reviewers plan
- identify missing controls, statistical gaps, or reporting-standard issues

## Bundled Asset

- `templates/reproducibility_checklist.py`

## Preferred Workflow

1. Restate the research question, claim, or draft under review.
2. Separate what is observed from what is inferred.
3. Enumerate methodological risks before proposing fixes.
4. Use the checklist template to create a durable artifact for reporting or project tracking.
5. Keep outputs explicitly on the research side. Do not cross into patient-level diagnosis or treatment planning.

## Reproducibility Checklist

```bash
python3 templates/reproducibility_checklist.py \
  --profile omics \
  --output research/omics_checklist.md \
  --summary research/omics_checklist.json
```

Supported baseline profiles:
- `general`
- `omics`
- `ml`
- `clinical-research`

Use the generated checklist as a starting artifact, then tailor it to the exact study.

## Working Rules

- Hypotheses should be testable and distinguish observation from mechanism.
- Peer-review style critique should prioritize reproducibility, controls, statistics, and claim scope.
- Scientific writing support should strengthen structure and rigor, not fabricate citations or results.
- Reporting-guideline and checklist outputs are planning artifacts, not proof that the study is compliant.

## Related Skills

For literature search outputs and evidence tables, activate `literature-review-tools`.
For clinical-study design and reporting-guideline selection, activate `clinical-research-tools`.
For numerical statistical execution, activate `stat-modeling-tools` or `survival-analysis-tools`.
For experiment suggestion or bounded closed-loop optimization, activate `bayesian-optimization-tools`.
For figure generation, activate `scientific-visualization-tools`.
For bioinformatics, chemistry, or docking execution, activate the corresponding domain skill instead of keeping the task abstract.
