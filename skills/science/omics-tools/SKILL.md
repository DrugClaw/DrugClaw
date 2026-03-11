---
name: omics-tools
description: Omics and single-cell workflow guide for AnnData, Scanpy-style dataset profiling, PyDESeq2-oriented count checks, pysam alignment inspection, and pyOpenMS mass-spectrometry summaries. Use when the user asks to inspect h5ad files, summarize BAM regions, profile omics count tables, or inventory mzML experiments before deeper modeling.
source: drugclaw
updated_at: "2026-03-11"
---

# Omics Tools

Use this skill when the user asks to inspect or triage omics datasets before deeper modeling.

Typical triggers:
- inspect `h5ad` or annotated single-cell matrices
- summarize cell types, batches, and QC columns from AnnData
- check alignment coverage or region counts from BAM or CRAM files
- profile a mass-spectrometry mzML experiment before proteomics or metabolomics analysis
- verify whether a dataset is ready for Scanpy, PyDESeq2, or downstream modeling

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pandas", "numpy", "anndata", "pysam"]
extra = ["scanpy", "pydeseq2", "pyopenms", "skbio"]
for name in mods + extra:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

Do not claim single-cell, alignment, or mass-spec analysis ran if the required module is absent.

## Bundled Assets

- `templates/single_cell_profile.py`
- `templates/pysam_region_profile.py`
- `templates/mzml_summary.py`

## Preferred Workflow

1. Start with structural profiling before statistical interpretation.
2. For single-cell data, inspect dimensions, metadata coverage, and top group counts before clustering or marker analysis.
3. For BAM or CRAM data, report mapped reads, index presence, and region counts before variant or expression conclusions.
4. For mzML data, summarize spectra and acquisition structure before quantification.
5. Save both a tabular output and a compact summary JSON.

## Single-Cell And AnnData Profiling

```bash
python3 templates/single_cell_profile.py \
  --input data/pbmc.h5ad \
  --cell-type-column cell_type \
  --group-column batch \
  --group-column donor \
  --output omics/pbmc_profile.csv \
  --summary omics/pbmc_profile.json
```

Use this first for:
- cell and gene counts
- observation and variable column inventory
- top cell-type or batch distributions
- quick readiness checks before Scanpy or scvi-style modeling

## Alignment Profiling With Pysam

```bash
python3 templates/pysam_region_profile.py \
  --bam alignments/sample.bam \
  --region chr7:55019017-55211628 \
  --region chr12:25205246-25250928 \
  --output omics/sample_region_profile.csv \
  --summary omics/sample_region_profile.json
```

Use this for:
- mapped versus unmapped read counts
- region-specific read totals
- quick QA before variant or coverage workflows

## Mass-Spectrometry Inventory

```bash
python3 templates/mzml_summary.py \
  --input proteomics/run01.mzML \
  --output omics/run01_mzml_profile.csv \
  --summary omics/run01_mzml_profile.json
```

Use this for:
- spectra and chromatogram counts
- MS level inventory
- retention-time range inspection before full pyOpenMS workflows

## Working Boundary

This skill is for data profiling and workflow triage. It does not replace full differential-expression analysis, trajectory inference, peptide identification, or validated clinical interpretation.

## Output Expectations

Good answers should mention:
- exact file paths and any regions or columns used
- which template ran
- core dataset dimensions or counts
- what output files were written
- whether the result is only profiling or a deeper analytical conclusion
- any missing modules, index files, or malformed records

## Related Skills

For general sequence analysis or command-line bioinformatics, activate `bio-tools`.
For remote biology APIs such as GEO, Ensembl, UniProt, PDB, or Reactome, activate `bio-db-tools`.
For transcription-factor network inference from processed expression matrices, activate `grn-tools`.
For statistical modeling or survival analysis on omics-derived tables, activate `stat-modeling-tools` or `survival-analysis-tools`.
For static or interactive omics figures, activate `scientific-visualization-tools`.
For chemistry, ADMET, QSAR, or structure-aware affinity, activate `chem-tools`.
