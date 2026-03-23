---
name: knowledge-graph-tools
description: Drug-discovery knowledge-graph workflow guide for assembling drug-target-disease-pathway relationship graphs from OpenTargets GraphQL, ChEMBL REST, STRING PPI, and Reactome pathway APIs, then running hub detection, shortest-path queries, and neighborhood expansion with networkx. Use when the user asks to build, query, or visualize a biomedical knowledge graph connecting drugs, targets, diseases, and pathways from real public databases without making clinical claims.
---

# Knowledge Graph Tools

Use this skill for building and querying biomedical relationship graphs from public drug-discovery APIs, not for clinical decision-making.

Typical triggers:
- build a knowledge graph seeded from a disease, a drug, or a target list
- find shortest paths from a drug to a disease through intermediate targets and pathways
- identify hub targets that bridge multiple disease areas or drug mechanisms
- expand the neighborhood around a protein to see connected drugs, diseases, and pathways
- merge OpenTargets, ChEMBL, STRING, and Reactome data into one queryable graph

## Working Rules

1. Every node gets a typed label: `drug`, `target`, `disease`, or `pathway`.
2. Every edge records its source database and, where available, an evidence score.
3. Use canonical identifiers: Ensembl for targets, ChEMBL for drugs, EFO for diseases, Reactome stable IDs for pathways.
4. Hub analysis reflects database connectivity, not biological importance; well-studied proteins dominate.
5. Shortest-path hypotheses are topological leads, not validated biology.
6. Do not claim causal or therapeutic conclusions from graph structure alone.

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["networkx", "requests"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If networkx or requests is missing, say so immediately. If network access is blocked, only the `query` mode on pre-built GraphML files will work.

## Bundled Assets

- `templates/knowledge_graph.py`

## Build: Disease-Centric Graph

Use `templates/knowledge_graph.py --mode build --seed-type disease` for:
- fetching disease-associated targets from OpenTargets
- fetching known drugs for those targets from OpenTargets
- adding protein-protein interactions from STRING
- adding pathway membership from Reactome
- assembling typed nodes and edges into a single graph

Quick start:

```bash
python3 templates/knowledge_graph.py \
  --mode build \
  --seed-type disease \
  --seed "Crohn's disease" \
  --max-targets 30 \
  --include-string \
  --include-reactome \
  --output kg/crohn_graph.graphml \
  --summary kg/crohn_summary.json
```

Deliverables:
- GraphML file with typed nodes (`entity_type`) and typed edges (`relation`, `source_db`, `score`)
- summary JSON with node/edge counts by type, top hubs, and data sources queried

## Build: Drug-Centric Graph

Use `--seed-type drug` to start from a drug and expand through its targets:

```bash
python3 templates/knowledge_graph.py \
  --mode build \
  --seed-type drug \
  --seed "imatinib" \
  --max-targets 20 \
  --include-string \
  --include-reactome \
  --output kg/imatinib_graph.graphml \
  --summary kg/imatinib_summary.json
```

## Query: Shortest Path

Use `--mode query --query-type shortest-path` on an existing GraphML file:

```bash
python3 templates/knowledge_graph.py \
  --mode query \
  --input kg/crohn_graph.graphml \
  --query-type shortest-path \
  --from-node "CHEMBL941" \
  --to-node "EFO_0000384" \
  --summary kg/path_result.json
```

Deliverables:
- summary JSON with path length, node sequence, and edge relations for each step

## Query: Hub Analysis

Use `--mode query --query-type hubs`:

```bash
python3 templates/knowledge_graph.py \
  --mode query \
  --input kg/crohn_graph.graphml \
  --query-type hubs \
  --top-k 20 \
  --summary kg/hub_targets.json
```

Deliverables:
- summary JSON with top-K nodes ranked by degree and betweenness centrality, with entity type

## Query: Neighborhood Expansion

Use `--mode query --query-type neighbors`:

```bash
python3 templates/knowledge_graph.py \
  --mode query \
  --input kg/crohn_graph.graphml \
  --query-type neighbors \
  --center-node "ENSG00000141510" \
  --radius 2 \
  --summary kg/tp53_neighborhood.json
```

Deliverables:
- summary JSON with subgraph node list, edge list, and entity-type breakdown

## Output Expectations

Good answers should mention:
- seed entity and type (drug, disease, or target list)
- which APIs were queried (OpenTargets, ChEMBL, STRING, Reactome)
- graph size: node count by type, edge count by relation type
- for hub queries: top hub identifiers, degrees, and entity types
- for path queries: full path with intermediate nodes and edge types
- identifier schemes used
- where GraphML and JSON were saved

## Related Skills

For compound and regulatory database lookups from ChEMBL, openFDA, ClinicalTrials.gov, activate `pharma-db-tools`.
For target-specific intelligence dossiers, activate `target-intelligence-tools`.
For drug repurposing hypothesis generation, activate `drug-repurposing-tools`.
For pathway enrichment from gene lists, activate `pathway-enrichment-tools`.
For network pharmacology analysis, activate `network-pharmacology-tools`.
For raw bio database lookups in UniProt, PDB, ClinVar, gnomAD, Reactome, STRING, activate `bio-db-tools`.

## Reference

This skill queries the following public APIs during `build` mode:
- **OpenTargets Platform GraphQL** — `https://api.platform.opentargets.org/api/v4/graphql` — disease-target associations (`associatedTargets`), known drugs (`knownDrugs`), and entity search ([platform.opentargets.org](https://platform.opentargets.org/))
- **ChEMBL REST API** — `https://www.ebi.ac.uk/chembl/api/data` — molecule search, mechanism-of-action retrieval, and target cross-references ([chembl.gitbook.io](https://chembl.gitbook.io/chembl-interface-documentation/web-services))
- **STRING API v12** — `https://version-12-0.string-db.org/api` — protein-protein interaction partners with combined confidence scores ([string-db.org](https://string-db.org/))
- **Reactome Content Service** — `https://reactome.org/ContentService` — pathway search by gene symbol with species filter ([reactome.org](https://reactome.org/))
- Graph analysis uses **networkx** — `nx.shortest_path`, `nx.betweenness_centrality`, `nx.ego_graph` ([networkx.org](https://networkx.org/))
- The `target-intelligence-tools` skill in this repository served as the reference implementation for API calling patterns, error handling, and identifier resolution.