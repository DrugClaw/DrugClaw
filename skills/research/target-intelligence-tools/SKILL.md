---
name: target-intelligence-tools
description: Target research workflow guide for building compact drug-target dossiers across protein identity, disease evidence, known drugs, interaction partners, pathways, and variant constraint signals. Use when the user asks for a target brief, target validation snapshot, or a one-file summary of what is known about a gene or protein target.
source: drugclaw
updated_at: "2026-03-11"
---

# Target Intelligence Tools

Use this skill when the user wants an integrated target brief rather than isolated API hits.

Typical triggers:
- build a quick dossier for a therapeutic target
- summarize what is known about a gene or protein target
- collect disease evidence, known drugs, pathways, and interaction partners in one report
- prepare a target-validation snapshot before docking, screening, or literature deepening

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["requests"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If outbound network access is blocked, say so explicitly before claiming the dossier ran.

## Bundled Asset

- `templates/target_dossier.py`

## Preferred Workflow

1. Start from the clearest target identifier available.
2. Resolve the target to stable IDs first.
3. Pull disease associations, known drugs, pathways, and interaction partners into one markdown dossier.
4. Keep the output compact and explicit about missing data.
5. Treat the dossier as a research briefing artifact, not a validated decision report.

## Quick Start

```bash
python3 templates/target_dossier.py \
  --query EGFR \
  --output targets/egfr_dossier.md \
  --summary targets/egfr_dossier.json \
  --detail-json targets/egfr_dossier.detail.json
```

## Output Expectations

Good answers should mention:
- the exact identifier or query used
- which stable IDs were resolved
- how many disease, drug, pathway, and interaction rows were found
- whether ClinVar or gnomAD constraint signals were available
- where the markdown dossier and summary JSON were written

## Related Skills

For raw UniProt, PDB, ClinVar, gnomAD, Reactome, STRING, or OpenTargets queries, activate `bio-db-tools`.
For public compound and regulatory APIs such as ChEMBL, BindingDB, openFDA, ClinicalTrials.gov, or OpenAlex, activate `pharma-db-tools`.
For local variant-callset summarization before target interpretation, activate `variant-analysis-tools`.
