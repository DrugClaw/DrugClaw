---
name: bio-tools
description: Bioinformatics workflow guide for sequence analysis, QC, plotting, structure rendering, and literature search.
source: drugclaw
updated_at: "2026-03-10"
---

# Bio Tools

Use this skill for bioinformatics, genomics, transcriptomics, structural biology, or general biological data-analysis requests.

This skill focuses on DrugClaw's reproducible bioinformatics workflow pattern:
- Run commands with `bash`
- Write reproducible scripts with `write_file` or `edit_file`
- Inspect outputs with `read_file`
- Use `web_search` / `web_fetch` for literature and database lookups

## Environment Check

Do not assume the runtime already has the biology stack. Check first.

```bash
which python3 blastn blastp samtools bedtools bwa minimap2 fastqc seqtk pymol || true
python3 - <<'PY'
mods = ["Bio", "pandas", "numpy", "matplotlib", "pysam", "seaborn", "sklearn"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If key tools are missing, say so explicitly and recommend the optional `drug-sandbox` image documented in `docs/operations/science-runtime.md`.

## Working Style

- Start by inventorying files and formats in the current chat working directory.
- State the exact command, parameters, and tool versions used.
- Save outputs as files in the working directory and mention their paths in the reply.
- Prefer reproducible scripts over one-off interactive commands for multi-step analysis.
- Flag quality issues, contamination risk, reference mismatch, and missing metadata.
- End with concrete next steps, not just raw output.

## Common Workflow

1. Inspect available inputs.
2. Identify data type: FASTA, FASTQ, BAM, BED, CSV/TSV, PDB, SMILES, etc.
3. Check tool availability.
4. Run the smallest validating command first.
5. Save primary outputs and a short README or command log when analysis is non-trivial.
6. Summarize findings with caveats and suggested follow-ups.

## File Triage

```bash
pwd
find . -maxdepth 3 -type f | sort
file sample.fastq.gz
gzip -dc sample.fastq.gz | head
```

Useful quick checks:

```bash
samtools --version | head -n 1
blastn -version
fastqc --version
python3 --version
```

## Sequence Search

```bash
# Nucleotide BLAST against a local FASTA database
blastn -query query.fa -subject reference.fa -outfmt 6 -evalue 1e-5 > blast.tsv

# Protein BLAST
blastp -query protein.fa -subject reference_proteins.fa -outfmt 6 > blastp.tsv

# Translate nucleotide query against proteins
blastx -query transcript.fa -subject proteins.fa -outfmt 6 > blastx.tsv
```

For remote NCBI lookups, prefer Python so the workflow is easy to archive:

```python
from Bio import Entrez, SeqIO

Entrez.email = "research@example.com"
handle = Entrez.efetch(db="nucleotide", id="NM_000546", rettype="fasta", retmode="text")
record = SeqIO.read(handle, "fasta")
print(record.id, len(record.seq))
```

## Read Alignment And BAM Processing

```bash
# Build index
bwa index reference.fa

# Short-read alignment
bwa mem reference.fa reads_R1.fastq.gz reads_R2.fastq.gz > aligned.sam

# Long-read alignment
minimap2 -a reference.fa long_reads.fastq.gz > aligned.sam

# SAM -> sorted/indexed BAM
samtools view -bS aligned.sam | samtools sort -o aligned.sorted.bam
samtools index aligned.sorted.bam
samtools flagstat aligned.sorted.bam > aligned.flagstat.txt
```

## FASTQ Quality Control

```bash
mkdir -p qc
fastqc reads_R1.fastq.gz reads_R2.fastq.gz -o qc

# Quick sequence statistics
seqtk comp reads_R1.fastq.gz | head
seqtk size reads_R1.fastq.gz
```

Report at minimum:
- total reads
- adapter or overrepresented sequence warnings
- per-base quality drop-off
- GC bias
- whether trimming/filtering is needed before alignment

## Genome Arithmetic

```bash
bedtools intersect -a peaks.bed -b genes.bed > overlap.bed
bedtools coverage -a targets.bed -b aligned.sorted.bam > coverage.tsv
bedtools getfasta -fi reference.fa -bed targets.bed > targets.fa
```

## Python Analysis Recipes

### Sequence I/O

```python
from Bio import SeqIO

for record in SeqIO.parse("input.fa", "fasta"):
    print(record.id, len(record.seq))
```

### Differential Expression

```python
import pandas as pd
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

counts = pd.read_csv("counts.csv", index_col=0)
meta = pd.read_csv("metadata.csv", index_col=0)

dds = DeseqDataSet(counts=counts, metadata=meta, design="~condition")
dds.deseq2()
stats = DeseqStats(dds, contrast=["condition", "treated", "control"])
stats.summary()
res = stats.results_df.sort_values("padj")
res.to_csv("deseq2_results.csv")
```

### Single-Cell RNA-seq

```python
import scanpy as sc

adata = sc.read_h5ad("data.h5ad")
sc.pp.normalize_total(adata)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata)
sc.pp.pca(adata)
sc.pp.neighbors(adata)
sc.tl.umap(adata)
sc.tl.leiden(adata)
sc.pl.umap(adata, color="leiden", save="_leiden.png")
```

### Publication-Style Plots

```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv("expression.csv")
sns.set_theme(style="whitegrid")
ax = sns.scatterplot(data=df, x="log2FoldChange", y="-log10_padj", hue="significant")
ax.figure.savefig("volcano.png", dpi=300, bbox_inches="tight")
```

## Structural Biology

Fetch structures from PDB with `web_fetch` or direct download, then render with PyMOL if available.

```bash
curl -L https://files.rcsb.org/download/1M17.pdb -o 1M17.pdb
cat > render.pml <<'PML'
load 1M17.pdb, prot
hide everything
show cartoon, prot
spectrum count, rainbow, prot
bg_color white
png 1M17_rainbow.png, width=1600, height=1200, dpi=200, ray=1
quit
PML
pymol -cq render.pml
```

When PyMOL is unavailable, still provide the fetched structure, any residue/chain findings, and the exact rendering script the user can run later.

## Literature Search

Use `web_search` or PubMed APIs for recent papers. For structured PubMed workflows:

```python
from Bio import Entrez

Entrez.email = "research@example.com"
search = Entrez.esearch(db="pubmed", term="CRISPR off-target 2025[dp]", retmax=5)
ids = Entrez.read(search)["IdList"]
summary = Entrez.esummary(db="pubmed", id=",".join(ids))
print(Entrez.read(summary))
```

Summaries should include:
- citation
- study type
- model system
- main finding
- why it matters for the user's question

## Outputs

Good replies should mention:
- what inputs were used
- what commands/scripts were run
- what files were generated
- the most important biological conclusion
- uncertainty or validation limits

Example closing pattern:

```text
I aligned the reads against GRCh38 with bwa mem and generated `aligned.sorted.bam` plus `aligned.flagstat.txt`.
FastQC shows 3' quality decay after cycle 125 and adapter contamination in R2, so trimming before re-alignment is recommended.
Next step: run fastp or cutadapt, then repeat alignment and variant calling.
```

## Related Skill

For remote biology database lookups across UniProt, PDB, AlphaFold, ClinVar, Ensembl, GEO, InterPro, KEGG, OpenTargets, Reactome, or STRING, activate `bio-db-tools`.
For AnnData, single-cell dataset profiling, alignment-region inspection, or mzML inventory, activate `omics-tools`.
For public drug-discovery database lookups across PubChem, ChEMBL, openFDA, ClinicalTrials.gov, or OpenAlex, activate `pharma-db-tools`.
For molecular docking or pose inspection, activate `docking-tools`.
For DeepChem, PySCF, RDKit descriptors, or chemistry-specific follow-up, activate `chem-tools`.
