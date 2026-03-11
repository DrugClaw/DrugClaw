# Science Runtime

This project now bundles a broader scientific, pharma, medical, genomics, and research skill layer for DrugClaw across `skills/science`, `skills/pharma`, `skills/medical`, `skills/genomics`, and `skills/research`:

- `bio-tools`
- `bio-db-tools`
- `bayesian-optimization-tools`
- `omics-tools`
- `grn-tools`
- `target-intelligence-tools`
- `variant-analysis-tools`
- `pharma-db-tools`
- `chem-tools`
- `pharma-ml-tools`
- `literature-review-tools`
- `medical-data-tools`
- `clinical-research-tools`
- `medical-qms-tools`
- `stat-modeling-tools`
- `survival-analysis-tools`
- `scientific-visualization-tools`
- `scientific-workflow-tools`
- `docking-tools`

Those skills provide workflow instructions, but the actual command availability still depends on the runtime that executes `bash`.

## Sandbox Design

DrugClaw now spans biology, chemistry, medical-research data, literature synthesis, and docking. A split such as `bio-sandbox`, `chem-sandbox`, and `med-sandbox` sounds tidy, but the current dependency graph does not justify it:

- `chem-tools`, `pharma-ml-tools`, and `docking-tools` share RDKit, DeepChem, and pandas-heavy Python stacks
- `medical-data-tools`, `omics-tools`, and `clinical-research-tools` all depend on the same data-science base
- routing users to three partially overlapping images would create more operator confusion than real isolation value

The current design is therefore:

- `drug-sandbox`: the canonical unified runtime for science and docking skills
- `drug-sandbox-docking`: a legacy compatibility tag only, for older configs and scripts that still expect the old name

If the project later adds GPU-heavy pose models or clinical imaging stacks with conflicting native dependencies, a second or third image can still make sense. Right now, one unified science+docking image is the cleaner design.

## Recommended Setup

Build the canonical science+docking sandbox image:

```sh
docker build -f docker/drug-sandbox.Dockerfile -t drugclaw-drug-sandbox:latest .
```

The Dockerfiles use version-constrained requirements files under `docker/requirements-*.txt` so rebuilds do not float across unrelated Python package releases.

Then point DrugClaw at it:

```yaml
sandbox:
  mode: "all"
  backend: "auto"
  image: "drugclaw-drug-sandbox:latest"
  security_profile: "standard"
  no_network: false
  require_runtime: true
```

Why `standard`:
- some scientific tools expect normal container capabilities
- headless rendering and package behavior are less fragile than `hardened`

Why `no_network: false`:
- remote BLAST, PubMed, PDB downloads, and package-backed APIs may need outbound network access

## Included Toolchain

The optional image provides the bundled scientific and docking stack used by these skills:

- CLI tools: `blastn`, `blastp`, `samtools`, `bedtools`, `bwa`, `minimap2`, `fastqc`, `seqtk`, `fastp`, `bcftools`, `seqkit`, `pigz`, `tabix`, `sra-toolkit`, `salmon`, `kallisto`, `obabel`, `vina`
- Python libraries: `biopython`, `cellxgene-census`, `datamol`, `deepchem`, `joblib`, `medchem`, `molfeat`, `pandas`, `numpy`, `plotly`, `pyopenms`, `PyTDC`, `pyscf`, `scikit-bio`, `scipy`, `matplotlib`, `seaborn`, `scikit-learn`, `rdkit-pypi`, `pydeseq2`, `scanpy`, `anndata`, `arboreto`, `dask`, `distributed`, `pydicom`, `neurokit2`, `pysam`, `requests`, `statsmodels`, `multiqc`, `beautifulsoup4`, `openmm`, `pdbfixer`, `pillow`, `psutil`, `rsa`
- Structure rendering: `pymol`

## Docking Compatibility

`docking-tools` is included in the unified image by default. The legacy
`drugclaw-drug-sandbox-docking:latest` name is now just a compatibility tag
that can point at the same image if older configs still reference it.

The bundled `docking-tools` skill now ships a reusable workflow template:

- `skills/pharma/docking-tools/templates/docking_workflow.py`
- `skills/pharma/docking-tools/templates/docking_manifest.example.json`
- `skills/pharma/docking-tools/templates/README.md`

Typical usage inside the repo or inside an installed skill copy:

```bash
python3 templates/docking_workflow.py init-manifest -o docking_manifest.json
python3 templates/docking_workflow.py doctor --manifest docking_manifest.json
python3 templates/docking_workflow.py run --manifest docking_manifest.json
```

That template ports the reusable docking stages into DrugClaw:
remote fetch, receptor and ligand preprocessing, automatic box generation, Vina docking,
complex assembly, CSV and heatmap outputs, markdown reports, optional chemistry post-processing, structure-aware affinity scoring, and optional PyMOL renders.

The base science image also now includes:

- `deepchem` for molecular featurization and lightweight chemistry ML workflows
- `pyscf` for small-molecule HF/DFT calculations and QM sanity checks

Bundled helper scripts for those libraries live under:

- `skills/science/bio-db-tools/templates/bio_db_lookup.py`
- `skills/research/bayesian-optimization-tools/templates/bayesian_optimize.py`
- `skills/science/omics-tools/templates/single_cell_profile.py`
- `skills/science/omics-tools/templates/pysam_region_profile.py`
- `skills/science/omics-tools/templates/mzml_summary.py`
- `skills/genomics/grn-tools/templates/arboreto_grn.py`
- `skills/research/target-intelligence-tools/templates/target_dossier.py`
- `skills/genomics/variant-analysis-tools/templates/variant_report.py`
- `skills/pharma/pharma-db-tools/templates/pharma_db_lookup.py`
- `skills/pharma/chem-tools/templates/deepchem_featurize.py`
- `skills/pharma/chem-tools/templates/pyscf_single_point.py`
- `skills/pharma/chem-tools/templates/rdkit_descriptors.py`
- `skills/pharma/chem-tools/templates/admet_screen.py`
- `skills/pharma/chem-tools/templates/assay_data_prepare.py`
- `skills/pharma/chem-tools/templates/pdbbind_prepare.py`
- `skills/pharma/chem-tools/templates/binding_affinity_predict.py`
- `skills/pharma/chem-tools/templates/bioactivity_predict.py`
- `skills/pharma/chem-tools/templates/drugbank_lookup.py`
- `skills/pharma/chem-tools/templates/protein_ligand_affinity.py`
- `skills/pharma/chem-tools/templates/protein_ligand_benchmark.py`
- `skills/pharma/chem-tools/templates/qsar_benchmark.py`
- `skills/pharma/chem-tools/templates/virtual_screen.py`
- `skills/pharma/pharma-ml-tools/templates/datamol_library_profile.py`
- `skills/pharma/pharma-ml-tools/templates/molfeat_featurize.py`
- `skills/pharma/pharma-ml-tools/templates/pytdc_dataset_fetch.py`
- `skills/pharma/pharma-ml-tools/templates/medchem_screen.py`
- `skills/science/literature-review-tools/templates/citation_table_normalize.py`
- `skills/science/literature-review-tools/templates/evidence_matrix.py`
- `skills/medical/medical-data-tools/templates/dicom_inspect.py`
- `skills/medical/medical-data-tools/templates/neuro_signal_analyze.py`
- `skills/medical/medical-data-tools/templates/clinical_cohort_profile.py`
- `skills/science/stat-modeling-tools/templates/stat_test_report.py`
- `skills/science/stat-modeling-tools/templates/statsmodels_regression.py`
- `skills/science/survival-analysis-tools/templates/survival_analysis.py`
- `skills/science/scientific-visualization-tools/templates/publication_plot.py`
- `skills/science/scientific-visualization-tools/templates/interactive_plot.py`
- `skills/science/scientific-workflow-tools/templates/reproducibility_checklist.py`

Those chemistry templates cover:

- descriptor calculation and rule-based ligand triage
- assay table normalization for ChEMBL, BindingDB, MoleculeNet, and generic CSV exports
- PDBbind-style structure dataset normalization for benchmark-ready CSV tables
- heuristic ADMET screening
- DrugBank local-export or online discovery lookup, structure export, and descriptive property summaries
- ligand-only binding-affinity prediction from labeled SMILES
- structure-aware protein-ligand affinity prediction from complexes or receptor-ligand coordinate pairs
- grouped or random benchmark runs for structure-aware affinity models
- ligand-only bioactivity classification or regression from labeled SMILES
- scaffold or random split QSAR benchmarking with optional uncertainty
- virtual screening that combines ADMET, QSAR, and docking outputs into one ranked table

The docking workflow also supports ligand `source: "drugbank"` when either `settings.drugbank_catalog` points at a local DrugBank CSV/TSV/JSON/XML export or `settings.drugbank_api_key` / `settings.drugbank_api_token` is configured for the online discovery API. That mode writes `inputs/ligands/*.drugbank.json` alongside the exported ligand structure.

These are reusable local pipelines built on RDKit, DeepChem features, and scikit-learn style estimators. They are not bundled pretrained foundation models.

The bundled `bio-db-tools` skill adds API-backed lookup templates for:

- UniProt, RCSB PDB, and AlphaFold DB
- ClinVar, dbSNP, gnomAD, and Ensembl
- GEO
- InterPro
- KEGG and Reactome
- OpenTargets and STRING

The bundled `omics-tools` skill adds local-data profiling templates for:

- AnnData and single-cell dataset triage
- BAM or CRAM region-count inspection with pysam
- mzML run inventory for pyOpenMS-based workflows

The bundled `grn-tools` skill adds network-inference templates for:

- Arboreto-based GRNBoost2 or GENIE3 runs
- optional transcription-factor constrained inference
- ranked TF-target edge export from expression matrices

The bundled `variant-analysis-tools` skill adds local callset templates for:

- VCF or BCF summarization with VAF, depth, PASS, and consequence filters
- SNV, indel, and SV table export before downstream annotation

The bundled `target-intelligence-tools` skill adds integrated dossier templates for:

- target identity, disease evidence, and known-drug snapshots
- interaction-partner and pathway summaries
- ClinVar count and gnomAD constraint context in one markdown brief

The bundled `pharma-db-tools` skill adds API-backed lookup templates for:

- PubChem compound records and molecular properties
- ChEMBL molecules, targets, and activity rows
- BindingDB measured affinity lookup from public service calls or local TSV exports
- openFDA labels, adverse events, NDC records, recalls, approvals, and shortages
- ClinicalTrials.gov study search and NCT record retrieval
- OpenAlex literature, author, and institution work lookup

The bundled `pharma-ml-tools` skill adds chemistry-ML preparation templates for:

- datamol-backed library standardization and scaffold profiling
- molfeat feature export for QSAR or ranking workflows
- PyTDC dataset fetch and split export
- medchem rule and alert screening

The bundled `medical-data-tools` skill adds local-data templates for:

- DICOM metadata inspection and basic de-identification copies
- ECG, PPG, EDA, RSP, and EMG feature extraction with NeuroKit2
- cohort-table profiling for clinical research datasets

The bundled `stat-modeling-tools` skill adds reusable statistics templates for:

- common hypothesis tests with machine-readable outputs
- OLS, logistic, and Poisson regression with statsmodels

The bundled `survival-analysis-tools` skill adds time-to-event templates for:

- Kaplan-Meier summaries and plots
- log-rank comparison for simple group analyses
- Cox proportional hazards baselines with hazard-ratio export

The bundled `scientific-visualization-tools` skill adds figure templates for:

- static scientific plots with seaborn or matplotlib
- interactive Plotly charts for exploratory analysis

The bundled `literature-review-tools` skill adds local workflow templates for:

- citation-table normalization and lightweight BibTeX export
- evidence-matrix assembly for review writing and gap mapping

The bundled `scientific-workflow-tools` skill adds planning templates for:

- reproducibility checklists across general, omics, ML, and clinical-research profiles

The bundled `bayesian-optimization-tools` skill adds experiment-suggestion templates for:

- Gaussian-process surrogate fitting over bounded numeric parameters
- ranked next-step proposals for assay, reaction, or tuning campaigns

The image is intentionally broader than a minimal Vina image because the docking workflow shares chemistry and reporting dependencies with the rest of the science stack.

## Verification

After startup, test through the agent or directly in the sandbox with:

```bash
which python3 blastn samtools bwa minimap2 fastqc seqtk pymol
python3 - <<'PY'
import Bio, arboreto, datamol, deepchem, medchem, pandas, matplotlib, plotly, scanpy, pysam, pyscf, statsmodels
print("python stack ok")
PY
```

If a skill is active but a tool is missing at execution time, the agent should:

1. say which binary or Python module is unavailable
2. avoid pretending the analysis ran
3. suggest switching to the `drug-sandbox` image or installing the missing dependency locally

For the docking image, use the stronger smoke test:

```bash
which vina obabel pymol
python3 - <<'PY'
mods = ["openbabel", "deepchem", "pdbfixer", "pyscf", "rdkit", "psutil", "rsa", "bs4"]
for name in mods:
    __import__(name)
print("docking python stack ok")
PY
```
