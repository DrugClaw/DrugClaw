#!/usr/bin/env python3
"""Build and query drug-discovery knowledge graphs from OpenTargets, ChEMBL, STRING, and Reactome."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import networkx as nx
except Exception:  # pragma: no cover - optional at runtime
    nx = None

try:
    import requests
except Exception:  # pragma: no cover - optional at runtime
    requests = None

OPENTARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
STRING_BASE = "https://version-12-0.string-db.org/api"
REACTOME_BASE = "https://reactome.org/ContentService"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build and query drug-target-disease-pathway knowledge graphs"
    )
    p.add_argument("--mode", choices=["build", "query"], required=True)

    grp_build = p.add_argument_group("build options")
    grp_build.add_argument("--seed-type", choices=["disease", "drug"])
    grp_build.add_argument("--seed", help="Disease name / EFO ID, or drug name / ChEMBL ID")
    grp_build.add_argument("--max-targets", type=int, default=30)
    grp_build.add_argument("--max-drugs-per-target", type=int, default=5)
    grp_build.add_argument("--string-limit", type=int, default=10)
    grp_build.add_argument("--pathway-limit", type=int, default=5)
    grp_build.add_argument("--include-string", action="store_true")
    grp_build.add_argument("--include-reactome", action="store_true")
    grp_build.add_argument("--organism-id", type=int, default=9606)
    grp_build.add_argument("--species-name", default="Homo sapiens")
    grp_build.add_argument("--timeout", type=int, default=30)

    grp_query = p.add_argument_group("query options")
    grp_query.add_argument("--input", help="GraphML file to load for query mode")
    grp_query.add_argument("--query-type", choices=["shortest-path", "hubs", "neighbors"])
    grp_query.add_argument("--from-node", help="Source node for shortest-path")
    grp_query.add_argument("--to-node", help="Target node for shortest-path")
    grp_query.add_argument("--center-node", help="Center node for neighbor expansion")
    grp_query.add_argument("--radius", type=int, default=2)
    grp_query.add_argument("--top-k", type=int, default=20)

    p.add_argument("--output", default="kg/knowledge_graph.graphml")
    p.add_argument("--summary", default="kg/knowledge_graph.json")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_networkx():
    if nx is None:
        raise SystemExit("knowledge_graph.py requires networkx")


def require_requests():
    if requests is None:
        raise SystemExit("knowledge_graph.py requires requests for build mode")
    return requests


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def http_json(method: str, url: str, *, timeout: int,
              params: dict[str, Any] | None = None,
              json_body: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None) -> Any:
    req = require_requests()
    resp = req.request(method, url, params=params, json=json_body,
                       headers=headers, timeout=timeout)
    resp.raise_for_status()
    if not resp.content:
        return {}
    return resp.json()


def ot_graphql(query: str, variables: dict[str, Any], timeout: int) -> Any:
    return http_json("POST", OPENTARGETS_URL, timeout=timeout,
                     json_body={"query": query, "variables": variables},
                     headers={"Content-Type": "application/json"})


def write_json(path: str, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# OpenTargets queries
# ---------------------------------------------------------------------------

SEARCH_DISEASE = """
query ($q: String!, $size: Int!) {
  search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: $size}) {
    hits { id name entity }
  }
}"""

DISEASE_TARGETS = """
query ($efoId: String!, $size: Int!) {
  disease(efoId: $efoId) {
    id name
    associatedTargets(page: {index: 0, size: $size}) {
      count
      rows { target { id approvedSymbol approvedName } score }
    }
  }
}"""

TARGET_DRUGS = """
query ($ensemblId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    id approvedSymbol
    knownDrugs(size: $size) {
      rows { drug { id name } mechanismOfAction phase status }
    }
  }
}"""

SEARCH_TARGET = """
query ($q: String!, $size: Int!) {
  search(queryString: $q, entityNames: ["target"], page: {index: 0, size: $size}) {
    hits { id name entity }
  }
}"""

TARGET_DISEASES = """
query ($ensemblId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    id approvedSymbol
    associatedDiseases(page: {index: 0, size: $size}) {
      rows { disease { id name } score }
    }
  }
}"""


# ---------------------------------------------------------------------------
# Build: resolve seed entities
# ---------------------------------------------------------------------------

def resolve_disease(name: str, timeout: int) -> dict[str, str]:
    if name.startswith("EFO_") or name.startswith("MONDO_") or name.startswith("Orphanet_"):
        return {"efo_id": name, "name": name}
    data = ot_graphql(SEARCH_DISEASE, {"q": name, "size": 5}, timeout)
    hits = data.get("data", {}).get("search", {}).get("hits", [])
    if not hits:
        raise SystemExit(f"Disease not found in OpenTargets: {name}")
    return {"efo_id": hits[0]["id"], "name": hits[0].get("name", name)}


def resolve_drug_chembl(name: str, timeout: int) -> tuple[str, str]:
    """Return (chembl_id, pref_name)."""
    req = require_requests()
    resp = req.get(f"{CHEMBL_BASE}/molecule/search.json",
                   params={"q": name, "limit": 3}, timeout=timeout)
    if resp.status_code != 200:
        raise SystemExit(f"ChEMBL molecule search failed for: {name}")
    mols = resp.json().get("molecules", [])
    if not mols:
        raise SystemExit(f"Drug not found in ChEMBL: {name}")
    return (clean_text(mols[0].get("molecule_chembl_id")),
            clean_text(mols[0].get("pref_name") or name))


def fetch_drug_mechanisms(chembl_id: str, timeout: int) -> list[dict[str, Any]]:
    req = require_requests()
    resp = req.get(f"{CHEMBL_BASE}/mechanism.json",
                   params={"molecule_chembl_id": chembl_id, "limit": 50}, timeout=timeout)
    if resp.status_code != 200:
        return []
    mechanisms = resp.json().get("mechanisms", [])
    results = []
    seen: set[str] = set()
    for mech in mechanisms:
        tid = clean_text(mech.get("target_chembl_id"))
        if not tid or tid in seen:
            continue
        seen.add(tid)
        results.append({
            "target_chembl_id": tid,
            "target_name": clean_text(mech.get("target_pref_name")),
            "mechanism": clean_text(mech.get("mechanism_of_action")),
        })
    return results


def chembl_target_to_ensembl(chembl_target_id: str, timeout: int) -> str:
    req = require_requests()
    try:
        resp = req.get(f"{CHEMBL_BASE}/target/{chembl_target_id}.json", timeout=timeout)
        if resp.status_code != 200:
            return ""
        for comp in resp.json().get("target_components") or []:
            for xref in comp.get("target_component_xrefs") or []:
                if xref.get("xref_src_db") == "EnsemblGene":
                    return clean_text(xref.get("xref_id"))
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Build: fetch layers
# ---------------------------------------------------------------------------

def fetch_disease_targets(efo_id: str, limit: int, timeout: int) -> list[dict[str, Any]]:
    data = ot_graphql(DISEASE_TARGETS, {"efoId": efo_id, "size": limit}, timeout)
    rows = data.get("data", {}).get("disease", {}).get("associatedTargets", {}).get("rows", [])
    return [{"ensembl_id": r["target"]["id"],
             "symbol": r["target"]["approvedSymbol"],
             "name": r["target"].get("approvedName", ""),
             "ot_score": r.get("score", 0)} for r in rows]


def fetch_target_drugs(ensembl_id: str, limit: int, timeout: int) -> list[dict[str, Any]]:
    data = ot_graphql(TARGET_DRUGS, {"ensemblId": ensembl_id, "size": limit}, timeout)
    target = data.get("data", {}).get("target", {}) or {}
    drugs: list[dict[str, Any]] = []
    for row in (target.get("knownDrugs") or {}).get("rows", []):
        drug = row.get("drug") or {}
        drugs.append({
            "chembl_id": clean_text(drug.get("id")),
            "name": clean_text(drug.get("name")),
            "mechanism": clean_text(row.get("mechanismOfAction")),
            "phase": row.get("phase", ""),
        })
    return drugs


def fetch_target_diseases(ensembl_id: str, limit: int, timeout: int) -> list[dict[str, Any]]:
    data = ot_graphql(TARGET_DISEASES, {"ensemblId": ensembl_id, "size": limit}, timeout)
    target = data.get("data", {}).get("target", {}) or {}
    diseases: list[dict[str, Any]] = []
    for row in (target.get("associatedDiseases") or {}).get("rows", []):
        d = row.get("disease") or {}
        diseases.append({
            "efo_id": clean_text(d.get("id")),
            "name": clean_text(d.get("name")),
            "ot_score": row.get("score", 0),
        })
    return diseases


def fetch_string_partners(symbol: str, species: int,
                          limit: int, timeout: int) -> list[dict[str, Any]]:
    try:
        data = http_json("GET", f"{STRING_BASE}/json/interaction_partners",
                         timeout=timeout,
                         params={"identifiers": symbol, "species": species,
                                 "caller_identity": "drugclaw", "limit": limit})
    except Exception:
        return []
    partners: list[dict[str, Any]] = []
    for item in (data or [])[:limit]:
        partners.append({
            "partner": clean_text(item.get("preferredName_B")),
            "score": item.get("score"),
        })
    return partners


def fetch_reactome_pathways(symbol: str, species_name: str,
                            limit: int, timeout: int) -> list[dict[str, Any]]:
    try:
        data = http_json("GET", f"{REACTOME_BASE}/search/query",
                         timeout=timeout,
                         params={"query": symbol, "species": species_name,
                                 "types": "Pathway", "cluster": "true"},
                         headers={"Accept": "application/json"})
    except Exception:
        return []
    pathways: list[dict[str, Any]] = []
    for group in data.get("results", []) or []:
        for entry in group.get("entries", []) or []:
            pathways.append({
                "pathway_id": clean_text(entry.get("stId")),
                "name": clean_text(entry.get("name")),
            })
            if len(pathways) >= limit:
                return pathways
    return pathways


# ---------------------------------------------------------------------------
# Build: assemble graph
# ---------------------------------------------------------------------------

def build_disease_graph(args: argparse.Namespace) -> Any:
    require_networkx()
    disease = resolve_disease(args.seed, args.timeout)
    efo_id = disease["efo_id"]
    disease_name = disease["name"]
    print(f"Disease: {disease_name} ({efo_id})")

    G = nx.DiGraph()
    G.add_node(efo_id, entity_type="disease", label=disease_name)

    targets = fetch_disease_targets(efo_id, args.max_targets, args.timeout)
    print(f"  Targets from OpenTargets: {len(targets)}")
    for t in targets:
        G.add_node(t["ensembl_id"], entity_type="target", label=t["symbol"])
        G.add_edge(t["ensembl_id"], efo_id,
                    relation="associated_with", source_db="opentargets",
                    score=str(t["ot_score"]))

    drug_count = 0
    for t in targets:
        drugs = fetch_target_drugs(t["ensembl_id"], args.max_drugs_per_target, args.timeout)
        for d in drugs:
            cid = d["chembl_id"]
            if not cid:
                continue
            if cid not in G:
                G.add_node(cid, entity_type="drug", label=d["name"])
            G.add_edge(cid, t["ensembl_id"],
                       relation="targets", source_db="opentargets",
                       mechanism=d.get("mechanism", ""),
                       phase=str(d.get("phase", "")))
            drug_count += 1
    print(f"  Drug-target edges from OpenTargets: {drug_count}")

    if args.include_string:
        ppi_count = 0
        for t in targets:
            partners = fetch_string_partners(t["symbol"], args.organism_id,
                                             args.string_limit, args.timeout)
            for p in partners:
                partner_name = p["partner"]
                if not partner_name:
                    continue
                partner_id = f"STRING:{partner_name}"
                if partner_id not in G:
                    G.add_node(partner_id, entity_type="target", label=partner_name)
                G.add_edge(t["ensembl_id"], partner_id,
                           relation="interacts_with", source_db="string",
                           score=str(p.get("score", "")))
                ppi_count += 1
        print(f"  PPI edges from STRING: {ppi_count}")

    if args.include_reactome:
        pathway_count = 0
        for t in targets:
            pathways = fetch_reactome_pathways(t["symbol"], args.species_name,
                                               args.pathway_limit, args.timeout)
            for pw in pathways:
                pid = pw["pathway_id"]
                if not pid:
                    continue
                if pid not in G:
                    G.add_node(pid, entity_type="pathway", label=pw["name"])
                G.add_edge(t["ensembl_id"], pid,
                           relation="member_of", source_db="reactome")
                pathway_count += 1
        print(f"  Pathway edges from Reactome: {pathway_count}")

    return G


def build_drug_graph(args: argparse.Namespace) -> Any:
    require_networkx()
    chembl_id, drug_name = resolve_drug_chembl(args.seed, args.timeout)
    print(f"Drug: {drug_name} ({chembl_id})")

    G = nx.DiGraph()
    G.add_node(chembl_id, entity_type="drug", label=drug_name)

    mechanisms = fetch_drug_mechanisms(chembl_id, args.timeout)
    print(f"  Mechanisms from ChEMBL: {len(mechanisms)}")

    targets_for_expansion: list[dict[str, Any]] = []
    for mech in mechanisms:
        ensembl = chembl_target_to_ensembl(mech["target_chembl_id"], args.timeout)
        if not ensembl:
            data = ot_graphql(SEARCH_TARGET, {"q": mech["target_name"], "size": 3}, args.timeout)
            hits = data.get("data", {}).get("search", {}).get("hits", [])
            ensembl = hits[0]["id"] if hits else ""
        if ensembl:
            symbol = mech["target_name"]
            G.add_node(ensembl, entity_type="target", label=symbol)
            G.add_edge(chembl_id, ensembl,
                       relation="targets", source_db="chembl",
                       mechanism=mech.get("mechanism", ""))
            targets_for_expansion.append({"ensembl_id": ensembl, "symbol": symbol})

    disease_count = 0
    for t in targets_for_expansion[:args.max_targets]:
        diseases = fetch_target_diseases(t["ensembl_id"], 10, args.timeout)
        for d in diseases:
            did = d["efo_id"]
            if not did:
                continue
            if did not in G:
                G.add_node(did, entity_type="disease", label=d["name"])
            G.add_edge(t["ensembl_id"], did,
                       relation="associated_with", source_db="opentargets",
                       score=str(d.get("ot_score", "")))
            disease_count += 1
    print(f"  Disease edges from OpenTargets: {disease_count}")

    if args.include_string:
        ppi_count = 0
        for t in targets_for_expansion[:args.max_targets]:
            partners = fetch_string_partners(t["symbol"], args.organism_id,
                                             args.string_limit, args.timeout)
            for p in partners:
                partner_name = p["partner"]
                if not partner_name:
                    continue
                partner_id = f"STRING:{partner_name}"
                if partner_id not in G:
                    G.add_node(partner_id, entity_type="target", label=partner_name)
                G.add_edge(t["ensembl_id"], partner_id,
                           relation="interacts_with", source_db="string",
                           score=str(p.get("score", "")))
                ppi_count += 1
        print(f"  PPI edges from STRING: {ppi_count}")

    if args.include_reactome:
        pathway_count = 0
        for t in targets_for_expansion[:args.max_targets]:
            pathways = fetch_reactome_pathways(t["symbol"], args.species_name,
                                               args.pathway_limit, args.timeout)
            for pw in pathways:
                pid = pw["pathway_id"]
                if not pid:
                    continue
                if pid not in G:
                    G.add_node(pid, entity_type="pathway", label=pw["name"])
                G.add_edge(t["ensembl_id"], pid,
                           relation="member_of", source_db="reactome")
                pathway_count += 1
        print(f"  Pathway edges from Reactome: {pathway_count}")

    return G


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def hub_analysis(G: Any, top_k: int) -> list[dict[str, Any]]:
    degree = dict(G.degree())
    try:
        betweenness = nx.betweenness_centrality(G)
    except Exception:
        betweenness = {n: 0.0 for n in G.nodes()}
    ranked = sorted(degree.keys(), key=lambda n: degree[n], reverse=True)[:top_k]
    return [{
        "node": n,
        "entity_type": G.nodes[n].get("entity_type", ""),
        "label": G.nodes[n].get("label", ""),
        "degree": degree[n],
        "betweenness": round(betweenness.get(n, 0.0), 6),
    } for n in ranked]


def shortest_path_query(G: Any, from_node: str, to_node: str) -> dict[str, Any]:
    try:
        path = nx.shortest_path(G, source=from_node, target=to_node)
        steps = []
        for i in range(len(path) - 1):
            edge_data = G.get_edge_data(path[i], path[i + 1]) or {}
            steps.append({
                "from": path[i],
                "from_type": G.nodes[path[i]].get("entity_type", ""),
                "from_label": G.nodes[path[i]].get("label", ""),
                "to": path[i + 1],
                "to_type": G.nodes[path[i + 1]].get("entity_type", ""),
                "to_label": G.nodes[path[i + 1]].get("label", ""),
                "relation": edge_data.get("relation", ""),
                "source_db": edge_data.get("source_db", ""),
            })
        return {"found": True, "length": len(path) - 1, "path": path, "steps": steps}
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        return {"found": False, "error": str(exc)}


def neighbor_query(G: Any, center: str, radius: int) -> dict[str, Any]:
    if center not in G:
        return {"found": False, "error": f"Node '{center}' not in graph"}
    sub = nx.ego_graph(G, center, radius=radius, undirected=True)
    nodes = [{"node": n, "entity_type": G.nodes[n].get("entity_type", ""),
              "label": G.nodes[n].get("label", "")} for n in sub.nodes()]
    edges = [{"from": u, "to": v,
              "relation": d.get("relation", ""),
              "source_db": d.get("source_db", "")} for u, v, d in sub.edges(data=True)]
    return {"found": True, "center": center, "radius": radius,
            "node_count": len(nodes), "edge_count": len(edges),
            "nodes": nodes, "edges": edges}


def graph_summary(G: Any) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        t = d.get("entity_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    rel_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        r = d.get("relation", "unknown")
        rel_counts[r] = rel_counts.get(r, 0) + 1
        s = d.get("source_db", "unknown")
        source_counts[s] = source_counts.get(s, 0) + 1
    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": type_counts,
        "edge_relations": rel_counts,
        "data_sources": source_counts,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    require_networkx()

    if args.mode == "build":
        if not args.seed_type or not args.seed:
            raise SystemExit("--seed-type and --seed required for build mode")

        if args.seed_type == "disease":
            G = build_disease_graph(args)
        else:
            G = build_drug_graph(args)

        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(G, args.output)
        print(f"Graph saved: {args.output}")

        hubs = hub_analysis(G, 10)
        summary = {
            **graph_summary(G),
            "seed_type": args.seed_type,
            "seed": args.seed,
            "include_string": args.include_string,
            "include_reactome": args.include_reactome,
            "top_hubs": hubs,
            "output": args.output,
        }
        write_json(args.summary, summary)

    elif args.mode == "query":
        if not args.input:
            raise SystemExit("--input (GraphML) required for query mode")
        G = nx.read_graphml(args.input)
        print(f"Loaded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        if args.query_type == "shortest-path":
            if not args.from_node or not args.to_node:
                raise SystemExit("--from-node and --to-node required")
            result = shortest_path_query(G, args.from_node, args.to_node)
            summary: dict[str, Any] = {"query_type": "shortest-path", **result}
        elif args.query_type == "hubs":
            hubs = hub_analysis(G, args.top_k)
            summary = {"query_type": "hubs", "top_k": args.top_k, "hubs": hubs}
        elif args.query_type == "neighbors":
            if not args.center_node:
                raise SystemExit("--center-node required for neighbor query")
            result = neighbor_query(G, args.center_node, args.radius)
            summary = {"query_type": "neighbors", **result}
        else:
            raise SystemExit(f"Unknown query type: {args.query_type}")

        write_json(args.summary, summary)

    print(json.dumps({"output": args.output, "summary": args.summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()