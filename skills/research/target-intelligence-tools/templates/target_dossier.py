#!/usr/bin/env python3
"""Build a compact drug-target intelligence dossier from public APIs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:
    requests = None

UNIPROT_BASE_URL = "https://rest.uniprot.org"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
OPENTARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
STRING_BASE_URL = "https://version-12-0.string-db.org/api"
REACTOME_CONTENT_URL = "https://reactome.org/ContentService"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GNOMAD_API_URL = "https://gnomad.broadinstitute.org/api"

SEARCH_QUERY = """
query Search($queryString: String!, $entityNames: [String!]!, $size: Int!) {
  search(queryString: $queryString, entityNames: $entityNames, page: { index: 0, size: $size }) {
    hits { id name description entity }
  }
}
"""

TARGET_DISEASES_QUERY = """
query TargetDiseases($ensemblId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    approvedName
    associatedDiseases(page: { index: 0, size: $size }) {
      count
      rows {
        disease { id name }
        score
      }
    }
  }
}
"""

TARGET_DRUGS_QUERY = """
query TargetDrugs($ensemblId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    approvedName
    knownDrugs(size: $size) {
      count
      rows {
        drug { id name }
        mechanismOfAction
        phase
        status
        disease { id name }
      }
    }
  }
}
"""

GNOMAD_CONSTRAINT_QUERY = """
query GeneConstraint($gene_symbol: String!, $reference_genome: ReferenceGenomeId!) {
  gene(gene_symbol: $gene_symbol, reference_genome: $reference_genome) {
    gene_id
    gene_symbol
    gnomad_constraint {
      pli
      oe_lof
      oe_lof_lower
      oe_lof_upper
      lof_z
      mis_z
    }
  }
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a target dossier from public biology and drug-discovery APIs")
    parser.add_argument("--query", required=True, help="Gene symbol, protein name, UniProt accession, or Ensembl gene id")
    parser.add_argument("--organism-id", type=int, default=9606)
    parser.add_argument("--species-name", default="Homo sapiens")
    parser.add_argument("--disease-limit", type=int, default=10)
    parser.add_argument("--drug-limit", type=int, default=10)
    parser.add_argument("--interaction-limit", type=int, default=10)
    parser.add_argument("--pathway-limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", default="target_dossier.md")
    parser.add_argument("--summary", default="target_dossier.json")
    parser.add_argument("--detail-json", help="Optional JSON dump of raw API payloads")
    return parser.parse_args()


def require_requests() -> Any:
    if requests is None:
        raise SystemExit("target_dossier.py requires requests")
    return requests


def http_json(method: str, url: str, *, timeout: int, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    req = require_requests()
    response = req.request(method, url, params=params, json=json_body, headers=headers, timeout=timeout)
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def list_to_text(values: list[Any]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return "; ".join(out)


def graphql(query: str, variables: dict[str, Any], timeout: int) -> Any:
    return http_json("POST", OPENTARGETS_URL, timeout=timeout, json_body={"query": query, "variables": variables}, headers={"Content-Type": "application/json"})


def resolve_target(query: str, organism_id: int, timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    detail: dict[str, Any] = {}
    ot = graphql(SEARCH_QUERY, {"queryString": query, "entityNames": ["target"], "size": 5}, timeout)
    detail["opentargets_search"] = ot
    hits = ot.get("data", {}).get("search", {}).get("hits", []) or []
    primary = hits[0] if hits else {}
    symbol = clean_text(primary.get("name") or query)
    ensembl_id = clean_text(primary.get("id"))

    uniprot = http_json(
        "GET",
        f"{UNIPROT_BASE_URL}/uniprotkb/search",
        timeout=timeout,
        params={
            "query": f"({query}) AND organism_id:{organism_id}",
            "size": 5,
            "format": "json",
            "fields": "accession,id,protein_name,gene_names,organism_name,length,cc_function",
        },
    )
    detail["uniprot_search"] = uniprot
    protein = (uniprot.get("results") or [{}])[0]
    accession = clean_text(protein.get("primaryAccession"))
    genes = protein.get("genes") or []
    if genes:
        symbol = clean_text((genes[0].get("geneName") or {}).get("value")) or symbol

    chembl = http_json(
        "GET",
        f"{CHEMBL_BASE}/target/search.json",
        timeout=timeout,
        params={"q": symbol or query, "limit": 5},
    )
    detail["chembl_target_search"] = chembl
    chembl_targets = chembl.get("targets") or []
    return {
        "query": query,
        "symbol": symbol or query,
        "ensembl_id": ensembl_id,
        "uniprot_accession": accession,
        "protein_name": clean_text(((protein.get("proteinDescription") or {}).get("recommendedName") or {}).get("fullName", {}).get("value")),
        "uniprot_id": clean_text(protein.get("uniProtkbId")),
        "organism": clean_text((protein.get("organism") or {}).get("scientificName")),
        "sequence_length": clean_text(protein.get("sequence", {}).get("length")),
        "function": clean_text(((protein.get("comments") or [{}])[0] or {}).get("texts", [{}])[0].get("value")),
        "chembl_target_id": clean_text((chembl_targets[0] or {}).get("target_chembl_id")) if chembl_targets else "",
        "chembl_target_name": clean_text((chembl_targets[0] or {}).get("pref_name")) if chembl_targets else "",
    }, detail


def fetch_target_diseases(ensembl_id: str, timeout: int, limit: int) -> tuple[list[dict[str, Any]], Any]:
    if not ensembl_id:
        return [], {}
    detail = graphql(TARGET_DISEASES_QUERY, {"ensemblId": ensembl_id, "size": limit}, timeout)
    rows = []
    target = detail.get("data", {}).get("target", {}) or {}
    for item in target.get("associatedDiseases", {}).get("rows", []) or []:
        disease = item.get("disease", {}) or {}
        rows.append({"id": clean_text(disease.get("id")), "name": clean_text(disease.get("name")), "score": item.get("score")})
    return rows, detail


def fetch_target_drugs(ensembl_id: str, timeout: int, limit: int) -> tuple[list[dict[str, Any]], Any]:
    if not ensembl_id:
        return [], {}
    detail = graphql(TARGET_DRUGS_QUERY, {"ensemblId": ensembl_id, "size": limit}, timeout)
    rows = []
    target = detail.get("data", {}).get("target", {}) or {}
    for item in target.get("knownDrugs", {}).get("rows", []) or []:
        drug = item.get("drug", {}) or {}
        disease = item.get("disease", {}) or {}
        rows.append({
            "id": clean_text(drug.get("id")),
            "name": clean_text(drug.get("name")),
            "mechanism": clean_text(item.get("mechanismOfAction")),
            "phase": item.get("phase"),
            "status": clean_text(item.get("status")),
            "disease": clean_text(disease.get("name")),
        })
    return rows, detail


def fetch_string_partners(symbol: str, species: int, timeout: int, limit: int) -> tuple[list[dict[str, Any]], Any]:
    if not symbol:
        return [], {}
    detail = http_json(
        "GET",
        f"{STRING_BASE_URL}/json/interaction_partners",
        timeout=timeout,
        params={"identifiers": symbol, "species": species, "caller_identity": "drugclaw", "limit": limit},
    )
    rows = []
    for item in (detail or [])[:limit]:
        rows.append({"partner": clean_text(item.get("preferredName_B")), "score": item.get("score"), "annotation": clean_text(item.get("annotation"))})
    return rows, detail


def fetch_reactome_pathways(symbol: str, species_name: str, timeout: int, limit: int) -> tuple[list[dict[str, Any]], Any]:
    if not symbol:
        return [], {}
    detail = http_json(
        "GET",
        f"{REACTOME_CONTENT_URL}/search/query",
        timeout=timeout,
        params={"query": symbol, "species": species_name, "types": "Pathway", "cluster": "true"},
        headers={"Accept": "application/json"},
    )
    rows = []
    for group in detail.get("results", []) or []:
        for entry in group.get("entries", []) or []:
            rows.append({"pathway_id": clean_text(entry.get("stId")), "name": clean_text(entry.get("name")), "species": clean_text(entry.get("species"))})
            if len(rows) >= limit:
                return rows, detail
    return rows, detail


def fetch_clinvar_count(symbol: str, timeout: int) -> tuple[int, Any]:
    if not symbol:
        return 0, {}
    detail = http_json(
        "GET",
        f"{NCBI_EUTILS_BASE}/esearch.fcgi",
        timeout=timeout,
        params={"db": "clinvar", "term": f"{symbol}[gene]", "retmode": "json"},
    )
    count = int(((detail.get("esearchresult") or {}).get("count") or 0))
    return count, detail


def fetch_gnomad_constraint(symbol: str, timeout: int) -> tuple[dict[str, Any], Any]:
    if not symbol:
        return {}, {}
    detail = http_json(
        "POST",
        GNOMAD_API_URL,
        timeout=timeout,
        json_body={"query": GNOMAD_CONSTRAINT_QUERY, "variables": {"gene_symbol": symbol, "reference_genome": "GRCh38"}},
        headers={"Content-Type": "application/json"},
    )
    gene = detail.get("data", {}).get("gene", {}) or {}
    constraint = gene.get("gnomad_constraint", {}) or {}
    row = {
        "gene_id": clean_text(gene.get("gene_id")),
        "gene_symbol": clean_text(gene.get("gene_symbol")),
        "pli": clean_text(constraint.get("pli")),
        "oe_lof": clean_text(constraint.get("oe_lof")),
        "oe_lof_lower": clean_text(constraint.get("oe_lof_lower")),
        "oe_lof_upper": clean_text(constraint.get("oe_lof_upper")),
        "lof_z": clean_text(constraint.get("lof_z")),
        "mis_z": clean_text(constraint.get("mis_z")),
    }
    return row, detail


def render_markdown(identity: dict[str, Any], diseases: list[dict[str, Any]], drugs: list[dict[str, Any]], partners: list[dict[str, Any]], pathways: list[dict[str, Any]], clinvar_count: int, constraint: dict[str, Any]) -> str:
    lines = [
        f"# Target Dossier: {identity.get('symbol') or identity.get('query')}",
        "",
        "## Identity",
        f"- Query: `{identity.get('query', '')}`",
        f"- Gene symbol: `{identity.get('symbol', '')}`",
        f"- Ensembl target id: `{identity.get('ensembl_id', '')}`",
        f"- UniProt accession: `{identity.get('uniprot_accession', '')}`",
        f"- UniProt id: `{identity.get('uniprot_id', '')}`",
        f"- Protein name: {identity.get('protein_name', '')}",
        f"- Organism: {identity.get('organism', '')}",
        f"- Sequence length: {identity.get('sequence_length', '')}",
        f"- ChEMBL target: `{identity.get('chembl_target_id', '')}` {identity.get('chembl_target_name', '')}",
        "",
        "## Functional Note",
        identity.get('function', '') or "No UniProt function text returned.",
        "",
        "## Disease Associations",
    ]
    if diseases:
        for item in diseases:
            lines.append(f"- {item.get('name', '')} (`{item.get('id', '')}`), score={item.get('score', '')}")
    else:
        lines.append("- No OpenTargets disease associations returned")
    lines.extend(["", "## Known Drugs"])
    if drugs:
        for item in drugs:
            lines.append(f"- {item.get('name', '')} (`{item.get('id', '')}`), phase={item.get('phase', '')}, status={item.get('status', '')}, disease={item.get('disease', '')}, mechanism={item.get('mechanism', '')}")
    else:
        lines.append("- No OpenTargets known-drug rows returned")
    lines.extend(["", "## Interaction Partners"])
    if partners:
        for item in partners:
            lines.append(f"- {item.get('partner', '')}, score={item.get('score', '')}, annotation={item.get('annotation', '')}")
    else:
        lines.append("- No STRING partners returned")
    lines.extend(["", "## Pathways"])
    if pathways:
        for item in pathways:
            lines.append(f"- {item.get('name', '')} (`{item.get('pathway_id', '')}`)")
    else:
        lines.append("- No Reactome pathways returned")
    lines.extend([
        "",
        "## Variant / Constraint Signals",
        f"- ClinVar record count for gene query: {clinvar_count}",
        f"- gnomAD pLI: {constraint.get('pli', '')}",
        f"- gnomAD oe_lof: {constraint.get('oe_lof', '')} ({constraint.get('oe_lof_lower', '')} - {constraint.get('oe_lof_upper', '')})",
        f"- gnomAD lof_z: {constraint.get('lof_z', '')}",
        f"- gnomAD mis_z: {constraint.get('mis_z', '')}",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    identity, details = resolve_target(args.query, args.organism_id, args.timeout)
    diseases, disease_detail = fetch_target_diseases(identity.get("ensembl_id", ""), args.timeout, args.disease_limit)
    drugs, drug_detail = fetch_target_drugs(identity.get("ensembl_id", ""), args.timeout, args.drug_limit)
    partners, partner_detail = fetch_string_partners(identity.get("symbol", ""), args.organism_id, args.timeout, args.interaction_limit)
    pathways, pathway_detail = fetch_reactome_pathways(identity.get("symbol", ""), args.species_name, args.timeout, args.pathway_limit)
    clinvar_count, clinvar_detail = fetch_clinvar_count(identity.get("symbol", ""), args.timeout)
    constraint, constraint_detail = fetch_gnomad_constraint(identity.get("symbol", ""), args.timeout)

    details.update({
        "target_diseases": disease_detail,
        "target_drugs": drug_detail,
        "string_partners": partner_detail,
        "reactome_pathways": pathway_detail,
        "clinvar_count": clinvar_detail,
        "gnomad_constraint": constraint_detail,
    })

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(identity, diseases, drugs, partners, pathways, clinvar_count, constraint), encoding="utf-8")

    summary = {
        "query": args.query,
        "symbol": identity.get("symbol", ""),
        "ensembl_id": identity.get("ensembl_id", ""),
        "uniprot_accession": identity.get("uniprot_accession", ""),
        "chembl_target_id": identity.get("chembl_target_id", ""),
        "disease_rows": len(diseases),
        "drug_rows": len(drugs),
        "interaction_rows": len(partners),
        "pathway_rows": len(pathways),
        "clinvar_count": clinvar_count,
        "gnomad_constraint": constraint,
        "output": args.output,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.detail_json:
        detail_path = Path(args.detail_json)
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": args.output, "summary": args.summary, "result_count": len(diseases)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
