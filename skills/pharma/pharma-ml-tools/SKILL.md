---
name: pharma-ml-tools
description: Pharmaceutical machine-learning workflow guide for library profiling, molecular featurization, benchmark dataset fetch, medicinal-chemistry filtering, and optional pose-generation handoff. Use when the user asks for datamol, molfeat, PyTDC, medchem, compound-library triage, dataset preparation, or chemistry-ML baselines beyond simple descriptor calculation.
source: drugclaw
updated_at: "2026-03-11"
---

# Pharma ML Tools

Use this skill when the user asks for compound-library profiling, chemistry ML feature generation, medicinal-chemistry screening, or benchmark dataset preparation.

Typical triggers:
- standardize and profile a compound library before QSAR or screening
- featurize molecules with `molfeat` for downstream ML
- pull benchmark-ready ADME, toxicity, DTI, or DDI datasets with `PyTDC`
- apply medicinal-chemistry rules or alert filters before prioritization
- compare scaffolds, duplicates, or diversity in a virtual-screening library
- prepare a docking or QSAR campaign with better compound hygiene

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pandas", "numpy", "datamol", "molfeat", "medchem"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
try:
    import tdc
    print("PyTDC: ok")
except Exception as exc:
    print(f"PyTDC: missing ({exc})")
PY
```

If a requested module is missing, say so explicitly. Do not claim the screen, featurization, or dataset pull completed.

## Bundled Assets

- `templates/datamol_library_profile.py`
- `templates/molfeat_featurize.py`
- `templates/pytdc_dataset_fetch.py`
- `templates/medchem_screen.py`

## Preferred Workflow

1. Normalize the input table first and identify the exact SMILES column.
2. Run `datamol_library_profile.py` before building models so duplicates, invalid structures, and scaffold concentration are visible.
3. Use `medchem_screen.py` before large docking or QSAR jobs to flag problematic chemotypes.
4. Use `molfeat_featurize.py` when the user needs model-ready features rather than only descriptor summaries.
5. Use `pytdc_dataset_fetch.py` when the user needs reproducible public benchmark datasets rather than ad hoc CSV collection.
6. Keep outputs under a dedicated directory such as `./pharma_ml/`.

## Library Profiling With Datamol

```bash
python3 templates/datamol_library_profile.py \
  --input libraries/kinase_hits.csv \
  --smiles-column smiles \
  --id-column compound_id \
  --output pharma_ml/kinase_hits_profile.csv \
  --summary pharma_ml/kinase_hits_profile.json
```

Use this first for:
- canonical SMILES and InChIKey generation
- invalid structure detection
- scaffold counts
- molecular-property summaries before modeling

## Molfeat Featurization

```bash
python3 templates/molfeat_featurize.py \
  --input libraries/kinase_hits.csv \
  --smiles-column smiles \
  --id-column compound_id \
  --featurizer ecfp \
  --output pharma_ml/kinase_hits_ecfp.csv \
  --summary pharma_ml/kinase_hits_ecfp.json
```

Supported baseline featurizers in the bundled template:
- `ecfp`
- `maccs`
- `rdkit2d`

Use this for local QSAR, ranking, clustering, or embedding handoff.

## PyTDC Benchmark Datasets

```bash
python3 templates/pytdc_dataset_fetch.py \
  --task adme \
  --dataset Caco2_Wang \
  --split-method scaffold \
  --out-dir pharma_ml/caco2_wang
```

Good use cases:
- ADME or toxicity baselines
- DTI or DDI dataset retrieval
- reproducible train/valid/test splits for benchmarking

## Medicinal-Chemistry Screening

```bash
python3 templates/medchem_screen.py \
  --input libraries/kinase_hits.csv \
  --smiles-column smiles \
  --id-column compound_id \
  --output pharma_ml/kinase_hits_medchem.csv \
  --summary pharma_ml/kinase_hits_medchem.json
```

Use this for:
- Rule-of-Five and lead-like checks
- alert-oriented library triage
- quick pass/fail summaries before wet-lab nomination

Treat these filters as prioritization heuristics, not hard truth.

## DiffDock Boundary

If the user asks for diffusion docking or deep pose generation, acknowledge that this runtime already includes `docking-tools` for Vina-style workflows, but DiffDock-class workflows require a heavier environment with PyTorch Geometric, model weights, and usually GPU acceleration. Do not pretend that support is bundled unless the environment is confirmed.

## Output Expectations

Good answers should mention:
- the exact input file and SMILES column
- which template ran
- valid versus invalid molecule counts
- whether outputs are profiling, features, dataset splits, or medchem filters
- what files were written
- any module, network, or dataset-license caveats

## Related Skills

For public APIs such as PubChem, ChEMBL, openFDA, ClinicalTrials.gov, or OpenAlex, activate `pharma-db-tools`.
For RDKit descriptors, ADMET heuristics, DrugBank, QSAR, or structure-aware affinity, activate `chem-tools`.
For docking and pose-level workflows, activate `docking-tools`.
