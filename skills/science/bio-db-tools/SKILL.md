---
name: bio-db-tools
description: Query public biology databases and APIs including UniProt, RCSB PDB, AlphaFold DB, ClinVar, dbSNP, gnomAD, Ensembl, GEO, InterPro, KEGG, OpenTargets, Reactome, and STRING. Use when the user asks to look up protein annotations, structures, variants, population frequencies, pathway knowledge, public datasets, interaction networks, or disease-target evidence.
source: drugclaw
updated_at: "2026-03-10"
---

# Bio DB Tools

Use this skill when the user asks to search or fetch data from public biology knowledge bases rather than analyze local files.

Typical triggers:
- protein function, accession, annotation, sequence metadata, domain architecture
- experimental PDB structures or AlphaFold models
- ClinVar pathogenicity or variant significance
- dbSNP rsIDs or gnomAD population-frequency / constraint lookups
- Ensembl gene coordinates, transcripts, or rsIDs
- GEO datasets, pathway databases, or interaction networks
- drug target and disease association evidence

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

- `templates/bio_db_lookup.py`

Supported sources:
- `uniprot`
- `pdb`
- `alphafold`
- `clinvar`
- `dbsnp`
- `gnomad`
- `ensembl`
- `geo`
- `interpro`
- `kegg`
- `opentargets`
- `reactome`
- `stringdb`

## Quick Start

```bash
python3 templates/bio_db_lookup.py uniprot \
  --query TP53 \
  --organism-id 9606 \
  --output bio/uniprot_tp53.csv \
  --summary bio/uniprot_tp53.json
```

```bash
python3 templates/bio_db_lookup.py pdb \
  --query "EGFR kinase inhibitor" \
  --limit 5 \
  --output bio/pdb_egfr.csv \
  --summary bio/pdb_egfr.json
```

```bash
python3 templates/bio_db_lookup.py clinvar \
  --query 'BRCA1[gene] AND clinsig_pathogenic[prop]' \
  --output bio/clinvar_brca1.csv \
  --summary bio/clinvar_brca1.json
```

```bash
python3 templates/bio_db_lookup.py gnomad \
  --mode gene-constraint \
  --gene-symbol BRCA1 \
  --output bio/gnomad_brca1.csv \
  --summary bio/gnomad_brca1.json
```

```bash
python3 templates/bio_db_lookup.py reactome \
  --mode enrichment \
  --gene BRCA1 --gene BRCA2 --gene TP53 --gene ATM \
  --output bio/reactome_dna_repair.csv \
  --summary bio/reactome_dna_repair.json
```

## Working Rules

1. Save both a machine-readable result file and a short summary JSON.
2. Report the exact database, query string, species, and any filters used.
3. Prefer exact identifiers when available: UniProt accession, PDB ID, Ensembl ID, rsID, ClinVar query, Reactome stable ID.
4. Return direct links for the user whenever the database exposes stable pages.
5. Distinguish clearly between:
   - search hits
   - record detail
   - enrichment or network evidence
6. If the remote API returns nothing, say that explicitly instead of inferring a biological conclusion.
7. Treat these sources as lookup surfaces, not experimental validation.

## Common Patterns

### Protein annotation

```bash
python3 templates/bio_db_lookup.py uniprot \
  --accession P04637 \
  --output bio/uniprot_p04637.csv \
  --summary bio/uniprot_p04637.json
```

### Experimental structure lookup

```bash
python3 templates/bio_db_lookup.py pdb \
  --pdb-id 6LU7 \
  --output bio/pdb_6lu7.csv \
  --summary bio/pdb_6lu7.json
```

### AlphaFold model metadata and download

```bash
python3 templates/bio_db_lookup.py alphafold \
  --uniprot-id P04637 \
  --download bio/AF-P04637-F1-model.pdb \
  --output bio/alphafold_tp53.csv \
  --summary bio/alphafold_tp53.json
```

### dbSNP record lookup

```bash
python3 templates/bio_db_lookup.py dbsnp \
  --rsid rs429358 \
  --output bio/dbsnp_rs429358.csv \
  --summary bio/dbsnp_rs429358.json
```

### Pathway and target evidence

```bash
python3 templates/bio_db_lookup.py opentargets \
  --mode disease-targets \
  --id EFO_0000305 \
  --limit 10 \
  --output bio/opentargets_breast_cancer.csv \
  --summary bio/opentargets_breast_cancer.json
```

```bash
python3 templates/bio_db_lookup.py stringdb \
  --mode network \
  --gene BRCA1 --gene BRCA2 --gene TP53 \
  --species 9606 \
  --output bio/string_brca_network.csv \
  --summary bio/string_brca_network.json
```

## Output Expectations

Good answers should mention:
- which API or database was queried
- the exact identifier or text query
- how many hits were returned
- the key IDs, names, scores, frequencies, constraint metrics, or annotations
- the saved output paths
- any rate-limit, network, or schema caveats

## Related Skills

For local sequence analysis, QC, plotting, or PubMed-style literature work, activate `bio-tools`.
For single-cell, BAM or mzML dataset triage, activate `omics-tools`.
For local VCF, SNV, indel, or SV summarization, activate `variant-analysis-tools`.
For integrated target briefs across disease, drug, pathway, and interaction evidence, activate `target-intelligence-tools`.
For public compound, regulatory, clinical-trial, or literature APIs such as PubChem, ChEMBL, openFDA, ClinicalTrials.gov, or OpenAlex, activate `pharma-db-tools`.
For docking and structure preparation, activate `docking-tools`.
For ligand properties, ADMET, DrugBank, or chemistry ML, activate `chem-tools`.
