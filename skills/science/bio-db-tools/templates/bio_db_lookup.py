#!/usr/bin/env python3
"""Query public biology databases and write normalized result tables."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import requests
except Exception:  # pragma: no cover - optional at runtime
    requests = None


UNIPROT_BASE_URL = "https://rest.uniprot.org"
RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry"
ALPHAFOLD_API_BASE = "https://alphafold.ebi.ac.uk/api"
ALPHAFOLD_FILE_BASE = "https://alphafold.ebi.ac.uk/files"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ENSEMBL_BASE_URL = "https://rest.ensembl.org"
INTERPRO_BASE_URL = "https://www.ebi.ac.uk/interpro/api"
KEGG_BASE_URL = "https://rest.kegg.jp"
OPENTARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
REACTOME_CONTENT_URL = "https://reactome.org/ContentService"
REACTOME_ANALYSIS_URL = "https://reactome.org/AnalysisService"
STRING_BASE_URL = "https://version-12-0.string-db.org/api"
GNOMAD_API_URL = "https://gnomad.broadinstitute.org/api"
NCBI_VARIATION_BASE = "https://api.ncbi.nlm.nih.gov/variation/v0"


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output", default="bio_db_hits.csv")
    common.add_argument("--summary", default="bio_db_summary.json")
    common.add_argument("--detail-json", help="Write the raw response payload to JSON")
    common.add_argument("--timeout", type=int, default=30)

    parser = argparse.ArgumentParser(description="Query public biology databases and APIs")
    subparsers = parser.add_subparsers(dest="database", required=True)

    uniprot = subparsers.add_parser("uniprot", parents=[common], help="Search UniProtKB")
    uniprot.add_argument("--query", help="Gene, protein, or free-text UniProt query")
    uniprot.add_argument("--accession", help="UniProt accession such as P04637")
    uniprot.add_argument("--organism-id", type=int, default=9606)
    uniprot.add_argument("--limit", type=int, default=10)
    uniprot.add_argument("--include-unreviewed", action="store_true", default=False)

    pdb = subparsers.add_parser("pdb", parents=[common], help="Search RCSB PDB")
    pdb.add_argument("--query", help="Full-text PDB query")
    pdb.add_argument("--pdb-id", help="PDB accession such as 6LU7")
    pdb.add_argument("--method", help="Experimental method filter such as X-RAY DIFFRACTION")
    pdb.add_argument("--limit", type=int, default=10)

    alphafold = subparsers.add_parser("alphafold", parents=[common], help="Fetch AlphaFold DB metadata")
    alphafold.add_argument("--uniprot-id", required=True)
    alphafold.add_argument("--download", help="Optional output path for the model file")
    alphafold.add_argument("--format", choices=["pdb", "cif"], default="pdb")

    clinvar = subparsers.add_parser("clinvar", parents=[common], help="Search ClinVar via NCBI eUtils")
    clinvar.add_argument("--query", required=True)
    clinvar.add_argument("--limit", type=int, default=10)
    clinvar.add_argument("--ncbi-email", default=os.getenv("NCBI_EMAIL", ""))

    ensembl = subparsers.add_parser("ensembl", parents=[common], help="Query Ensembl")
    ensembl.add_argument("--species", default="homo_sapiens")
    ensembl.add_argument("--symbol", help="Gene symbol such as BRCA1")
    ensembl.add_argument("--ensembl-id", help="Ensembl gene or transcript ID")
    ensembl.add_argument("--rsid", help="Variant rsID")

    geo = subparsers.add_parser("geo", parents=[common], help="Search NCBI GEO via eUtils")
    geo.add_argument("--query", required=True)
    geo.add_argument("--limit", type=int, default=10)
    geo.add_argument("--db", default="gds")
    geo.add_argument("--ncbi-email", default=os.getenv("NCBI_EMAIL", ""))

    interpro = subparsers.add_parser("interpro", parents=[common], help="Query InterPro")
    interpro.add_argument("--query", help="Free-text InterPro search")
    interpro.add_argument("--uniprot-id", help="UniProt accession for domain matches")
    interpro.add_argument("--interpro-id", help="InterPro accession such as IPR000719")
    interpro.add_argument("--limit", type=int, default=10)

    kegg = subparsers.add_parser("kegg", parents=[common], help="Query KEGG REST")
    kegg.add_argument("--query", help="Free-text KEGG search")
    kegg.add_argument("--entry-id", help="KEGG entry id such as hsa04110 or hsa:672")
    kegg.add_argument("--scope", choices=["pathway", "gene"], default="pathway")
    kegg.add_argument("--organism", default="hsa")
    kegg.add_argument("--limit", type=int, default=10)

    opentargets = subparsers.add_parser("opentargets", parents=[common], help="Query OpenTargets GraphQL")
    opentargets.add_argument(
        "--mode",
        required=True,
        choices=["search-target", "search-disease", "target-diseases", "disease-targets", "target-drugs"],
    )
    opentargets.add_argument("--query", help="Search text for search modes")
    opentargets.add_argument("--id", help="Ensembl target id or disease EFO id")
    opentargets.add_argument("--limit", type=int, default=10)

    reactome = subparsers.add_parser("reactome", parents=[common], help="Query Reactome")
    reactome.add_argument("--mode", required=True, choices=["search", "participants", "enrichment"])
    reactome.add_argument("--query", help="Pathway search text")
    reactome.add_argument("--pathway-id", help="Reactome stable id such as R-HSA-73894")
    reactome.add_argument("--species", default="Homo sapiens")
    reactome.add_argument("--gene", action="append", default=[])
    reactome.add_argument("--gene-file", help="Text file with one gene symbol per line")
    reactome.add_argument("--limit", type=int, default=10)

    stringdb = subparsers.add_parser("stringdb", parents=[common], help="Query STRING")
    stringdb.add_argument("--mode", required=True, choices=["network", "partners", "enrichment"])
    stringdb.add_argument("--gene", action="append", default=[])
    stringdb.add_argument("--gene-file", help="Text file with one gene symbol per line")
    stringdb.add_argument("--species", type=int, default=9606)
    stringdb.add_argument("--score-threshold", type=int, default=400)
    stringdb.add_argument("--limit", type=int, default=10)

    gnomad = subparsers.add_parser("gnomad", parents=[common], help="Query gnomAD GraphQL")
    gnomad.add_argument("--mode", required=True, choices=["variant", "gene-constraint"])
    gnomad.add_argument("--variant-id", help="Variant id such as 17-43094692-G-A")
    gnomad.add_argument("--gene-symbol", help="Gene symbol such as BRCA1")
    gnomad.add_argument("--dataset", default="gnomad_r4")
    gnomad.add_argument("--reference-genome", default="GRCh38")

    dbsnp = subparsers.add_parser("dbsnp", parents=[common], help="Query dbSNP or NCBI Variation")
    dbsnp.add_argument("--rsid", required=True, help="rs identifier such as rs429358")

    return parser.parse_args()


def require_requests() -> Any:
    if requests is None:
        raise SystemExit("requests is required for bio_db_lookup.py")
    return requests


def http_json(
    method: str,
    url: str,
    *,
    timeout: int,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    json_body: Optional[dict[str, Any]] = None,
    data: Optional[str] = None,
) -> Any:
    req = require_requests()
    response = req.request(method, url, params=params, headers=headers, json=json_body, data=data, timeout=timeout)
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def http_text(
    method: str,
    url: str,
    *,
    timeout: int,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    data: Optional[str] = None,
) -> str:
    req = require_requests()
    response = req.request(method, url, params=params, headers=headers, data=data, timeout=timeout)
    response.raise_for_status()
    return response.text


def http_bytes(method: str, url: str, *, timeout: int, headers: Optional[dict[str, str]] = None) -> bytes:
    req = require_requests()
    response = req.request(method, url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.content


def graphql_json(url: str, query: str, variables: dict[str, Any], timeout: int) -> Any:
    return http_json(
        "POST",
        url,
        timeout=timeout,
        headers={"Content-Type": "application/json"},
        json_body={"query": query, "variables": variables},
    )


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        try:
            if value != value:
                return ""
        except Exception:
            pass
    return str(value).strip()


def compact_spaces(value: Any) -> str:
    return " ".join(clean_text(value).split())


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def list_to_text(values: Iterable[Any]) -> str:
    items = []
    for value in values:
        if isinstance(value, dict):
            text = first_nonempty(value.get("value"), value.get("name"), value.get("label"), value.get("id"))
        else:
            text = clean_text(value)
        if text:
            items.append(text)
    return "; ".join(dedupe(items))


def flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return "; ".join(clean_text(item) for item in value if clean_text(item))
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return clean_text(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_rows(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        write_json(output_path, rows)
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(key)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["message"])
        writer.writeheader()
        if not rows:
            return
        for row in rows:
            writer.writerow({key: flatten_value(value) for key, value in row.items()})


def finish(rows: list[dict[str, Any]], summary: dict[str, Any], args: argparse.Namespace, detail: Any = None) -> None:
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    write_rows(rows, output_path)
    summary["result_count"] = len(rows)
    summary["output"] = str(output_path)
    write_json(summary_path, summary)
    if args.detail_json:
        write_json(Path(args.detail_json), detail if detail is not None else rows)
    print(json.dumps({"output": str(output_path), "summary": str(summary_path), "result_count": len(rows)}, ensure_ascii=False))


def get_function_text(comments: list[dict[str, Any]]) -> str:
    snippets: list[str] = []
    for comment in comments:
        if comment.get("commentType") != "FUNCTION":
            continue
        for text_block in comment.get("texts", []):
            text = clean_text(text_block.get("value"))
            if text:
                snippets.append(text)
    return " | ".join(dedupe(snippets))


def summarize_uniprot_entry(entry: dict[str, Any]) -> dict[str, Any]:
    protein_name = first_nonempty(
        entry.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value"),
        entry.get("proteinDescription", {}).get("submissionNames", [{}])[0].get("fullName", {}).get("value"),
    )
    gene_names = []
    for gene in entry.get("genes", []):
        gene_name = gene.get("geneName", {})
        if gene_name.get("value"):
            gene_names.append(gene_name["value"])
        for synonym in gene.get("synonyms", []):
            if synonym.get("value"):
                gene_names.append(synonym["value"])
    keyword_names = [item.get("name", "") for item in entry.get("keywords", [])]
    return {
        "accession": clean_text(entry.get("primaryAccession")),
        "entry_id": clean_text(entry.get("uniProtkbId")),
        "gene_names": list_to_text(gene_names),
        "protein_name": protein_name,
        "organism": clean_text(entry.get("organism", {}).get("scientificName")),
        "length": entry.get("sequence", {}).get("length", ""),
        "function": get_function_text(entry.get("comments", [])),
        "keywords": list_to_text(keyword_names),
        "link": f"https://www.uniprot.org/uniprotkb/{clean_text(entry.get('primaryAccession'))}",
    }


def run_uniprot(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if not args.query and not args.accession:
        raise SystemExit("uniprot requires --query or --accession")
    if args.accession:
        detail = http_json("GET", f"{UNIPROT_BASE_URL}/uniprotkb/{args.accession}.json", timeout=args.timeout)
        rows = [summarize_uniprot_entry(detail)]
        return rows, {"database": "uniprot", "mode": "accession", "query": args.accession}, detail
    query = args.query
    if args.organism_id:
        query = f"({query}) AND organism_id:{args.organism_id}"
    if not args.include_unreviewed:
        query = f"({query}) AND reviewed:true"
    detail = http_json(
        "GET",
        f"{UNIPROT_BASE_URL}/uniprotkb/search",
        timeout=args.timeout,
        params={
            "query": query,
            "format": "json",
            "size": args.limit,
            "fields": "accession,id,gene_names,protein_name,organism_name,length,cc_function,keyword",
        },
    )
    rows = [summarize_uniprot_entry(entry) for entry in detail.get("results", [])]
    return rows, {"database": "uniprot", "mode": "search", "query": query}, detail


def summarize_pdb_entry(pdb_id: str, detail: dict[str, Any]) -> dict[str, Any]:
    info = detail.get("rcsb_entry_info", {})
    resolutions = info.get("resolution_combined", [])
    return {
        "pdb_id": pdb_id,
        "title": clean_text(detail.get("struct", {}).get("title")),
        "method": clean_text(detail.get("exptl", [{}])[0].get("method")),
        "resolution_angstrom": resolutions[0] if resolutions else "",
        "deposit_date": clean_text(detail.get("rcsb_accession_info", {}).get("deposit_date")),
        "polymer_entity_count": info.get("polymer_entity_count", ""),
        "ligand_entity_count": info.get("nonpolymer_entity_count", ""),
        "link": f"https://www.rcsb.org/structure/{pdb_id}",
    }


def pdb_search_payload(query_text: str, limit: int, method: str) -> dict[str, Any]:
    text_node = {
        "type": "terminal",
        "service": "full_text",
        "parameters": {"value": query_text},
    }
    if not method:
        query = text_node
    else:
        query = {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                text_node,
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "exptl.method",
                        "operator": "exact_match",
                        "value": method,
                    },
                },
            ],
        }
    return {
        "query": query,
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": limit}},
    }


def run_pdb(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if not args.query and not args.pdb_id:
        raise SystemExit("pdb requires --query or --pdb-id")
    if args.pdb_id:
        pdb_id = args.pdb_id.upper()
        detail = http_json("GET", f"{RCSB_ENTRY_URL}/{pdb_id}", timeout=args.timeout)
        rows = [summarize_pdb_entry(pdb_id, detail)]
        return rows, {"database": "pdb", "mode": "entry", "query": pdb_id}, detail
    payload = pdb_search_payload(args.query, args.limit, args.method or "")
    search_response = http_json("POST", RCSB_SEARCH_URL, timeout=args.timeout, json_body=payload)
    rows: list[dict[str, Any]] = []
    detailed_hits: list[dict[str, Any]] = []
    for item in search_response.get("result_set", []):
        pdb_id = clean_text(item.get("identifier")).upper()
        if not pdb_id:
            continue
        detail = http_json("GET", f"{RCSB_ENTRY_URL}/{pdb_id}", timeout=args.timeout)
        detailed_hits.append(detail)
        rows.append(summarize_pdb_entry(pdb_id, detail))
    detail = {"search": search_response, "entries": detailed_hits}
    return rows, {"database": "pdb", "mode": "search", "query": args.query, "method": args.method or ""}, detail


def run_alphafold(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    uniprot_id = args.uniprot_id.upper()
    detail = http_json("GET", f"{ALPHAFOLD_API_BASE}/prediction/{uniprot_id}", timeout=args.timeout)
    if not isinstance(detail, list):
        detail = [detail]
    rows: list[dict[str, Any]] = []
    for item in detail:
        rows.append(
            {
                "uniprot_accession": clean_text(item.get("uniprotAccession", uniprot_id)),
                "gene": clean_text(item.get("gene")),
                "organism": clean_text(item.get("organismScientificName")),
                "model_entity": clean_text(item.get("entryId")),
                "global_metric_value": item.get("globalMetricValue", ""),
                "pdb_url": clean_text(item.get("pdbUrl")),
                "cif_url": clean_text(item.get("cifUrl")),
                "pae_image_url": clean_text(item.get("paeImageUrl")),
                "link": f"https://alphafold.ebi.ac.uk/entry/{uniprot_id}",
            }
        )
    if args.download:
        download_url = ""
        if detail:
            download_url = clean_text(detail[0].get("pdbUrl" if args.format == "pdb" else "cifUrl"))
        if not download_url:
            suffix = "pdb" if args.format == "pdb" else "cif"
            download_url = f"{ALPHAFOLD_FILE_BASE}/AF-{uniprot_id}-F1-model_v4.{suffix}"
        content = http_bytes("GET", download_url, timeout=args.timeout)
        download_path = Path(args.download)
        download_path.parent.mkdir(parents=True, exist_ok=True)
        download_path.write_bytes(content)
    return rows, {"database": "alphafold", "mode": "prediction", "query": uniprot_id, "download": args.download or ""}, detail


def ncbi_params(base: dict[str, Any], email: str) -> dict[str, Any]:
    params = dict(base)
    if clean_text(email):
        params["email"] = clean_text(email)
    params.setdefault("tool", "drugclaw")
    return params


def run_clinvar(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    search = http_json(
        "GET",
        f"{NCBI_EUTILS_BASE}/esearch.fcgi",
        timeout=args.timeout,
        params=ncbi_params({"db": "clinvar", "term": args.query, "retmax": args.limit, "retmode": "json"}, args.ncbi_email),
    )
    ids = search.get("esearchresult", {}).get("idlist", [])
    summary = {}
    if ids:
        summary = http_json(
            "GET",
            f"{NCBI_EUTILS_BASE}/esummary.fcgi",
            timeout=args.timeout,
            params=ncbi_params({"db": "clinvar", "id": ",".join(ids), "retmode": "json"}, args.ncbi_email),
        )
    rows: list[dict[str, Any]] = []
    results = summary.get("result", {}) if isinstance(summary, dict) else {}
    for uid in ids:
        entry = results.get(str(uid), {})
        genes = [gene.get("symbol", "") for gene in entry.get("genes", [])]
        rows.append(
            {
                "uid": str(uid),
                "title": clean_text(entry.get("title")),
                "assembly_name": clean_text(entry.get("variation_set", [{}])[0].get("variation_loc", [{}])[0].get("assembly_name")),
                "clinical_significance": clean_text(entry.get("clinical_significance", {}).get("description")),
                "review_status": clean_text(entry.get("supporting_submissions", {}).get("review_status")),
                "genes": list_to_text(genes),
                "accession": clean_text(entry.get("accession")),
                "link": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
            }
        )
    detail = {"search": search, "summary": summary}
    return rows, {"database": "clinvar", "mode": "search", "query": args.query}, detail


def location_text(chrom: Any, start: Any, end: Any, strand: Any) -> str:
    chrom_text = clean_text(chrom)
    start_text = clean_text(start)
    end_text = clean_text(end)
    strand_text = "+" if str(strand) == "1" else "-" if str(strand) == "-1" else clean_text(strand)
    if chrom_text and start_text and end_text:
        return f"chr{chrom_text}:{start_text}-{end_text} ({strand_text})"
    return ""


def summarize_ensembl_lookup(detail: dict[str, Any]) -> dict[str, Any]:
    transcripts = detail.get("Transcript", []) or detail.get("transcripts", [])
    return {
        "ensembl_id": clean_text(detail.get("id")),
        "display_name": clean_text(detail.get("display_name")),
        "biotype": clean_text(detail.get("biotype")),
        "description": clean_text(detail.get("description")),
        "location": location_text(detail.get("seq_region_name"), detail.get("start"), detail.get("end"), detail.get("strand")),
        "canonical_transcript": clean_text(detail.get("canonical_transcript")),
        "transcript_count": len(transcripts),
        "link": f"https://www.ensembl.org/id/{clean_text(detail.get('id'))}",
    }


def summarize_ensembl_variant(detail: dict[str, Any], species: str) -> dict[str, Any]:
    mappings = []
    for mapping in detail.get("mappings", []):
        mappings.append(location_text(mapping.get("seq_region_name"), mapping.get("start"), mapping.get("end"), mapping.get("strand")))
    return {
        "rsid": clean_text(detail.get("name")),
        "most_severe_consequence": clean_text(detail.get("most_severe_consequence")),
        "clinical_significance": list_to_text(detail.get("clinical_significance", [])),
        "synonyms": list_to_text(detail.get("synonyms", [])),
        "mappings": list_to_text(mappings),
        "link": f"https://www.ensembl.org/{species}/Variation/Explore?v={clean_text(detail.get('name'))}",
    }


def run_ensembl(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    headers = {"Accept": "application/json"}
    if args.rsid:
        detail = http_json("GET", f"{ENSEMBL_BASE_URL}/variation/{args.species}/{args.rsid}", timeout=args.timeout, headers=headers)
        rows = [summarize_ensembl_variant(detail, args.species)]
        return rows, {"database": "ensembl", "mode": "variation", "query": args.rsid, "species": args.species}, detail
    if args.symbol:
        detail = http_json(
            "GET",
            f"{ENSEMBL_BASE_URL}/lookup/symbol/{args.species}/{args.symbol}",
            timeout=args.timeout,
            headers=headers,
            params={"expand": 1},
        )
        rows = [summarize_ensembl_lookup(detail)]
        return rows, {"database": "ensembl", "mode": "symbol", "query": args.symbol, "species": args.species}, detail
    if args.ensembl_id:
        detail = http_json(
            "GET",
            f"{ENSEMBL_BASE_URL}/lookup/id/{args.ensembl_id}",
            timeout=args.timeout,
            headers=headers,
            params={"expand": 1},
        )
        rows = [summarize_ensembl_lookup(detail)]
        return rows, {"database": "ensembl", "mode": "id", "query": args.ensembl_id, "species": args.species}, detail
    raise SystemExit("ensembl requires --symbol, --ensembl-id, or --rsid")


def run_geo(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    search = http_json(
        "GET",
        f"{NCBI_EUTILS_BASE}/esearch.fcgi",
        timeout=args.timeout,
        params=ncbi_params({"db": args.db, "term": args.query, "retmax": args.limit, "retmode": "json", "sort": "relevance"}, args.ncbi_email),
    )
    ids = search.get("esearchresult", {}).get("idlist", [])
    summary = {}
    if ids:
        summary = http_json(
            "GET",
            f"{NCBI_EUTILS_BASE}/esummary.fcgi",
            timeout=args.timeout,
            params=ncbi_params({"db": args.db, "id": ",".join(ids), "retmode": "json"}, args.ncbi_email),
        )
    rows: list[dict[str, Any]] = []
    results = summary.get("result", {}) if isinstance(summary, dict) else {}
    for uid in ids:
        entry = results.get(str(uid), {})
        accession = clean_text(entry.get("accession"))
        rows.append(
            {
                "uid": str(uid),
                "accession": accession,
                "title": clean_text(entry.get("title")),
                "summary": compact_spaces(entry.get("summary")),
                "samples": entry.get("n_samples", ""),
                "platform": clean_text(entry.get("gpl")),
                "organism": list_to_text(entry.get("taxon", [])) if isinstance(entry.get("taxon"), list) else clean_text(entry.get("taxon")),
                "entry_type": clean_text(entry.get("entryType")),
                "link": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}" if accession else "",
            }
        )
    detail = {"search": search, "summary": summary}
    return rows, {"database": "geo", "mode": "search", "query": args.query, "db": args.db}, detail


def interpro_fragments(result: dict[str, Any]) -> str:
    fragments: list[str] = []
    for protein in result.get("proteins", []):
        for location in protein.get("entry_protein_locations", []):
            for fragment in location.get("fragments", []):
                start = clean_text(fragment.get("start"))
                end = clean_text(fragment.get("end"))
                if start and end:
                    fragments.append(f"{start}-{end}")
    return "; ".join(fragments)


def interpro_row(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata", result)
    return {
        "accession": clean_text(metadata.get("accession")),
        "name": first_nonempty(metadata.get("name"), metadata.get("source_database")),
        "type": clean_text(metadata.get("type")),
        "description": compact_spaces(metadata.get("description")),
        "fragments": interpro_fragments(result),
        "link": f"https://www.ebi.ac.uk/interpro/entry/InterPro/{clean_text(metadata.get('accession'))}" if clean_text(metadata.get("accession")) else "",
    }


def run_interpro(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    headers = {"Accept": "application/json"}
    if args.interpro_id:
        detail = http_json("GET", f"{INTERPRO_BASE_URL}/entry/interpro/{args.interpro_id}", timeout=args.timeout, headers=headers)
        results = detail.get("results", []) if isinstance(detail, dict) else []
        rows = [interpro_row(result) for result in results] or [interpro_row(detail)]
        return rows, {"database": "interpro", "mode": "entry", "query": args.interpro_id}, detail
    if args.uniprot_id:
        detail = http_json(
            "GET",
            f"{INTERPRO_BASE_URL}/protein/uniprot/{args.uniprot_id}/entry/interpro",
            timeout=args.timeout,
            headers=headers,
            params={"page_size": args.limit},
        )
        rows = [interpro_row(result) for result in detail.get("results", [])]
        return rows, {"database": "interpro", "mode": "protein", "query": args.uniprot_id}, detail
    if not args.query:
        raise SystemExit("interpro requires --query, --uniprot-id, or --interpro-id")
    detail = http_json(
        "GET",
        f"{INTERPRO_BASE_URL}/entry/interpro",
        timeout=args.timeout,
        headers=headers,
        params={"search": args.query, "page_size": args.limit},
    )
    rows = [interpro_row(result) for result in detail.get("results", [])]
    return rows, {"database": "interpro", "mode": "search", "query": args.query}, detail


def parse_kegg_record(text: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    current_key = ""
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[:12].strip():
            current_key = line[:12].strip().lower()
            value = line[12:].strip()
            row[current_key] = value
        elif current_key:
            row[current_key] = f"{row.get(current_key, '')} {line[12:].strip()}".strip()
    return row


def run_kegg(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if args.entry_id:
        detail = http_text("GET", f"{KEGG_BASE_URL}/get/{args.entry_id}", timeout=args.timeout)
        parsed = parse_kegg_record(detail)
        rows = [
            {
                "entry_id": args.entry_id,
                "name": clean_text(parsed.get("name")),
                "description": clean_text(parsed.get("description")),
                "pathway": clean_text(parsed.get("pathway")),
                "drug": clean_text(parsed.get("drug")),
                "link": f"https://www.genome.jp/entry/{args.entry_id}",
            }
        ]
        return rows, {"database": "kegg", "mode": "entry", "query": args.entry_id}, {"record": detail}
    if not args.query:
        raise SystemExit("kegg requires --query or --entry-id")
    endpoint = f"find/pathway/{args.query}" if args.scope == "pathway" else f"find/{args.organism}/{args.query}"
    detail = http_text("GET", f"{KEGG_BASE_URL}/{endpoint}", timeout=args.timeout)
    rows: list[dict[str, Any]] = []
    for line in detail.splitlines()[: args.limit]:
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        entry_id = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else ""
        rows.append(
            {
                "entry_id": entry_id,
                "name": name,
                "scope": args.scope,
                "link": f"https://www.genome.jp/entry/{entry_id}",
            }
        )
    return rows, {"database": "kegg", "mode": "search", "query": args.query, "scope": args.scope}, {"text": detail}


SEARCH_QUERY = """
query Search($queryString: String!, $entityNames: [String!]!, $size: Int!) {
  search(queryString: $queryString, entityNames: $entityNames, page: {index: 0, size: $size}) {
    total
    hits {
      id
      name
      description
      entity
    }
  }
}
"""

TARGET_DISEASES_QUERY = """
query TargetDiseases($ensemblId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    approvedName
    associatedDiseases(page: {index: 0, size: $size}) {
      count
      rows {
        disease { id name }
        score
      }
    }
  }
}
"""

DISEASE_TARGETS_QUERY = """
query DiseaseTargets($diseaseId: String!, $size: Int!) {
  disease(efoId: $diseaseId) {
    id
    name
    associatedTargets(page: {index: 0, size: $size}) {
      count
      rows {
        target { id approvedSymbol approvedName }
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


def opentargets_query(query: str, variables: dict[str, Any], timeout: int) -> dict[str, Any]:
    payload = {"query": query, "variables": variables}
    return http_json(
        "POST",
        OPENTARGETS_URL,
        timeout=timeout,
        headers={"Content-Type": "application/json"},
        json_body=payload,
    )


def run_opentargets(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if args.mode == "search-target":
        if not args.query:
            raise SystemExit("opentargets --mode search-target requires --query")
        detail = opentargets_query(SEARCH_QUERY, {"queryString": args.query, "entityNames": ["target"], "size": args.limit}, args.timeout)
        hits = detail.get("data", {}).get("search", {}).get("hits", [])
        rows = [{"id": hit.get("id"), "name": hit.get("name"), "description": compact_spaces(hit.get("description")), "entity": hit.get("entity")} for hit in hits]
        return rows, {"database": "opentargets", "mode": args.mode, "query": args.query}, detail
    if args.mode == "search-disease":
        if not args.query:
            raise SystemExit("opentargets --mode search-disease requires --query")
        detail = opentargets_query(SEARCH_QUERY, {"queryString": args.query, "entityNames": ["disease"], "size": args.limit}, args.timeout)
        hits = detail.get("data", {}).get("search", {}).get("hits", [])
        rows = [{"id": hit.get("id"), "name": hit.get("name"), "description": compact_spaces(hit.get("description")), "entity": hit.get("entity")} for hit in hits]
        return rows, {"database": "opentargets", "mode": args.mode, "query": args.query}, detail
    if not args.id:
        raise SystemExit(f"opentargets --mode {args.mode} requires --id")
    if args.mode == "target-diseases":
        detail = opentargets_query(TARGET_DISEASES_QUERY, {"ensemblId": args.id, "size": args.limit}, args.timeout)
        rows = []
        target = detail.get("data", {}).get("target", {})
        for row in target.get("associatedDiseases", {}).get("rows", []):
            disease = row.get("disease", {})
            rows.append({
                "target_id": target.get("id"),
                "target_symbol": target.get("approvedSymbol"),
                "target_name": target.get("approvedName"),
                "disease_id": disease.get("id"),
                "disease_name": disease.get("name"),
                "score": row.get("score", ""),
            })
        return rows, {"database": "opentargets", "mode": args.mode, "query": args.id}, detail
    if args.mode == "disease-targets":
        detail = opentargets_query(DISEASE_TARGETS_QUERY, {"diseaseId": args.id, "size": args.limit}, args.timeout)
        rows = []
        disease = detail.get("data", {}).get("disease", {})
        for row in disease.get("associatedTargets", {}).get("rows", []):
            target = row.get("target", {})
            rows.append({
                "disease_id": disease.get("id"),
                "disease_name": disease.get("name"),
                "target_id": target.get("id"),
                "target_symbol": target.get("approvedSymbol"),
                "target_name": target.get("approvedName"),
                "score": row.get("score", ""),
            })
        return rows, {"database": "opentargets", "mode": args.mode, "query": args.id}, detail
    detail = opentargets_query(TARGET_DRUGS_QUERY, {"ensemblId": args.id, "size": args.limit}, args.timeout)
    rows = []
    target = detail.get("data", {}).get("target", {})
    for row in target.get("knownDrugs", {}).get("rows", []):
        drug = row.get("drug", {})
        disease = row.get("disease", {})
        rows.append({
            "target_id": target.get("id"),
            "target_symbol": target.get("approvedSymbol"),
            "target_name": target.get("approvedName"),
            "drug_id": drug.get("id"),
            "drug_name": drug.get("name"),
            "mechanism_of_action": row.get("mechanismOfAction"),
            "phase": row.get("phase"),
            "status": row.get("status"),
            "disease_id": disease.get("id"),
            "disease_name": disease.get("name"),
        })
    return rows, {"database": "opentargets", "mode": args.mode, "query": args.id}, detail


def read_gene_inputs(genes: list[str], gene_file: Optional[str]) -> list[str]:
    output = [clean_text(gene) for gene in genes if clean_text(gene)]
    if gene_file:
        for line in Path(gene_file).read_text(encoding="utf-8").splitlines():
            text = clean_text(line)
            if text:
                output.append(text)
    return dedupe(output)


def reactome_search_rows(detail: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in detail.get("results", []):
        for entry in group.get("entries", []):
            rows.append(
                {
                    "pathway_id": entry.get("stId"),
                    "name": entry.get("name"),
                    "species": entry.get("species"),
                    "type": entry.get("type"),
                    "link": f"https://reactome.org/content/detail/{entry.get('stId')}",
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def reactome_participant_rows(detail: Any, pathway_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(detail, list):
        for entry in detail:
            ref = entry.get("refEntities", []) if isinstance(entry, dict) else []
            rows.append(
                {
                    "pathway_id": pathway_id,
                    "entity_name": entry.get("displayName") if isinstance(entry, dict) else clean_text(entry),
                    "entity_type": entry.get("schemaClass") if isinstance(entry, dict) else "",
                    "reference_ids": list_to_text([item.get("displayName", "") for item in ref]),
                }
            )
    return rows


def reactome_enrichment_rows(detail: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pathway in detail.get("pathways", [])[:limit]:
        entities = pathway.get("entities", {})
        rows.append(
            {
                "pathway_id": pathway.get("stId"),
                "name": pathway.get("name"),
                "species": pathway.get("species", {}).get("displayName") if isinstance(pathway.get("species"), dict) else pathway.get("species"),
                "found_entities": entities.get("found"),
                "total_entities": entities.get("total"),
                "p_value": entities.get("pValue"),
                "fdr": entities.get("fdr"),
                "link": f"https://reactome.org/content/detail/{pathway.get('stId')}",
            }
        )
    return rows


def run_reactome(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    headers = {"Accept": "application/json"}
    if args.mode == "search":
        if not args.query:
            raise SystemExit("reactome --mode search requires --query")
        detail = http_json(
            "GET",
            f"{REACTOME_CONTENT_URL}/search/query",
            timeout=args.timeout,
            headers=headers,
            params={"query": args.query, "species": args.species, "types": "Pathway", "cluster": "true"},
        )
        rows = reactome_search_rows(detail, args.limit)
        return rows, {"database": "reactome", "mode": args.mode, "query": args.query, "species": args.species}, detail
    if args.mode == "participants":
        if not args.pathway_id:
            raise SystemExit("reactome --mode participants requires --pathway-id")
        detail = http_json(
            "GET",
            f"{REACTOME_CONTENT_URL}/data/participants/{args.pathway_id}",
            timeout=args.timeout,
            headers=headers,
        )
        rows = reactome_participant_rows(detail, args.pathway_id)
        return rows, {"database": "reactome", "mode": args.mode, "query": args.pathway_id}, detail
    genes = read_gene_inputs(args.gene, args.gene_file)
    if not genes:
        raise SystemExit("reactome --mode enrichment requires --gene or --gene-file")
    detail = http_json(
        "POST",
        f"{REACTOME_ANALYSIS_URL}/identifiers/projection",
        timeout=args.timeout,
        headers={"Content-Type": "text/plain", "Accept": "application/json"},
        data="\n".join(genes),
    )
    rows = reactome_enrichment_rows(detail, args.limit)
    return rows, {"database": "reactome", "mode": args.mode, "query": genes}, detail


def run_stringdb(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    genes = read_gene_inputs(args.gene, args.gene_file)
    if not genes:
        raise SystemExit("stringdb requires --gene or --gene-file")
    identifiers = "\r".join(genes)
    params = {"identifiers": identifiers, "species": args.species, "caller_identity": "drugclaw"}
    if args.mode == "network":
        params["required_score"] = args.score_threshold
        detail = http_json("GET", f"{STRING_BASE_URL}/json/network", timeout=args.timeout, params=params)
        rows = []
        for item in detail[: args.limit]:
            rows.append(
                {
                    "preferred_name_a": item.get("preferredName_A"),
                    "preferred_name_b": item.get("preferredName_B"),
                    "score": item.get("score"),
                    "experimental_score": item.get("escore"),
                    "database_score": item.get("dscore"),
                    "textmining_score": item.get("tscore"),
                }
            )
        return rows, {"database": "stringdb", "mode": args.mode, "query": genes, "species": args.species}, detail
    if args.mode == "partners":
        params["limit"] = args.limit
        detail = http_json("GET", f"{STRING_BASE_URL}/json/interaction_partners", timeout=args.timeout, params=params)
        rows = []
        for item in detail[: args.limit]:
            rows.append(
                {
                    "query_item": item.get("inputIdentifier"),
                    "partner": item.get("preferredName_B"),
                    "score": item.get("score"),
                    "annotation": item.get("annotation"),
                }
            )
        return rows, {"database": "stringdb", "mode": args.mode, "query": genes, "species": args.species}, detail
    detail = http_json("GET", f"{STRING_BASE_URL}/json/enrichment", timeout=args.timeout, params=params)
    rows = []
    for item in detail[: args.limit]:
        rows.append(
            {
                "category": item.get("category"),
                "term": item.get("term"),
                "description": item.get("description"),
                "fdr": item.get("fdr"),
                "number_of_genes": item.get("number_of_genes"),
                "input_genes": item.get("inputGenes"),
            }
        )
    return rows, {"database": "stringdb", "mode": args.mode, "query": genes, "species": args.species}, detail


GNOMAD_VARIANT_QUERY = """
query VariantDetails($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variant_id
    chrom
    pos
    ref
    alt
    rsids
    consequence
    lof
    genome { af ac an ac_hom }
    exome { af ac an ac_hom }
  }
}
"""

GNOMAD_CONSTRAINT_QUERY = """
query GeneConstraint($gene_symbol: String!, $reference_genome: ReferenceGenomeId!) {
  gene(gene_symbol: $gene_symbol, reference_genome: $reference_genome) {
    gene_id
    gene_symbol
    gnomad_constraint {
      exp_lof
      obs_lof
      oe_lof
      oe_lof_lower
      oe_lof_upper
      lof_z
      mis_z
      syn_z
      pli
    }
  }
}
"""


def run_gnomad(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if args.mode == "variant":
        if not args.variant_id:
            raise SystemExit("gnomad --mode variant requires --variant-id")
        detail = graphql_json(
            GNOMAD_API_URL,
            GNOMAD_VARIANT_QUERY,
            {"variantId": args.variant_id, "dataset": args.dataset},
            args.timeout,
        )
        variant = detail.get("data", {}).get("variant") or {}
        rows = [{
            "variant_id": clean_text(variant.get("variant_id")),
            "chrom": clean_text(variant.get("chrom")),
            "pos": clean_text(variant.get("pos")),
            "ref": clean_text(variant.get("ref")),
            "alt": clean_text(variant.get("alt")),
            "rsids": list_to_text(variant.get("rsids") or []),
            "consequence": clean_text(variant.get("consequence")),
            "lof": clean_text(variant.get("lof")),
            "genome_af": clean_text((variant.get("genome") or {}).get("af")),
            "genome_ac": clean_text((variant.get("genome") or {}).get("ac")),
            "exome_af": clean_text((variant.get("exome") or {}).get("af")),
            "exome_ac": clean_text((variant.get("exome") or {}).get("ac")),
            "link": f"https://gnomad.broadinstitute.org/variant/{args.variant_id}?dataset={args.dataset}",
        }]
        return rows, {"database": "gnomad", "mode": args.mode, "query": args.variant_id, "dataset": args.dataset}, detail
    if not args.gene_symbol:
        raise SystemExit("gnomad --mode gene-constraint requires --gene-symbol")
    detail = graphql_json(
        GNOMAD_API_URL,
        GNOMAD_CONSTRAINT_QUERY,
        {"gene_symbol": args.gene_symbol, "reference_genome": args.reference_genome},
        args.timeout,
    )
    gene = detail.get("data", {}).get("gene") or {}
    constraint = gene.get("gnomad_constraint") or {}
    rows = [{
        "gene_symbol": clean_text(gene.get("gene_symbol")),
        "gene_id": clean_text(gene.get("gene_id")),
        "pli": clean_text(constraint.get("pli")),
        "oe_lof": clean_text(constraint.get("oe_lof")),
        "oe_lof_lower": clean_text(constraint.get("oe_lof_lower")),
        "oe_lof_upper": clean_text(constraint.get("oe_lof_upper")),
        "lof_z": clean_text(constraint.get("lof_z")),
        "mis_z": clean_text(constraint.get("mis_z")),
        "syn_z": clean_text(constraint.get("syn_z")),
        "obs_lof": clean_text(constraint.get("obs_lof")),
        "exp_lof": clean_text(constraint.get("exp_lof")),
        "link": f"https://gnomad.broadinstitute.org/gene/{clean_text(gene.get('gene_id'))}",
    }]
    return rows, {
        "database": "gnomad",
        "mode": args.mode,
        "query": args.gene_symbol,
        "reference_genome": args.reference_genome,
    }, detail


def dbsnp_numeric_id(rsid: str) -> str:
    text = clean_text(rsid).lower()
    if text.startswith("rs"):
        text = text[2:]
    if not text.isdigit():
        raise SystemExit(f"Invalid rsid: {rsid}")
    return text


def dbsnp_primary_placement(detail: dict[str, Any]) -> tuple[str, str, str]:
    placements = detail.get("primary_snapshot_data", {}).get("placements_with_allele", []) or []
    for placement in placements:
        if placement.get("is_ptlp"):
            traits = (placement.get("placement_annot") or {}).get("seq_id_traits_by_assembly", []) or []
            assembly_name = clean_text(traits[0].get("assembly_name")) if traits else ""
            hgvs = list_to_text([item.get("hgvs") for item in placement.get("alleles", []) or []])
            mol_type = clean_text((placement.get("placement_annot") or {}).get("mol_type"))
            return assembly_name, hgvs, mol_type
    return "", "", ""


def run_dbsnp(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    numeric_id = dbsnp_numeric_id(args.rsid)
    detail = http_json("GET", f"{NCBI_VARIATION_BASE}/refsnp/{numeric_id}", timeout=args.timeout)
    assembly, hgvs, mol_type = dbsnp_primary_placement(detail)
    allele_annotations = detail.get("primary_snapshot_data", {}).get("allele_annotations", []) or []
    clinical: list[str] = []
    for annotation in allele_annotations:
        for clinical_entry in annotation.get("clinical", []) or []:
            clinical.extend(clinical_entry.get("clinical_significances") or [])
    rows = [{
        "rsid": f"rs{numeric_id}",
        "variant_type": clean_text(detail.get("primary_snapshot_data", {}).get("variant_type")),
        "assembly_name": assembly,
        "molecule_type": mol_type,
        "hgvs": hgvs,
        "clinical_significance": list_to_text(clinical),
        "citations": list_to_text(detail.get("citations", []) or []),
        "link": f"https://www.ncbi.nlm.nih.gov/snp/rs{numeric_id}",
    }]
    return rows, {"database": "dbsnp", "mode": "refsnp", "query": f"rs{numeric_id}"}, detail


def main() -> None:
    args = parse_args()
    handlers = {
        "uniprot": run_uniprot,
        "pdb": run_pdb,
        "alphafold": run_alphafold,
        "clinvar": run_clinvar,
        "ensembl": run_ensembl,
        "geo": run_geo,
        "interpro": run_interpro,
        "kegg": run_kegg,
        "opentargets": run_opentargets,
        "reactome": run_reactome,
        "stringdb": run_stringdb,
        "gnomad": run_gnomad,
        "dbsnp": run_dbsnp,
    }
    rows, summary, detail = handlers[args.database](args)
    finish(rows, summary, args, detail)


if __name__ == "__main__":
    main()
