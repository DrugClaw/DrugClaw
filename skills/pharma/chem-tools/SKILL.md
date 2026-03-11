---
name: chem-tools
description: Computational chemistry workflow guide for DeepChem, PySCF, RDKit, assay-table normalization, PDBbind-style structure datasets, QSAR and structure benchmarks, DrugBank lookup, ligand-only and structure-aware affinity prediction, ADMET triage, bioactivity prediction, virtual screening, and docking follow-up.
source: drugclaw
updated_at: "2026-03-10"
---

# Chem Tools

Use this skill when the user asks to:
- featurize molecules from SMILES, CSV, TSV, or text inputs
- use DeepChem for molecular ML preprocessing, fingerprints, or dataset preparation
- use PySCF for small-molecule HF or DFT calculations
- run ADMET triage or structural alert screening
- normalize ChEMBL, BindingDB, MoleculeNet, or generic assay tables into DrugClaw-ready datasets
- adapt PDBbind-style structure datasets into benchmark-ready CSV tables
- benchmark QSAR baselines with scaffold or random splits
- train or apply ligand binding-affinity models from labeled SMILES
- train or apply structure-aware protein-ligand affinity models from complexes
- benchmark structure-aware protein-ligand models on grouped or random splits
- train or apply bioactivity models from labeled SMILES
- rank a library for virtual screening with chemistry, activity, affinity, and docking signals
- search DrugBank from a local export or the online discovery API, export the matched drug structure, or read drug descriptive properties
- compute chemistry follow-up checks on docking hits
- inspect small-molecule descriptors, simple QM sanity checks, or ligand ranking features

## Environment Check

Do not assume the chemistry stack is available. Check first.

```bash
which python3 || true
python3 - <<'PY'
mods = ["deepchem", "pyscf", "rdkit", "numpy", "pandas", "sklearn"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If key modules are missing, say so immediately and recommend the unified `drug-sandbox` image documented in `docs/operations/science-runtime.md`.

## Bundled Assets

- `templates/deepchem_featurize.py`
- `templates/pyscf_single_point.py`
- `templates/rdkit_descriptors.py`
- `templates/admet_screen.py`
- `templates/assay_data_prepare.py`
- `templates/pdbbind_prepare.py`
- `templates/binding_affinity_predict.py`
- `templates/bioactivity_predict.py`
- `templates/drugbank_lookup.py`
- `templates/protein_ligand_affinity.py`
- `templates/protein_ligand_benchmark.py`
- `templates/qsar_benchmark.py`
- `templates/virtual_screen.py`

Use these templates instead of rewriting the same chemistry scripts from scratch.

## Preferred Workflow

1. Identify the input type: inline SMILES, CSV/TSV, text list, XYZ, or inline atom string.
2. Run the smallest deterministic template first.
3. For predictive work, separate descriptive heuristics from supervised models.
4. Save structured outputs such as `.npy`, `.csv`, `.joblib`, or `.json`.
5. Benchmark supervised models with scaffold or external splits before treating them as useful.
6. Report the exact featurizer, basis set, method, model algorithm, label definition, split strategy, and whether convergence or training succeeded.
7. Call out whether a model is ligand-only or structure-aware.
8. State clearly whether the result is descriptive, predictive, or quantum-mechanical.

## DeepChem

Use `templates/deepchem_featurize.py` for:
- circular fingerprints
- MACCS keys
- Mol2Vec fingerprints
- quick dataset preparation for downstream ML

Quick start:

```bash
python3 templates/deepchem_featurize.py \
  --smiles "CCO" "c1ccccc1" \
  --featurizer circular \
  --output-prefix chem/deepchem/demo
```

CSV input example:

```bash
python3 templates/deepchem_featurize.py \
  --input ligands.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --featurizer maccs \
  --output-prefix chem/deepchem/ligands
```

Deliverables:
- `.npy` feature matrix
- `.summary.csv` with per-molecule stats
- `.json` metadata with featurizer and shape

If the user asks for actual DeepChem neural models, verify the required backend first. Do not assume TensorFlow or PyTorch models are available just because `deepchem` imports.

## RDKit

Use `templates/rdkit_descriptors.py` for:
- common molecular descriptors
- Lipinski and Veber rule flags
- quick ligand triage before docking or QM follow-up

Quick start:

```bash
python3 templates/rdkit_descriptors.py \
  --smiles "CCO" "c1ccccc1O" \
  --output chem/rdkit/descriptors.csv \
  --summary chem/rdkit/summary.json
```

CSV input example:

```bash
python3 templates/rdkit_descriptors.py \
  --input ligands.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --output chem/rdkit/ligands.csv \
  --summary chem/rdkit/ligands.json
```

Deliverables:
- descriptor CSV
- summary JSON
- explicit invalid-SMILES list when parsing fails

## ADMET

Use `templates/admet_screen.py` for:
- fast oral-drug-likeness triage
- Lipinski, Veber, and Egan filters
- BBB-likeness heuristics
- PAINS or BRENK structural alerts when RDKit filter catalogs are available
- simple ADMET prioritization before docking or QSAR

Quick start:

```bash
python3 templates/admet_screen.py \
  --smiles "CCO" "CC(=O)Oc1ccccc1C(=O)O" \
  --output chem/admet/screen.csv \
  --summary chem/admet/summary.json
```

CSV input example:

```bash
python3 templates/admet_screen.py \
  --input ligands.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --output chem/admet/ligands.csv \
  --summary chem/admet/ligands.json
```

Deliverables:
- per-ligand ADMET CSV with descriptors and pass or warn flags
- summary JSON with valid and invalid counts

Treat this as heuristic triage. It is not a clinically validated ADMET predictor.

## Assay Data

Use `templates/assay_data_prepare.py` for:
- normalizing ChEMBL exports into a compact `id, smiles, target` style table
- extracting BindingDB potency columns into a cleaner training dataset
- adapting MoleculeNet or generic CSV data before QSAR work
- optional numeric-to-class conversion for active or inactive labeling

Example:

```bash
python3 templates/assay_data_prepare.py \
  --input chembl_export.csv \
  --source chembl \
  --task regression \
  --convert-nm-to-pactivity \
  --output chem/data/chembl_normalized.csv \
  --summary chem/data/chembl_normalized.json
```

BindingDB classification example:

```bash
python3 templates/assay_data_prepare.py \
  --input bindingdb_hits.tsv \
  --source bindingdb \
  --task classification \
  --activity-threshold 1000 \
  --threshold-direction "<=" \
  --label-positive binder \
  --label-negative non_binder \
  --output chem/data/bindingdb_binary.csv \
  --summary chem/data/bindingdb_binary.json
```

Deliverables:
- normalized CSV ready for the downstream templates
- summary JSON with source detection, threshold policy, and invalid-row counts

Do not silently mix incompatible assays or units. If the export combines unrelated targets or endpoints, split it first.

## Structure Dataset Prep

Use `templates/pdbbind_prepare.py` for:
- normalizing PDBbind-style index files into `complex_path` or `receptor_path + ligand_path` tables
- merging extra metadata such as target family, protein id, or SMILES into the normalized output
- preparing benchmark inputs for `protein_ligand_affinity.py` or `protein_ligand_benchmark.py`

Example:

```bash
python3 templates/pdbbind_prepare.py \
  --root pdbbind/refined-set \
  --index pdbbind/index/INDEX_refined_data.2020 \
  --metadata pdbbind/pocket_groups.csv \
  --output chem/data/pdbbind_normalized.csv \
  --summary chem/data/pdbbind_normalized.json
```

Deliverables:
- normalized CSV with structure paths and affinity
- summary JSON with path coverage and invalid rows

## Benchmarking

Use `templates/qsar_benchmark.py` for:
- scaffold-split or random-split QSAR benchmarking
- baseline regression or classification sanity checks
- holdout prediction exports with optional ensemble uncertainty
- refitting a model bundle after benchmark validation

Example:

```bash
python3 templates/qsar_benchmark.py \
  --input chem/data/chembl_normalized.csv \
  --target-column target \
  --task regression \
  --split scaffold \
  --feature-backend rdkit-morgan \
  --algorithm rf \
  --include-descriptors \
  --metrics-output chem/benchmarks/affinity_metrics.json \
  --predictions-output chem/benchmarks/affinity_predictions.csv \
  --folds-output chem/benchmarks/affinity_folds.csv \
  --model-output chem/models/affinity_from_benchmark.joblib
```

Deliverables:
- benchmark metrics JSON
- holdout prediction CSV
- fold-level metrics CSV
- optional refit model bundle

Use scaffold split by default when chemical series leakage is a real risk.

## Binding Affinity

Use `templates/binding_affinity_predict.py` for:
- local ligand-only affinity regression from labeled SMILES tables
- quick QSAR baselines before docking or after docking hit expansion
- reusable model bundles that can score new ligand libraries

Training example:

```bash
python3 templates/binding_affinity_predict.py \
  --train affinity_train.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --target-column affinity \
  --feature-backend deepchem-circular \
  --algorithm et \
  --include-descriptors \
  --model-output chem/models/affinity.joblib \
  --metrics-output chem/models/affinity_metrics.json
```

Inference example:

```bash
python3 templates/binding_affinity_predict.py \
  --model-input chem/models/affinity.joblib \
  --predict screening_library.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --predictions-output chem/predictions/affinity.csv
```

Deliverables:
- `.joblib` model bundle
- metrics JSON with regression scores
- prediction CSV with per-ligand affinity estimates

Assumptions:
- this is ligand-only prediction from chemistry features
- labeled training data must already exist
- affinity direction must be reported explicitly if lower values are better in the source assay

## Protein-Ligand Affinity

Use `templates/protein_ligand_affinity.py` for:
- structure-aware affinity regression from receptor-ligand complexes
- feature extraction from `complex_path` or `receptor_path + ligand_path`
- docking follow-up when you want contact geometry, pocket composition, and atom-pair features instead of ligand-only fingerprints

Training example:

```bash
python3 templates/protein_ligand_affinity.py \
  --train structure_affinity_train.csv \
  --id-column id \
  --complex-path-column complex_path \
  --smiles-column smiles \
  --target-column affinity \
  --algorithm rf \
  --metrics-output chem/benchmarks/protein_affinity_metrics.json \
  --features-output chem/benchmarks/protein_affinity_features.csv \
  --model-output chem/models/protein_affinity.joblib
```

Prediction example on docking outputs:

```bash
python3 templates/protein_ligand_affinity.py \
  --model-input chem/models/protein_affinity.joblib \
  --predict docking/results/analysis/docking_summary.csv \
  --id-column ligand_slug \
  --complex-path-column complex_path \
  --predictions-output chem/predictions/protein_affinity.csv
```

Deliverables:
- structure feature CSV
- metrics JSON
- prediction CSV with optional uncertainty for ensemble models

Treat this as a structure-aware baseline. It is still limited by complex quality and docking pose quality.

## Structure Benchmarking

Use `templates/protein_ligand_benchmark.py` for:
- grouped or random holdout evaluation of structure-aware affinity models
- fold-level benchmarking on PDBbind-style normalized tables
- measuring the real boundary between near-target interpolation and cross-target generalization

Example:

```bash
python3 templates/protein_ligand_benchmark.py \
  --input chem/data/pdbbind_normalized.csv \
  --split group \
  --group-column target_group \
  --algorithm rf \
  --metrics-output chem/benchmarks/protein_affinity_metrics.json \
  --predictions-output chem/benchmarks/protein_affinity_predictions.csv \
  --folds-output chem/benchmarks/protein_affinity_folds.csv \
  --model-output chem/models/protein_affinity_benchmark.joblib
```

Deliverables:
- structure feature CSV
- metrics JSON
- holdout prediction CSV
- fold metrics CSV

Prefer group split when the benchmark should punish target-family leakage instead of only ligand-series leakage.

## DrugBank

Use `templates/drugbank_lookup.py` for:
- searching a local DrugBank CSV, TSV, JSON, or XML export by name, synonym, brand, or DrugBank accession
- querying the online DrugBank discovery API when API credentials are available
- exporting a matched drug as SMILES or generated SDF
- reading descriptive properties such as indication, mechanism, groups, identifiers, and text summaries

Example:

```bash
python3 templates/drugbank_lookup.py \
  --catalog drugbank_export.csv \
  --query imatinib \
  --output chem/drugbank/imatinib_hits.csv \
  --summary chem/drugbank/imatinib_summary.json \
  --top-hit-json chem/drugbank/imatinib.json \
  --sdf-output chem/drugbank/imatinib.sdf
```

Deliverables:
- hit table CSV
- summary JSON
- optional top-hit JSON and exported structure files

Treat this as licensed local-catalog search. Do not imply that DrugBank can be scraped anonymously at runtime.

Online example:

```bash
DRUGBANK_API_KEY=... \
python3 templates/drugbank_lookup.py \
  --mode online \
  --query imatinib \
  --summary chem/drugbank/imatinib_online_summary.json \
  --top-hit-json chem/drugbank/imatinib_online.json
```

Use `--api-token` or `DRUGBANK_API_TOKEN` when you need the token-based browser-compatible endpoint instead of the default API-key flow.

## Bioactivity

Use `templates/bioactivity_predict.py` for:
- active or inactive classification
- local regression for potency-like numeric bioactivity values
- baseline QSAR screening from labeled SMILES tables

Classification example:

```bash
python3 templates/bioactivity_predict.py \
  --train bioactivity_train.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --target-column active \
  --task classification \
  --feature-backend rdkit-morgan \
  --algorithm rf \
  --include-descriptors \
  --model-output chem/models/bioactivity.joblib \
  --metrics-output chem/models/bioactivity_metrics.json
```

Prediction example:

```bash
python3 templates/bioactivity_predict.py \
  --model-input chem/models/bioactivity.joblib \
  --predict screening_library.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --predictions-output chem/predictions/bioactivity.csv
```

Deliverables:
- classification or regression model bundle
- metrics JSON
- prediction CSV with label or probability outputs

State the training label definition in the report, for example `active`, `binder`, `pIC50`, or `IC50_nM`.

## Virtual Screening

Use `templates/virtual_screen.py` for:
- ranking a screening library after chemistry triage
- combining ADMET, bioactivity, binding-affinity, and docking scores
- reusing structure-aware affinity predictions exported from `protein_ligand_affinity.py`
- producing a sortable hit table for medicinal chemistry follow-up

Example:

```bash
python3 templates/virtual_screen.py \
  --input screening_library.csv \
  --smiles-column smiles \
  --id-column ligand_id \
  --admet-csv chem/admet/ligands.csv \
  --affinity-csv chem/predictions/protein_affinity.csv \
  --affinity-model chem/models/affinity.joblib \
  --bioactivity-model chem/models/bioactivity.joblib \
  --docking-csv docking/results/summary.csv \
  --docking-id-column ligand_id \
  --docking-score-column best_score \
  --output chem/screening/ranked.csv \
  --summary chem/screening/summary.json
```

Deliverables:
- ranked virtual-screening CSV with component scores
- summary JSON with top hit ids and enabled signal sources

Report the weights used for affinity, activity, ADMET, and docking. If only one signal is available, say so instead of presenting the rank as a multi-factor screen.

## PySCF

Use `templates/pyscf_single_point.py` for:
- RHF single-point energies
- UHF single-point energies
- RKS or UKS DFT single-point calculations
- small-molecule QM sanity checks for docked ligands or fragments

Quick start:

```bash
python3 templates/pyscf_single_point.py \
  --atom "O 0 0 0; H 0 0 0.96; H 0.92 0 -0.24" \
  --basis sto-3g \
  --method rhf \
  --output chem/pyscf/water_rhf.json
```

XYZ input example:

```bash
python3 templates/pyscf_single_point.py \
  --xyz ligand.xyz \
  --basis 6-31g* \
  --method rks \
  --xc b3lyp \
  --output chem/pyscf/ligand_b3lyp.json
```

Report at minimum:
- method
- basis
- charge
- spin
- converged or not
- total energy in Hartree

## Working Principles

- Treat DeepChem features as model inputs, not biological conclusions.
- Treat ADMET screening outputs as heuristic prioritization, not clinical safety claims.
- Treat affinity and bioactivity templates as local QSAR baselines, not pretrained benchmark models.
- Treat protein-ligand affinity from docked complexes as pose-conditional estimates, not experimental truth.
- Prefer benchmarked models over ad hoc train/test claims.
- Prefer scaffold-based validation when compounds cluster into close analog series.
- Treat PySCF single-point energies as computational estimates, not experimental measurements.
- Keep chemistry outputs in a dedicated subdirectory such as `./chem/`.
- Prefer JSON or CSV outputs over only printing stdout.
- When inputs come from docking, include the source pose or ligand file path in the report.

## Failure Modes

- `deepchem` missing: cannot featurize with the bundled template
- `pyscf` missing: cannot run QM calculations
- mixed assays or units: benchmark conclusions become invalid
- no labeled training table: cannot fit affinity or bioactivity models
- malformed complex, receptor, or ligand coordinates: structure-aware affinity extraction fails
- no local DrugBank export and no DrugBank API credentials: DrugBank search and structure export cannot run
- all labels in one class: classification metrics become misleading and screening value is limited
- malformed SMILES or XYZ: stop and report the bad record or file
- SCF not converged: return the failure explicitly instead of pretending the energy is final

## Related Skills

- For general bioinformatics, activate `bio-tools`.
- For public compound, regulatory, clinical-trial, or literature APIs, activate `pharma-db-tools`.
- For datamol, molfeat, PyTDC, or medicinal-chemistry rule screens, activate `pharma-ml-tools`.
- For docking pipelines and pose inspection, activate `docking-tools`.
