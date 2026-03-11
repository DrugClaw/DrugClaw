---
name: variant-analysis-tools
description: Variant and VCF workflow guide for local SNV, indel, and structural-variant summarization, filtering, and consequence triage. Use when the user asks to inspect a VCF, count mutation classes, filter by VAF or depth, summarize genes or consequences, or prepare a local variant report before downstream annotation.
source: drugclaw
updated_at: "2026-03-11"
---

# Variant Analysis Tools

Use this skill when the user provides a VCF or BCF and wants concrete counts, filtering, or mutation summaries instead of only database lookup.

Typical triggers:
- summarize the contents of a VCF or BCF
- count SNVs, indels, or structural variants
- filter by VAF, read depth, PASS status, or variant type
- exclude intronic or intergenic consequences from a local callset
- generate a machine-readable variant table before ClinVar, gnomAD, or dbSNP follow-up

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pysam"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

Do not claim VCF analysis ran if `pysam` is unavailable.

## Bundled Asset

- `templates/variant_report.py`

## Preferred Workflow

1. Confirm which sample to read when the VCF is multi-sample.
2. Decide whether the user wants raw counts, filtered rows, or both.
3. Apply explicit filters for VAF, depth, PASS status, and consequence terms.
4. Export the filtered table plus a summary JSON.
5. If the user wants clinical significance or population frequency, hand the filtered rows to `bio-db-tools` for ClinVar, gnomAD, or dbSNP follow-up.

## Quick Start

```bash
python3 templates/variant_report.py \
  --input cohort/sample.vcf.gz \
  --sample TUMOR \
  --pass-only \
  --min-vaf 0.05 \
  --min-depth 20 \
  --exclude-consequence intronic \
  --exclude-consequence intergenic \
  --output variants/sample_filtered.csv \
  --summary variants/sample_filtered.json
```

Structural-variant focused example:

```bash
python3 templates/variant_report.py \
  --input sv_calls.vcf.gz \
  --include-variant-type DEL \
  --include-variant-type DUP \
  --output variants/sv_subset.csv \
  --summary variants/sv_subset.json
```

## Output Expectations

Good answers should mention:
- the exact variant file and sample used
- which filters were applied
- total records seen versus retained
- variant-type and consequence distributions
- top affected genes after filtering
- where the CSV and summary JSON were written

## Related Skills

For ClinVar, Ensembl, gnomAD, or dbSNP lookups, activate `bio-db-tools`.
For statistical testing or survival modeling on variant-derived burden tables, activate `stat-modeling-tools` or `survival-analysis-tools`.
For target-level interpretation around genes hit by the variants, activate `target-intelligence-tools`.
