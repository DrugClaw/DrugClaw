---
name: docking-tools
description: Molecular docking workflow guide and reusable pipeline template for AutoDock Vina, Open Babel, and PyMOL.
source: drugclaw
updated_at: "2026-03-10"
---

# Docking Tools

Use this skill when the user asks to:
- dock a ligand, compound, or drug against a receptor
- estimate binding poses or affinities
- inspect a binding site or ligand contacts
- render docking poses or interaction figures
- batch-screen ligands and summarize docking rankings

DrugClaw does not ship a native docking engine module. This skill packages a reusable non-GUI docking workflow into a CLI template under `templates/`.

## Runtime Requirements

The workflow assumes the runtime provides:
- `obabel`
- `vina`
- `pymol`
- `pdbfixer` for receptor cleanup and protonation
- Python modules used by the fuller docking and downstream chemistry workflow: `openbabel`, `deepchem`, `pdbfixer`, `pyscf`, `rdkit`, `psutil`, `rsa`, `bs4`, `requests`, `pandas`, `matplotlib`, `seaborn`, `sklearn`, `Bio`

Check first:

```bash
which obabel vina pymol pdbfixer || true
vina --version || true
obabel -V || true
python3 - <<'PY'
mods = ["openbabel", "deepchem", "pdbfixer", "pyscf", "rdkit", "psutil", "rsa", "bs4", "requests", "pandas", "matplotlib", "seaborn", "sklearn", "Bio"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If these tools are missing, say so immediately. Prefer the unified science sandbox image documented in `docker/drug-sandbox.Dockerfile` and `docs/operations/science-runtime.md`.

## Preferred Workflow

Use the bundled template instead of rebuilding the pipeline ad hoc.

Bundled assets:
- `templates/docking_workflow.py`
- `templates/docking_manifest.example.json`
- `templates/README.md`

The template ports these usable desktop-tool capabilities into DrugClaw:
- ligand download from `PubChem`, `ChEMBL`, `ZINC`, `TCMSP`, local `DrugBank` exports, and the online DrugBank discovery API
- receptor download from `RCSB PDB`, `AlphaFold DB`
- SMILES and sequence-driven structure generation
- receptor preprocessing with `pdbfixer -> obabel`
- ligand preprocessing with 2D-to-3D generation, forcefield minimization, and biomolecule fallbacks
- automatic search-box inference from co-crystal ligands, active residues, or bounding boxes
- batch AutoDock Vina docking
- PDBQT-to-PDB complex assembly while preserving ligand coordinates
- CSV, heatmap, evaluation note, and paper-style markdown report generation
- optional PyMOL rendering for top hits
- optional heuristic ML rescoring when descriptors are available
- optional downstream DeepChem featurization or PySCF sanity checks outside the core docking pipeline
- optional chemistry post-processing with ADMET, ligand-only QSAR models, structure-aware affinity scoring, and virtual-screen reranking through `chem-tools`
- direct handoff from docked complexes into `chem-tools/templates/protein_ligand_affinity.py` for structure-aware affinity scoring

Scope boundary:
- port the computational workflow
- do not port the original GUI, installer wizard, or license/device-fingerprint logic

## Fast Start

From the skill directory or a copied template workspace:

```bash
python3 templates/docking_workflow.py init-manifest -o docking_manifest.json
python3 templates/docking_workflow.py doctor --manifest docking_manifest.json
python3 templates/docking_workflow.py run --manifest docking_manifest.json
```

`doctor` now fails on dependencies that the current manifest actually requires.
Use `--strict` when you also want optional plotting and chemistry extras audited.
If the manifest uses `drugbank` ligands or `chem_postprocess`, the sibling `chem-tools/templates` bundle must also be present; `doctor` now checks that explicitly.

Incremental execution:

```bash
python3 templates/docking_workflow.py fetch --manifest docking_manifest.json
python3 templates/docking_workflow.py prepare --manifest docking_manifest.json
python3 templates/docking_workflow.py box --manifest docking_manifest.json
python3 templates/docking_workflow.py dock --manifest docking_manifest.json
python3 templates/docking_workflow.py analyze --manifest docking_manifest.json
python3 templates/docking_workflow.py render --manifest docking_manifest.json --top-n 5
```

## Manifest Guidance

Use `templates/docking_manifest.example.json` as the base.

Supported input styles include:
- ligand `source`: `smiles`, `local`, `pubchem`, `chembl`, `zinc`, `tcmsp`, `drugbank`, `auto`
- receptor `source`: `local`, `pdb`, `alphafold`, `peptide`, `protein`, `protein_sequence`, `nucleic`, `nucleic_sequence`, `auto`

For `drugbank` ligands, set either `settings.drugbank_catalog` to a local DrugBank CSV, TSV, JSON, or XML export, or configure `settings.drugbank_api_key` / `settings.drugbank_api_token` for online lookup. The fetch stage will save both the exported structure and a per-drug JSON property file under `inputs/ligands/`.

Manual box override example:

```json
{
  "box": {
    "mode": "manual",
    "center": [10.5, -3.2, 22.1],
    "size": [24, 24, 24]
  }
}
```

If `box` is omitted, the template tries:
1. co-crystal ligand coordinates
2. active-site residue coordinates
3. whole-structure bounding box

Optional chemistry post-processing block:

```json
{
  "chem_postprocess": {
    "enabled": true,
    "run_admet": true,
    "run_virtual_screen": true,
    "affinity_model": "./models/affinity.joblib",
    "structure_affinity_model": "./models/protein_affinity.joblib",
    "bioactivity_model": "./models/bioactivity.joblib",
    "affinity_direction": "higher-better",
    "top_n": 25,
    "weights": {
      "affinity": 0.35,
      "activity": 0.35,
      "admet": 0.20,
      "docking": 0.10
    }
  }
}
```

When this block is enabled, `analyze` also writes ligand-level chemistry outputs under `results/analysis/chem/`.

## Working Principles

- Create a dedicated working directory such as `./docking/`.
- Keep the manifest, generated configs, logs, and renders together for reproducibility.
- Tell the user whether the search box came from prior knowledge, co-crystal geometry, active residues, or a geometric fallback.
- Treat docking scores as ranking heuristics, not experimental truth.
- When the pipeline falls back from protein-specific cleanup to generic conversion, report that explicitly.

## Output Layout

The template writes:
- `inputs/`
- `prepared/`
- `configs/`
- `results/docking/`
- `results/complexes/`
- `results/renders/`
- `results/analysis/`
- `metadata/session.json`
- `metadata/history.jsonl`

Key deliverables:
- `results/analysis/docking_summary.csv`
- `results/analysis/binding_energy_matrix.csv`
- `results/analysis/ligand_best_scores.csv`
- `results/analysis/binding_energy_heatmap.png`
- `results/analysis/evaluation.md`
- `results/analysis/paper_report.md`
- `results/analysis/ml_scores.csv` when the ML stage is available
- `results/analysis/chem/` when chemistry post-processing is enabled
- `inputs/ligands/*.drugbank.json` when DrugBank-backed ligands are used

## Failure Modes

- `obabel` missing: cannot prepare receptor or ligand
- `vina` missing: cannot score poses
- `pdbfixer` missing: protein receptor cleanup falls back poorly; say so explicitly
- no `settings.drugbank_catalog` and no `settings.drugbank_api_key` / `settings.drugbank_api_token`: DrugBank ligands cannot be resolved
- no plausible box definition: ask for catalytic residues, a co-crystal ligand, or approximate binding-site coordinates
- PyMOL missing: still return text results plus the generated `.pml` scripts
- chemistry models missing: keep docking outputs and skip the optional reranking stage explicitly
- structure-affinity model missing: keep docking outputs, ligand-only chemistry outputs, and skip structure-aware scoring explicitly

## Recommended Response Pattern

```text
I used the bundled docking workflow template to prepare the receptor and ligand, generate the docking box, run AutoDock Vina, and save the artifacts in `docking/`.
The top-ranked pose reports `-8.1 kcal/mol` in `results/analysis/docking_summary.csv`.
I also generated `evaluation.md`, `paper_report.md`, and a PyMOL render script for the top hits.
This is a docking ranking result, not a measured binding affinity; the main uncertainty is the search-box definition.
```
