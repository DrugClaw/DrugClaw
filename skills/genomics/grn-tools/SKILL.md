---
name: grn-tools
description: Gene regulatory network workflow guide for transcriptomics and single-cell expression matrices using Arboreto, GRNBoost2, and GENIE3. Use when the user asks to infer transcription factor-target links, score regulatory edges, or build a GRN from bulk or single-cell expression data.
source: drugclaw
updated_at: "2026-03-11"
---

# GRN Tools

Use this skill when the user asks for gene regulatory network inference rather than basic dataset profiling.

Typical triggers:
- infer transcription factor to target edges from bulk RNA-seq or single-cell expression data
- run GRNBoost2 or GENIE3 on an expression matrix
- restrict GRN inference to a curated TF list
- export ranked regulatory edges for downstream SCENIC-style or network analysis

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pandas", "arboreto"]
extra = ["distributed"]
for name in mods + extra:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

`distributed` is only required when using `--workers` for a local Dask cluster.

## Bundled Asset

- `templates/arboreto_grn.py`

## Preferred Workflow

1. Confirm the matrix orientation before inference. Arboreto expects observations as rows and genes as columns.
2. Drop sample-id columns or transpose the matrix before fitting.
3. Provide a TF whitelist when the user wants biologically narrower networks.
4. Save the full ranked edge table and a summary JSON.
5. Treat the output as an inferred regulatory hypothesis set, not a validated causal network.

## Quick Start

```bash
python3 templates/arboreto_grn.py \
  --input expression.tsv \
  --algorithm grnboost2 \
  --tf-file tf_names.txt \
  --min-importance 0.01 \
  --top-edges 5000 \
  --output grn/network.tsv \
  --summary grn/network.json
```

If the input is genes-by-samples, transpose it first or use `--transpose`:

```bash
python3 templates/arboreto_grn.py \
  --input expression_genes_by_samples.csv \
  --transpose \
  --algorithm genie3 \
  --workers 4 \
  --output grn/network.tsv \
  --summary grn/network.json
```

## Output Expectations

Good answers should mention:
- the exact matrix path and whether it was transposed
- which algorithm ran
- whether a TF list was used
- observation count, gene count, and retained edge count
- any `distributed` or dependency limitation
- where the network TSV and summary JSON were written

## Related Skills

For `h5ad`, BAM, CRAM, or mzML dataset triage before GRN inference, activate `omics-tools`.
For statistical modeling on downstream regulon or score tables, activate `stat-modeling-tools`.
For figure generation from network summaries, activate `scientific-visualization-tools`.
