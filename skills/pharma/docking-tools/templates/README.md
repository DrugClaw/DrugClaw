# Docking Workflow Template

`docking_workflow.py` packages DrugClaw's reusable non-GUI docking workflow into a CLI.

## Included workflow stages

- remote fetch for receptors and ligands
- SMILES and sequence input generation
- receptor preprocessing with `pdbfixer` and `obabel`
- ligand preprocessing with 2D-to-3D generation, forcefield minimization, and biomolecule fallbacks
- automatic docking-box generation
- AutoDock Vina batch docking
- PDBQT-to-PDB complex assembly while preserving ligand coordinates
- heatmap, CSV, evaluation note, and paper-style markdown report generation
- optional PyMOL rendering for top hits
- optional heuristic ML rescoring when RDKit and scikit-learn are available
- optional chemistry post-processing that runs ADMET, ligand-only QSAR models, structure-aware affinity scoring, and virtual-screen reranking
- optional `drugbank` ligand fetch from a local DrugBank export or the online DrugBank discovery API

The broader bio/docking runtime can also expose:

- `deepchem` for post-docking featurization and lightweight molecular ML
- `pyscf` for small-molecule QM follow-up calculations

## Quick start

```bash
python3 templates/docking_workflow.py init-manifest -o docking_manifest.json
python3 templates/docking_workflow.py doctor --manifest docking_manifest.json
python3 templates/docking_workflow.py run --manifest docking_manifest.json
```

`doctor` validates the dependencies required by the current manifest.
Add `--strict` to also audit optional plotting and chemistry extras.
If you copied only `docking_workflow.py`, manifests that use `drugbank` or `chem_postprocess` also need the sibling `chem-tools/templates` scripts present next to the copied workflow.

## Typical incremental usage

```bash
python3 templates/docking_workflow.py fetch --manifest docking_manifest.json
python3 templates/docking_workflow.py prepare --manifest docking_manifest.json
python3 templates/docking_workflow.py box --manifest docking_manifest.json
python3 templates/docking_workflow.py dock --manifest docking_manifest.json
python3 templates/docking_workflow.py analyze --manifest docking_manifest.json
python3 templates/docking_workflow.py render --manifest docking_manifest.json --top-n 5
```

## Manifest notes

- `workspace` is resolved relative to the manifest file when it is not absolute.
- Local `path` values are also resolved relative to the manifest file.
- Receptor `box` can be set manually:

```json
{
  "box": {
    "mode": "manual",
    "center": [10.5, -3.2, 22.1],
    "size": [24, 24, 24]
  }
}
```

- If `box` is omitted, the script tries `co-crystal ligand -> active residues -> whole-structure bounding box`.
- `docking_pairs` is optional; when omitted, the script docks every ligand against every receptor.
- `chem_postprocess` is optional; when enabled, `analyze` also builds ligand-level chemistry outputs in `results/analysis/chem/`.
- set `chem_postprocess.structure_affinity_model` when you want `protein_ligand_affinity.py` to score the best docked complex per ligand.
- ligand `source` also supports `drugbank`; point `settings.drugbank_catalog` at a local CSV/TSV/JSON/XML export or set `settings.drugbank_api_key` / `settings.drugbank_api_token` for online lookup. The fetch stage will save both `*.sdf` and `*.drugbank.json`.

Chemistry post-processing example:

```json
{
  "chem_postprocess": {
    "enabled": true,
    "run_admet": true,
    "run_virtual_screen": true,
    "affinity_model": "./models/affinity.joblib",
    "structure_affinity_model": "./models/protein_affinity.joblib",
    "bioactivity_model": "./models/bioactivity.joblib",
    "weights": {
      "affinity": 0.35,
      "activity": 0.35,
      "admet": 0.20,
      "docking": 0.10
    }
  }
}
```

## Output layout

```text
<workspace>/
  inputs/
  prepared/
  configs/
  results/
    docking/
    complexes/
    renders/
    analysis/
  metadata/
```

Main outputs:

- `results/analysis/docking_summary.csv`
- `results/analysis/binding_energy_matrix.csv`
- `results/analysis/ligand_best_scores.csv`
- `results/analysis/binding_energy_heatmap.png`
- `results/analysis/evaluation.md`
- `results/analysis/paper_report.md`
- `results/analysis/ml_scores.csv` when the heuristic ML step is available
- `results/analysis/chem/` when chemistry post-processing is enabled
- `results/analysis/chem/structure_affinity_predictions.csv` when a structure-aware affinity model is configured

## Scope boundary

This template ports the computational workflow. It does not port the original desktop GUI, installer wizard, or licensing/device-fingerprint logic.
