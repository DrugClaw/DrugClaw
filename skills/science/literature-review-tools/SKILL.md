---
name: literature-review-tools
description: Research-literature workflow guide for evidence-matrix assembly, citation-table normalization, structured review synthesis, and research-gap mapping. Use when the user asks for systematic or scoped literature review workflows, citation cleanup, evidence tables, or manuscript-ready review preparation for drug-discovery and biomedical topics.
source: drugclaw
updated_at: "2026-03-11"
---

# Literature Review Tools

Use this skill when the user asks for structured literature review work rather than only a single paper lookup.

Typical triggers:
- systematic or scoped literature review preparation
- citation cleanup before manuscript drafting
- evidence-table or evidence-matrix construction
- research-gap mapping across a paper set
- turning search results into a review-ready artifact

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["pandas"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

For current papers, citations, or metadata that may have changed, also verify with live APIs or web search rather than relying on stale local tables.

## Bundled Assets

- `templates/citation_table_normalize.py`
- `templates/evidence_matrix.py`

## Preferred Workflow

1. Gather citations first from PubMed, OpenAlex, Crossref-like exports, or existing CSV/JSON tables.
2. Run `citation_table_normalize.py` to normalize DOI, PMID, title, and key metadata before synthesis.
3. Run `evidence_matrix.py` to convert the cleaned table into a review or screening matrix.
4. Only then draft a narrative synthesis, gap map, or manuscript section.
5. Keep the evidence matrix and citation table as durable artifacts, not just prose.

## Citation Normalization

```bash
python3 templates/citation_table_normalize.py \
  --input literature/raw_hits.csv \
  --title-column title \
  --doi-column doi \
  --pmid-column pmid \
  --year-column year \
  --journal-column journal \
  --authors-column authors \
  --output literature/normalized_citations.csv \
  --summary literature/normalized_citations.json \
  --bibtex-output literature/normalized_citations.bib
```

Use this for:
- duplicate cleanup by DOI or normalized title
- stable citation-key creation
- lightweight BibTeX export from tabular metadata

## Evidence Matrix Assembly

```bash
python3 templates/evidence_matrix.py \
  --input literature/normalized_citations.csv \
  --title-column title \
  --question-column topic \
  --model-column model_system \
  --intervention-column intervention \
  --outcome-column outcome \
  --finding-column key_finding \
  --evidence-type-column study_type \
  --output literature/evidence_matrix.csv \
  --summary literature/evidence_matrix.json
```

Use this for:
- scoping reviews
- screen-ready evidence tables
- thematic synthesis inputs
- identifying under-covered mechanisms, assays, or modalities

## Working Rules

- Distinguish clearly between local table cleanup and live literature search.
- Do not claim a review is systematic unless search strategy, deduplication, and inclusion logic are documented.
- Treat citation counts and publication volume as context, not proof.
- Keep exact search strings, identifiers, and date ranges when the user needs a reproducible review.

## Related Skills

For paper, author, institution, trial, or public drug-database APIs, activate `pharma-db-tools`.
For PubMed-style biology lookups, activate `bio-tools` or `bio-db-tools` depending on the source.
For hypothesis framing, peer-review style critique, or reproducibility planning, activate `scientific-workflow-tools`.
