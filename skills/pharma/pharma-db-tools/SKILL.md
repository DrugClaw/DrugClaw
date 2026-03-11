---
name: pharma-db-tools
description: Query public drug-discovery and translational-research databases including PubChem, ChEMBL, BindingDB, openFDA, ClinicalTrials.gov, and OpenAlex. Use when the user asks to look up compounds, measured binding affinities, regulatory labels or adverse events, clinical trials, or drug-discovery literature from public APIs and curated exports.
source: drugclaw
updated_at: "2026-03-11"
---

# Pharma DB Tools

Use this skill when the user asks for public drug-discovery database lookups rather than local cheminformatics analysis.

Typical triggers:
- compound lookup by name, CID, SMILES, or ChEMBL id
- public bioactivity or target-association lookup from ChEMBL
- measured drug-target affinity lookup from BindingDB by UniProt, compound, or local TSV export
- FDA labeling, adverse-event, NDC, approval, recall, or shortage data
- ClinicalTrials.gov study search, status review, or NCT lookup
- OpenAlex literature retrieval for drug, target, modality, or institution queries

## Environment Check

The bundled template uses Python plus HTTP APIs. Check first.

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

If outbound network access is blocked, say so explicitly before claiming the lookup ran.

## Bundled Asset

Use the reusable template instead of rewriting API snippets every time:

- `templates/pharma_db_lookup.py`

Supported sources:
- `pubchem`
- `chembl`
- `bindingdb`
- `openfda`
- `clinicaltrials`
- `openalex`

## Quick Start

```bash
python3 templates/pharma_db_lookup.py pubchem \
  --query imatinib \
  --output pharma/pubchem_imatinib.csv \
  --summary pharma/pubchem_imatinib.json
```

```bash
python3 templates/pharma_db_lookup.py chembl \
  --mode molecule \
  --chembl-id CHEMBL941 \
  --output pharma/chembl_imatinib.csv \
  --summary pharma/chembl_imatinib.json
```

```bash
python3 templates/pharma_db_lookup.py bindingdb \
  --tsv BindingDB_All.tsv \
  --uniprot-id P00519 \
  --affinity-type Ki \
  --max-nm 1000 \
  --output pharma/bindingdb_abl1.csv \
  --summary pharma/bindingdb_abl1.json
```

```bash
python3 templates/pharma_db_lookup.py openfda \
  --endpoint label \
  --query imatinib \
  --output pharma/fda_imatinib_label.csv \
  --summary pharma/fda_imatinib_label.json
```

```bash
python3 templates/pharma_db_lookup.py clinicaltrials \
  --condition "non-small cell lung cancer" \
  --intervention osimertinib \
  --status RECRUITING \
  --output pharma/osimertinib_trials.csv \
  --summary pharma/osimertinib_trials.json
```

```bash
python3 templates/pharma_db_lookup.py openalex \
  --query "KRAS G12C inhibitor resistance" \
  --limit 20 \
  --output pharma/openalex_kras_g12c.csv \
  --summary pharma/openalex_kras_g12c.json
```

## Working Rules

1. Save both a machine-readable result file and a summary JSON.
2. Report the exact database, mode, identifier, filters, and endpoint used.
3. Prefer exact identifiers when available: PubChem CID, ChEMBL id, NCT id, DOI.
4. Return direct stable links when the upstream database exposes them.
5. Distinguish clearly between compound metadata, activity measurements, regulatory evidence, clinical-study records, and literature hits.
6. If the API returns no hits, say that explicitly instead of inferring a scientific conclusion.
7. Treat these sources as evidence surfaces for prioritization and review, not as experimental proof.

## Common Patterns

### PubChem compound lookup by CID

```bash
python3 templates/pharma_db_lookup.py pubchem \
  --cid 5291 \
  --output pharma/pubchem_5291.csv \
  --summary pharma/pubchem_5291.json
```

### ChEMBL activity rows for a target

```bash
python3 templates/pharma_db_lookup.py chembl \
  --mode activity \
  --target-id CHEMBL203 \
  --standard-type IC50 \
  --limit 25 \
  --output pharma/egfr_ic50.csv \
  --summary pharma/egfr_ic50.json
```

### BindingDB measured affinities from a local export

```bash
python3 templates/pharma_db_lookup.py bindingdb \
  --tsv BindingDB_All.tsv \
  --compound-name imatinib \
  --affinity-type Ki \
  --limit 25 \
  --output pharma/imatinib_bindingdb.csv \
  --summary pharma/imatinib_bindingdb.json
```

### openFDA adverse-event aggregation

```bash
python3 templates/pharma_db_lookup.py openfda \
  --endpoint event \
  --query pembrolizumab \
  --output pharma/pembro_events.csv \
  --summary pharma/pembro_events.json
```

### ClinicalTrials.gov study detail

```bash
python3 templates/pharma_db_lookup.py clinicaltrials \
  --nct-id NCT04280705 \
  --output pharma/nct04280705.csv \
  --summary pharma/nct04280705.json
```

### OpenAlex author- or institution-scoped literature

```bash
python3 templates/pharma_db_lookup.py openalex \
  --author "Jennifer Doudna" \
  --limit 20 \
  --output pharma/doudna_works.csv \
  --summary pharma/doudna_works.json
```

## Output Expectations

Good answers should mention:
- which database and endpoint were queried
- the exact identifier or text query
- how many hits were returned
- the key IDs, names, phases, activities, warnings, affinity values, or citation counts
- the saved output paths
- any rate-limit, schema, or network caveats

## Related Skills

For UniProt, PDB, AlphaFold, ClinVar, Ensembl, GEO, KEGG, Reactome, STRING, or OpenTargets, activate `bio-db-tools`.
For DrugBank, ADMET, QSAR, descriptors, or structure-aware affinity work, activate `chem-tools`.
For datamol, molfeat, PyTDC, or medchem-style library workflows, activate `pharma-ml-tools`.
For docking, receptor preparation, or virtual screening execution, activate `docking-tools`.
