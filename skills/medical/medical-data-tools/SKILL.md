---
name: medical-data-tools
description: Medical data workflow guide for DICOM metadata inspection and basic de-identification, physiological signal analysis with NeuroKit2, and cohort-table profiling for clinical research datasets. Use when the user asks to inspect imaging metadata, summarize ECG/PPG/EDA/RSP/EMG signals, or profile tabular medical datasets without making patient-specific diagnoses or treatment decisions.
---

# Medical Data Tools

Use this skill when the user asks to inspect medical imaging files, biosignal recordings, or cohort tables for research, QA, or data-engineering work.

Typical triggers:
- inspect DICOM files, modality mix, study or series structure, metadata completeness
- write basic de-identified DICOM copies for downstream research workflows
- analyze ECG, PPG, EDA, RSP, or EMG tables with NeuroKit2
- summarize clinical cohort tables exported from EHR, OMOP, FHIR, registry, or claims workflows
- profile labels, codes, visits, time ranges, or subgroup balance before modeling

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pandas", "numpy", "pydicom", "neurokit2"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If `pydicom` or `neurokit2` is missing, say so immediately instead of pretending the analysis ran.

## Bundled Assets

- `templates/dicom_inspect.py`
- `templates/neuro_signal_analyze.py`
- `templates/clinical_cohort_profile.py`

## Preferred Workflow

1. Identify the input surface first: DICOM file tree, CSV or TSV signal table, or cohort table.
2. Run the smallest deterministic template before any broader interpretation.
3. Save both the machine-readable output and the summary JSON.
4. Report missing columns, unreadable files, or module gaps explicitly.
5. Treat all outputs as research or operations artifacts, not clinical decisions.

## DICOM

Use `templates/dicom_inspect.py` for:
- modality or study inventory
- metadata QA
- study/series counts
- basic research-oriented de-identification copies

Quick start:

```bash
python3 templates/dicom_inspect.py imaging/ct_series \
  --recursive \
  --output medical/dicom_inventory.csv \
  --summary medical/dicom_inventory.json
```

Basic de-identification example:

```bash
python3 templates/dicom_inspect.py imaging/mri_case \
  --recursive \
  --deidentify-dir medical/dicom_deidentified \
  --output medical/dicom_case.csv \
  --summary medical/dicom_case.json
```

Deliverables:
- per-file metadata CSV
- summary JSON with modality counts and study/series counts
- optional de-identified DICOM copies

State clearly that the built-in de-identification is basic tag scrubbing, not a validated anonymization pipeline.

## Biosignals

Use `templates/neuro_signal_analyze.py` for:
- ECG feature extraction and quality-aware summaries
- PPG, EDA, RSP, or EMG preprocessing and interval features
- quick physiology feature generation for downstream research models

Example:

```bash
python3 templates/neuro_signal_analyze.py \
  --input signals/ecg.csv \
  --signal-column ecg \
  --signal-type ecg \
  --sampling-rate 250 \
  --signals-output medical/ecg_processed.csv \
  --output medical/ecg_features.csv \
  --summary medical/ecg_features.json
```

Deliverables:
- one-row feature CSV
- optional processed signal CSV
- summary JSON with duration and processing metadata

Do not overstate these outputs. They are research features, signal summaries, and QA signals, not diagnoses.

## Cohort Tables

Use `templates/clinical_cohort_profile.py` for:
- patient and visit counts
- label balance checks
- code distribution checks
- subgroup balance before survival, prediction, or trial-emulation work

Example:

```bash
python3 templates/clinical_cohort_profile.py \
  --input cohorts/nsclc_registry.csv \
  --patient-id-column patient_id \
  --visit-id-column visit_id \
  --time-column encounter_time \
  --label-column response \
  --code-column regimen \
  --group-column sex \
  --group-column stage \
  --output medical/nsclc_profile.csv \
  --summary medical/nsclc_profile.json
```

Deliverables:
- normalized metric table CSV
- summary JSON with patient, visit, label, code, and group distributions

## Output Expectations

Good answers should mention:
- the exact input paths and column names used
- which template was run
- what files were written
- the key data-quality findings
- any missing metadata, missing modules, or de-identification limits

## Related Skills

For public drug, clinical-trial, regulatory, or literature APIs, activate `pharma-db-tools`.
For study design, evidence synthesis, and reporting-guideline work, activate `clinical-research-tools`.
For biology databases, activate `bio-db-tools`.
For hypothesis tests, regression, or survival analysis on cohort tables, activate `stat-modeling-tools` or `survival-analysis-tools`.
For review matrices, citation cleanup, or hypothesis and reproducibility planning, activate `literature-review-tools` or `scientific-workflow-tools`.
