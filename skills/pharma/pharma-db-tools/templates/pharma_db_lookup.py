#!/usr/bin/env python3
"""Query public drug-discovery, regulatory, and translational research databases."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote
from xml.etree import ElementTree

try:
    import requests
except Exception:  # pragma: no cover - optional at runtime
    requests = None


PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
OPENFDA_BASE = "https://api.fda.gov"
CLINICALTRIALS_BASE = "https://clinicaltrials.gov/api/v2"
OPENALEX_BASE = "https://api.openalex.org"
BINDINGDB_BASE = "https://www.bindingdb.org/axis2/services/BDBService"
PUBCHEM_PROPERTIES = [
    "MolecularFormula",
    "MolecularWeight",
    "CanonicalSMILES",
    "IsomericSMILES",
    "IUPACName",
    "XLogP",
    "TPSA",
    "HBondDonorCount",
    "HBondAcceptorCount",
    "RotatableBondCount",
    "InChI",
    "InChIKey",
]
BINDINGDB_AFFINITY_FIELDS = {
    "Ki": "Ki (nM)",
    "Kd": "Kd (nM)",
    "IC50": "IC50 (nM)",
    "EC50": "EC50 (nM)",
}


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output", default="pharma_db_hits.csv")
    common.add_argument("--summary", default="pharma_db_summary.json")
    common.add_argument("--detail-json", help="Write the raw response payload to JSON")
    common.add_argument("--timeout", type=int, default=30)

    parser = argparse.ArgumentParser(description="Query public drug-discovery, regulatory, and literature databases")
    subparsers = parser.add_subparsers(dest="database", required=True)

    pubchem = subparsers.add_parser("pubchem", parents=[common], help="Query PubChem compounds")
    pubchem.add_argument("--query", help="Compound name or free-text identifier")
    pubchem.add_argument("--cid", help="PubChem compound id")
    pubchem.add_argument("--smiles", help="Canonical or isomeric SMILES string")
    pubchem.add_argument("--limit", type=int, default=10)

    chembl = subparsers.add_parser("chembl", parents=[common], help="Query ChEMBL molecules, targets, or activities")
    chembl.add_argument("--mode", required=True, choices=["molecule", "target", "activity"])
    chembl.add_argument("--query", help="Free-text molecule or target query")
    chembl.add_argument("--chembl-id", help="ChEMBL molecule id such as CHEMBL25")
    chembl.add_argument("--target-id", help="ChEMBL target id such as CHEMBL203")
    chembl.add_argument("--standard-type", default="IC50")
    chembl.add_argument("--limit", type=int, default=10)

    openfda = subparsers.add_parser("openfda", parents=[common], help="Query openFDA drug endpoints")
    openfda.add_argument("--endpoint", required=True, choices=["label", "event", "ndc", "recall", "approval", "shortage"])
    openfda.add_argument("--query", help="Simple drug or product query")
    openfda.add_argument("--search", help="Raw openFDA search expression")
    openfda.add_argument("--limit", type=int, default=10)
    openfda.add_argument("--count-field", help="Optional aggregation field for count queries")
    openfda.add_argument("--api-key", default=os.getenv("FDA_API_KEY", ""))

    clinicaltrials = subparsers.add_parser("clinicaltrials", parents=[common], help="Query ClinicalTrials.gov API v2")
    clinicaltrials.add_argument("--query", help="General search text")
    clinicaltrials.add_argument("--condition", help="Condition query")
    clinicaltrials.add_argument("--intervention", help="Drug, device, or intervention query")
    clinicaltrials.add_argument("--sponsor", help="Lead sponsor filter applied after fetch")
    clinicaltrials.add_argument("--status", action="append", default=[])
    clinicaltrials.add_argument("--phase", action="append", default=[])
    clinicaltrials.add_argument("--nct-id", help="ClinicalTrials.gov identifier")
    clinicaltrials.add_argument("--limit", type=int, default=10)

    openalex = subparsers.add_parser("openalex", parents=[common], help="Query OpenAlex works")
    openalex.add_argument("--query", help="Free-text literature query")
    openalex.add_argument("--doi", help="DOI lookup")
    openalex.add_argument("--author", help="Author display name for work lookup")
    openalex.add_argument("--institution", help="Institution display name for work lookup")
    openalex.add_argument("--email", default=os.getenv("OPENALEX_EMAIL", ""))
    openalex.add_argument("--sort", default="cited_by_count:desc")
    openalex.add_argument("--limit", type=int, default=10)

    bindingdb = subparsers.add_parser(
        "bindingdb",
        parents=[common],
        help="Query BindingDB measured affinities from a local TSV export or the public service",
    )
    bindingdb.add_argument("--tsv", help="Local BindingDB TSV or CSV export for deterministic offline queries")
    bindingdb.add_argument("--uniprot-id", help="UniProt accession such as P00519")
    bindingdb.add_argument("--compound-name", help="Compound name or synonym text filter")
    bindingdb.add_argument("--target-name", help="Target name filter")
    bindingdb.add_argument("--smiles", help="Exact ligand SMILES filter")
    bindingdb.add_argument("--affinity-type", choices=sorted(BINDINGDB_AFFINITY_FIELDS.keys()), default="Ki")
    bindingdb.add_argument("--max-nm", type=float, default=10000.0, help="Maximum affinity value in nM to keep")
    bindingdb.add_argument("--limit", type=int, default=50)

    return parser.parse_args()


def require_requests() -> Any:
    if requests is None:
        raise SystemExit("requests is required for pharma_db_lookup.py")
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
    if isinstance(values, str):
        return clean_text(values)
    if isinstance(values, dict):
        values = [values]
    items: list[str] = []
    for value in values:
        if isinstance(value, dict):
            text = first_nonempty(value.get("name"), value.get("title"), value.get("value"), value.get("id"))
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


def contains_text(haystack: Any, needle: str) -> bool:
    target = clean_text(needle).lower()
    if not target:
        return True
    return target in clean_text(haystack).lower()


def numeric_from_text(value: Any) -> Optional[float]:
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except Exception:
        return None
    if number != number:
        return None
    return number


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


def pubchem_identifiers_from_query(args: argparse.Namespace) -> tuple[list[str], str]:
    if args.cid:
        return [clean_text(args.cid)], "cid"
    if args.query:
        detail = http_json(
            "GET",
            f"{PUBCHEM_BASE}/compound/name/{quote(args.query)}/cids/JSON",
            timeout=args.timeout,
        )
        ids = [clean_text(value) for value in detail.get("IdentifierList", {}).get("CID", [])][: args.limit]
        return ids, "name"
    if args.smiles:
        detail = http_json(
            "GET",
            f"{PUBCHEM_BASE}/compound/smiles/{quote(args.smiles)}/cids/JSON",
            timeout=args.timeout,
        )
        ids = [clean_text(value) for value in detail.get("IdentifierList", {}).get("CID", [])][: args.limit]
        return ids, "smiles"
    raise SystemExit("pubchem requires --cid, --query, or --smiles")


def pubchem_fetch_properties(cids: list[str], timeout: int) -> list[dict[str, Any]]:
    if not cids:
        return []
    fields = ",".join(PUBCHEM_PROPERTIES)
    detail = http_json(
        "GET",
        f"{PUBCHEM_BASE}/compound/cid/{','.join(cids)}/property/{fields}/JSON",
        timeout=timeout,
    )
    return list(detail.get("PropertyTable", {}).get("Properties", []))


def summarize_pubchem_entry(entry: dict[str, Any]) -> dict[str, Any]:
    cid = clean_text(entry.get("CID"))
    return {
        "cid": cid,
        "name": first_nonempty(entry.get("IUPACName"), entry.get("Title"), f"CID {cid}"),
        "molecular_formula": clean_text(entry.get("MolecularFormula")),
        "molecular_weight": clean_text(entry.get("MolecularWeight")),
        "xlogp": clean_text(entry.get("XLogP")),
        "tpsa": clean_text(entry.get("TPSA")),
        "hbond_donor_count": clean_text(entry.get("HBondDonorCount")),
        "hbond_acceptor_count": clean_text(entry.get("HBondAcceptorCount")),
        "rotatable_bond_count": clean_text(entry.get("RotatableBondCount")),
        "canonical_smiles": clean_text(entry.get("CanonicalSMILES")),
        "isomeric_smiles": clean_text(entry.get("IsomericSMILES")),
        "inchi": clean_text(entry.get("InChI")),
        "inchikey": clean_text(entry.get("InChIKey")),
        "link": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else "",
    }


def run_pubchem(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    cids, mode = pubchem_identifiers_from_query(args)
    detail = pubchem_fetch_properties(cids, args.timeout)
    rows = [summarize_pubchem_entry(entry) for entry in detail]
    query = args.cid or args.query or args.smiles or ""
    return rows, {"database": "pubchem", "mode": mode, "query": query}, detail


def summarize_chembl_molecule(entry: dict[str, Any]) -> dict[str, Any]:
    chembl_id = clean_text(entry.get("molecule_chembl_id"))
    props = entry.get("molecule_properties") or {}
    structures = entry.get("molecule_structures") or {}
    hierarchy = entry.get("molecule_hierarchy") or {}
    return {
        "chembl_id": chembl_id,
        "pref_name": clean_text(entry.get("pref_name")),
        "molecule_type": clean_text(entry.get("molecule_type")),
        "max_phase": clean_text(entry.get("max_phase")),
        "therapeutic_flag": clean_text(entry.get("therapeutic_flag")),
        "alogp": clean_text(props.get("alogp")),
        "molecular_weight": clean_text(props.get("full_mwt")),
        "qed_weighted": clean_text(props.get("qed_weighted")),
        "canonical_smiles": clean_text(structures.get("canonical_smiles")),
        "standard_inchi_key": clean_text(structures.get("standard_inchi_key")),
        "parent_chembl_id": clean_text(hierarchy.get("parent_chembl_id")),
        "link": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "",
    }


def summarize_chembl_target(entry: dict[str, Any]) -> dict[str, Any]:
    chembl_id = clean_text(entry.get("target_chembl_id"))
    comps = entry.get("target_components") or []
    component = comps[0] if comps else {}
    synonyms = [item.get("component_synonym") for item in component.get("target_component_synonyms", []) or []]
    return {
        "target_chembl_id": chembl_id,
        "pref_name": clean_text(entry.get("pref_name")),
        "target_type": clean_text(entry.get("target_type")),
        "organism": clean_text(entry.get("organism")),
        "accession": clean_text(component.get("accession")),
        "gene_symbols": list_to_text(synonyms),
        "link": f"https://www.ebi.ac.uk/chembl/target_report_card/{chembl_id}/" if chembl_id else "",
    }


def summarize_chembl_activity(entry: dict[str, Any]) -> dict[str, Any]:
    molecule_id = clean_text(entry.get("molecule_chembl_id"))
    target_id = clean_text(entry.get("target_chembl_id"))
    assay_id = clean_text(entry.get("assay_chembl_id"))
    return {
        "activity_id": clean_text(entry.get("activity_id")),
        "molecule_chembl_id": molecule_id,
        "target_chembl_id": target_id,
        "assay_chembl_id": assay_id,
        "standard_type": clean_text(entry.get("standard_type")),
        "standard_relation": clean_text(entry.get("standard_relation")),
        "standard_value": clean_text(entry.get("standard_value")),
        "standard_units": clean_text(entry.get("standard_units")),
        "pchembl_value": clean_text(entry.get("pchembl_value")),
        "activity_comment": compact_spaces(entry.get("activity_comment")),
        "document_year": clean_text(entry.get("document_year")),
        "molecule_link": f"https://www.ebi.ac.uk/chembl/compound_report_card/{molecule_id}/" if molecule_id else "",
        "target_link": f"https://www.ebi.ac.uk/chembl/target_report_card/{target_id}/" if target_id else "",
        "assay_link": f"https://www.ebi.ac.uk/chembl/assay_report_card/{assay_id}/" if assay_id else "",
    }


def run_chembl(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if args.mode == "molecule":
        if args.chembl_id:
            detail = http_json("GET", f"{CHEMBL_BASE}/molecule/{args.chembl_id.upper()}.json", timeout=args.timeout)
            rows = [summarize_chembl_molecule(detail)]
            return rows, {"database": "chembl", "mode": "molecule", "query": args.chembl_id.upper()}, detail
        if not args.query:
            raise SystemExit("chembl molecule mode requires --chembl-id or --query")
        detail = http_json(
            "GET",
            f"{CHEMBL_BASE}/molecule/search.json",
            timeout=args.timeout,
            params={"q": args.query, "limit": args.limit},
        )
        rows = [summarize_chembl_molecule(entry) for entry in detail.get("molecules", [])]
        return rows, {"database": "chembl", "mode": "molecule-search", "query": args.query}, detail
    if args.mode == "target":
        if args.target_id:
            detail = http_json("GET", f"{CHEMBL_BASE}/target/{args.target_id.upper()}.json", timeout=args.timeout)
            rows = [summarize_chembl_target(detail)]
            return rows, {"database": "chembl", "mode": "target", "query": args.target_id.upper()}, detail
        if not args.query:
            raise SystemExit("chembl target mode requires --target-id or --query")
        detail = http_json(
            "GET",
            f"{CHEMBL_BASE}/target/search.json",
            timeout=args.timeout,
            params={"q": args.query, "limit": args.limit},
        )
        rows = [summarize_chembl_target(entry) for entry in detail.get("targets", [])]
        return rows, {"database": "chembl", "mode": "target-search", "query": args.query}, detail
    if not args.chembl_id and not args.target_id:
        raise SystemExit("chembl activity mode requires --chembl-id or --target-id")
    params = {
        "limit": args.limit,
        "standard_type": args.standard_type,
    }
    if args.chembl_id:
        params["molecule_chembl_id"] = args.chembl_id.upper()
    if args.target_id:
        params["target_chembl_id"] = args.target_id.upper()
    detail = http_json("GET", f"{CHEMBL_BASE}/activity.json", timeout=args.timeout, params=params)
    rows = [summarize_chembl_activity(entry) for entry in detail.get("activities", [])]
    return rows, {"database": "chembl", "mode": "activity", "query": params}, detail


def build_openfda_search(endpoint: str, query: str) -> str:
    quoted = query.replace('"', "")
    if endpoint in {"label", "ndc", "approval"}:
        return f'openfda.brand_name:"{quoted}"+OR+openfda.generic_name:"{quoted}"'
    if endpoint == "event":
        return f'patient.drug.medicinalproduct:"{quoted}"'
    if endpoint == "recall":
        return f'product_description:"{quoted}"+OR+openfda.brand_name:"{quoted}"'
    if endpoint == "shortage":
        return f'generic_name:"{quoted}"+OR+brand_name:"{quoted}"'
    return quoted


def openfda_endpoint_path(endpoint: str) -> str:
    mapping = {
        "label": "drug/label.json",
        "event": "drug/event.json",
        "ndc": "drug/ndc.json",
        "recall": "drug/enforcement.json",
        "approval": "drug/drugsfda.json",
        "shortage": "drug/drugshortages.json",
    }
    return mapping[endpoint]


def summarize_openfda_result(endpoint: str, entry: dict[str, Any]) -> dict[str, Any]:
    openfda = entry.get("openfda") or {}
    brand = list_to_text(openfda.get("brand_name") or [])
    generic = list_to_text(openfda.get("generic_name") or [])
    if endpoint == "label":
        set_id = first_nonempty(entry.get("set_id"), entry.get("id"), list_to_text(openfda.get("spl_set_id") or []))
        return {
            "set_id": set_id,
            "brand_name": brand,
            "generic_name": generic,
            "manufacturer_name": list_to_text(openfda.get("manufacturer_name") or []),
            "product_type": list_to_text(openfda.get("product_type") or []),
            "route": list_to_text(openfda.get("route") or []),
            "indications_and_usage": compact_spaces((entry.get("indications_and_usage") or [""])[0]),
            "warnings": compact_spaces((entry.get("warnings") or [""])[0]),
            "dosage_and_administration": compact_spaces((entry.get("dosage_and_administration") or [""])[0]),
            "link": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}" if set_id else "",
        }
    if endpoint == "event":
        reactions = []
        for patient in entry.get("patient", {}).get("reaction", []) or []:
            reactions.append(patient.get("reactionmeddrapt"))
        products = []
        for drug in entry.get("patient", {}).get("drug", []) or []:
            products.append(drug.get("medicinalproduct"))
        return {
            "safetyreportid": clean_text(entry.get("safetyreportid")),
            "receivedate": clean_text(entry.get("receivedate")),
            "serious": clean_text(entry.get("serious")),
            "drugs": list_to_text(products),
            "reactions": list_to_text(reactions),
            "occurcountry": clean_text(entry.get("occurcountry")),
            "source": clean_text(entry.get("primarysource", {}).get("reportercountry")),
        }
    if endpoint == "ndc":
        return {
            "product_ndc": clean_text(entry.get("product_ndc")),
            "brand_name": brand or clean_text(entry.get("brand_name")),
            "generic_name": generic or clean_text(entry.get("generic_name")),
            "dosage_form": clean_text(entry.get("dosage_form")),
            "route": list_to_text(entry.get("route") or []),
            "marketing_status": clean_text(entry.get("marketing_status")),
            "labeler_name": clean_text(entry.get("labeler_name")),
            "product_type": clean_text(entry.get("product_type")),
        }
    if endpoint == "recall":
        return {
            "recall_number": clean_text(entry.get("recall_number")),
            "classification": clean_text(entry.get("classification")),
            "status": clean_text(entry.get("status")),
            "report_date": clean_text(entry.get("report_date")),
            "product_description": compact_spaces(entry.get("product_description")),
            "reason_for_recall": compact_spaces(entry.get("reason_for_recall")),
            "recalling_firm": clean_text(entry.get("recalling_firm")),
            "product_type": clean_text(entry.get("product_type")),
        }
    if endpoint == "approval":
        products = entry.get("products") or []
        product = products[0] if products else {}
        return {
            "application_number": clean_text(entry.get("application_number")),
            "sponsor_name": clean_text(entry.get("sponsor_name")),
            "brand_name": clean_text(product.get("brand_name")),
            "generic_name": clean_text(product.get("generic_name")),
            "dosage_form": clean_text(product.get("dosage_form")),
            "marketing_status": clean_text(product.get("marketing_status")),
            "submission_status_date": clean_text(entry.get("submissions", [{}])[0].get("submission_status_date")),
        }
    return {
        "generic_name": clean_text(entry.get("generic_name")),
        "brand_name": clean_text(entry.get("brand_name")),
        "status": clean_text(entry.get("status")),
        "active_ingredient": clean_text(entry.get("active_ingredient")),
        "dosage_form": clean_text(entry.get("dosage_form")),
        "reason": compact_spaces(entry.get("reason")),
    }


def run_openfda(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    search = args.search or (build_openfda_search(args.endpoint, args.query) if args.query else "")
    if not search and not args.count_field:
        raise SystemExit("openfda requires --query or --search")
    params: dict[str, Any] = {"limit": args.limit}
    if search:
        params["search"] = search
    if args.count_field:
        params["count"] = args.count_field
        params.pop("limit", None)
    if args.api_key:
        params["api_key"] = args.api_key
    detail = http_json("GET", f"{OPENFDA_BASE}/{openfda_endpoint_path(args.endpoint)}", timeout=args.timeout, params=params)
    if args.count_field:
        rows = [
            {
                "term": clean_text(item.get("term")),
                "count": clean_text(item.get("count")),
            }
            for item in detail.get("results", [])
        ]
    else:
        rows = [summarize_openfda_result(args.endpoint, entry) for entry in detail.get("results", [])]
    return rows, {"database": "openfda", "endpoint": args.endpoint, "query": search or args.count_field}, detail


def extract_clinical_trial_row(study: dict[str, Any]) -> dict[str, Any]:
    protocol = study.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}
    interventions = [item.get("name") for item in arms.get("interventions", []) or []]
    phases = design.get("phases") or []
    nct_id = clean_text(ident.get("nctId"))
    return {
        "nct_id": nct_id,
        "brief_title": clean_text(ident.get("briefTitle")),
        "overall_status": clean_text(status.get("overallStatus")),
        "study_type": clean_text(design.get("studyType")),
        "phases": list_to_text(phases),
        "conditions": list_to_text(conditions.get("conditions") or []),
        "interventions": list_to_text(interventions),
        "lead_sponsor": clean_text((sponsor.get("leadSponsor") or {}).get("name")),
        "start_date": clean_text((status.get("startDateStruct") or {}).get("date")),
        "completion_date": clean_text((status.get("completionDateStruct") or {}).get("date")),
        "link": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
    }


def filter_clinical_trial_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    status_filters = {item.strip().lower() for item in args.status if clean_text(item)}
    phase_filters = {item.strip().lower() for item in args.phase if clean_text(item)}
    sponsor_filter = clean_text(args.sponsor).lower()
    output: list[dict[str, Any]] = []
    for row in rows:
        row_status = clean_text(row.get("overall_status")).lower()
        row_phases = clean_text(row.get("phases")).lower()
        row_sponsor = clean_text(row.get("lead_sponsor")).lower()
        if status_filters and row_status not in status_filters:
            continue
        if phase_filters and not any(phase in row_phases for phase in phase_filters):
            continue
        if sponsor_filter and sponsor_filter not in row_sponsor:
            continue
        output.append(row)
        if len(output) >= args.limit:
            break
    return output


def run_clinicaltrials(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if args.nct_id:
        detail = http_json("GET", f"{CLINICALTRIALS_BASE}/studies/{args.nct_id}", timeout=args.timeout)
        study = detail.get("protocolSection") and detail or detail.get("study") or detail
        rows = [extract_clinical_trial_row(study)]
        return rows, {"database": "clinicaltrials", "mode": "study", "query": args.nct_id}, detail
    params: dict[str, Any] = {"pageSize": max(args.limit * 3, args.limit)}
    if args.query:
        params["query.term"] = args.query
    if args.condition:
        params["query.cond"] = args.condition
    if args.intervention:
        params["query.intr"] = args.intervention
    detail = http_json("GET", f"{CLINICALTRIALS_BASE}/studies", timeout=args.timeout, params=params)
    raw_studies = detail.get("studies", [])
    rows = [extract_clinical_trial_row(study) for study in raw_studies]
    rows = filter_clinical_trial_rows(rows, args)
    return rows, {
        "database": "clinicaltrials",
        "mode": "search",
        "query": {"term": args.query, "condition": args.condition, "intervention": args.intervention},
    }, detail


def openalex_headers(email: str) -> dict[str, str]:
    user_agent = "DrugClaw pharma-db-tools"
    if email:
        user_agent = f"DrugClaw pharma-db-tools ({email})"
    return {"User-Agent": user_agent}


def resolve_openalex_entity(entity_type: str, query: str, timeout: int, email: str) -> tuple[str, dict[str, Any]]:
    detail = http_json(
        "GET",
        f"{OPENALEX_BASE}/{entity_type}",
        timeout=timeout,
        params={"search": query, "per-page": 1, **({"mailto": email} if email else {})},
        headers=openalex_headers(email),
    )
    results = detail.get("results", [])
    if not results:
        raise SystemExit(f"OpenAlex returned no {entity_type} match for query: {query}")
    entity = results[0]
    return clean_text(entity.get("id")), entity


def summarize_openalex_work(entry: dict[str, Any]) -> dict[str, Any]:
    authorships = entry.get("authorships") or []
    authors = []
    institutions = []
    for authorship in authorships:
        author = authorship.get("author") or {}
        institution_hits = authorship.get("institutions") or []
        if author.get("display_name"):
            authors.append(author.get("display_name"))
        for institution in institution_hits:
            if institution.get("display_name"):
                institutions.append(institution.get("display_name"))
    ids = entry.get("ids") or {}
    return {
        "openalex_id": clean_text(entry.get("id")),
        "title": clean_text(entry.get("display_name")),
        "publication_year": clean_text(entry.get("publication_year")),
        "type": clean_text(entry.get("type")),
        "cited_by_count": clean_text(entry.get("cited_by_count")),
        "doi": clean_text(ids.get("doi")),
        "pmid": clean_text(ids.get("pmid")),
        "primary_source": clean_text((entry.get("primary_location") or {}).get("source", {}).get("display_name")),
        "is_open_access": clean_text((entry.get("open_access") or {}).get("is_oa")),
        "authors": list_to_text(authors),
        "institutions": list_to_text(institutions),
        "link": clean_text(entry.get("id")),
    }


def run_openalex(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    headers = openalex_headers(args.email)
    params: dict[str, Any] = {"per-page": args.limit, "sort": args.sort}
    if args.email:
        params["mailto"] = args.email
    query_desc = ""
    detail_context: dict[str, Any] = {}
    if args.doi:
        params["filter"] = f"doi:https://doi.org/{args.doi.lstrip('/')}"
        query_desc = args.doi
    elif args.author:
        author_id, author_detail = resolve_openalex_entity("authors", args.author, args.timeout, args.email)
        params["filter"] = f"authorships.author.id:{author_id}"
        query_desc = args.author
        detail_context["author"] = author_detail
    elif args.institution:
        institution_id, institution_detail = resolve_openalex_entity("institutions", args.institution, args.timeout, args.email)
        params["filter"] = f"authorships.institutions.id:{institution_id}"
        query_desc = args.institution
        detail_context["institution"] = institution_detail
    elif args.query:
        params["search"] = args.query
        query_desc = args.query
    else:
        raise SystemExit("openalex requires --query, --doi, --author, or --institution")
    detail = http_json("GET", f"{OPENALEX_BASE}/works", timeout=args.timeout, params=params, headers=headers)
    rows = [summarize_openalex_work(entry) for entry in detail.get("results", [])]
    if detail_context:
        detail = {**detail_context, "works": detail}
    return rows, {"database": "openalex", "mode": "works", "query": query_desc}, detail


def bindingdb_delimiter(path: Path) -> str:
    return "," if path.suffix.lower() == ".csv" else "\t"


def bindingdb_query_columns(row: dict[str, Any]) -> dict[str, str]:
    return {
        "reactant_set_id": first_nonempty(
            row.get("BindingDB Reactant_set_id"),
            row.get("BindingDB Reactant Set ID"),
            row.get("bindingdb_reactant_set_id"),
            row.get("reactant_set_id"),
        ),
        "ligand_name": first_nonempty(
            row.get("Ligand Name"),
            row.get("ligand_name"),
            row.get("MonomerID"),
            row.get("Monomer ID"),
        ),
        "ligand_smiles": first_nonempty(row.get("Ligand SMILES"), row.get("ligand_smiles"), row.get("SMILES")),
        "uniprot_id": first_nonempty(
            row.get("UniProt (SwissProt) Primary ID of Target Chain"),
            row.get("UniProt (TrEMBL) Primary ID of Target Chain"),
            row.get("UniProt ID"),
            row.get("uniprot_id"),
        ),
        "target_name": first_nonempty(row.get("Target Name"), row.get("target_name")),
        "organism": first_nonempty(
            row.get("Target Source Organism According to Curator or DataSource"),
            row.get("Target Source Organism"),
            row.get("organism"),
        ),
        "pdb_ids": first_nonempty(row.get("PDB ID(s) for Ligand-Target Complex"), row.get("pdb_ids")),
        "pubchem_cid": first_nonempty(row.get("PubChem CID"), row.get("pubchem_cid")),
        "chembl_id": first_nonempty(row.get("ChEMBL ID of Ligand"), row.get("chembl_id")),
        "drugbank_id": first_nonempty(row.get("DrugBank ID of Ligand"), row.get("drugbank_id")),
    }


def bindingdb_local_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=bindingdb_delimiter(path))
        return list(reader)


def bindingdb_row_matches(row: dict[str, Any], args: argparse.Namespace) -> bool:
    columns = bindingdb_query_columns(row)
    if args.uniprot_id and clean_text(args.uniprot_id).upper() != clean_text(columns["uniprot_id"]).upper():
        return False
    if args.compound_name:
        compound_fields = [
            columns["ligand_name"],
            row.get("Ligand Name"),
            row.get("Ligand Synonyms"),
            row.get("Ligand HET ID in PDB"),
        ]
        if not any(contains_text(field, args.compound_name) for field in compound_fields):
            return False
    if args.target_name and not contains_text(columns["target_name"], args.target_name):
        return False
    if args.smiles and clean_text(args.smiles) != clean_text(columns["ligand_smiles"]):
        return False
    return True


def bindingdb_best_affinity(row: dict[str, Any], requested_type: str) -> tuple[str, Optional[float]]:
    fields = [requested_type] + [name for name in BINDINGDB_AFFINITY_FIELDS if name != requested_type]
    for name in fields:
        value = numeric_from_text(row.get(BINDINGDB_AFFINITY_FIELDS[name]))
        if value is not None:
            return name, value
    return requested_type, None


def bindingdb_summary_row(row: dict[str, Any], affinity_type: str, affinity_nm: Optional[float]) -> dict[str, Any]:
    columns = bindingdb_query_columns(row)
    reactant_set_id = columns["reactant_set_id"]
    output = {
        "bindingdb_reactant_set_id": reactant_set_id,
        "ligand_name": columns["ligand_name"],
        "ligand_smiles": columns["ligand_smiles"],
        "target_name": columns["target_name"],
        "uniprot_id": columns["uniprot_id"],
        "affinity_type": affinity_type,
        "affinity_value_nm": "" if affinity_nm is None else affinity_nm,
        "pactivity": "" if affinity_nm is None or affinity_nm <= 0 else -math.log10(affinity_nm * 1e-9),
        "organism": columns["organism"],
        "pdb_ids": columns["pdb_ids"],
        "pubchem_cid": columns["pubchem_cid"],
        "chembl_id": columns["chembl_id"],
        "drugbank_id": columns["drugbank_id"],
        "link": (
            f"https://www.bindingdb.org/rwd/bind/BindingDBReact.jsp?ReactantSetID={reactant_set_id}"
            if reactant_set_id
            else "https://www.bindingdb.org/"
        ),
    }
    return output


def run_bindingdb_local(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    path = Path(args.tsv)
    if not path.exists():
        raise SystemExit(f"BindingDB export not found: {path}")
    matched: list[dict[str, Any]] = []
    detail: list[dict[str, Any]] = []
    for row in bindingdb_local_rows(path):
        if not bindingdb_row_matches(row, args):
            continue
        affinity_type, affinity_nm = bindingdb_best_affinity(row, args.affinity_type)
        if affinity_nm is None or affinity_nm > args.max_nm:
            continue
        matched.append(bindingdb_summary_row(row, affinity_type, affinity_nm))
        detail.append(row)
    matched.sort(key=lambda item: numeric_from_text(item.get("affinity_value_nm")) or float("inf"))
    matched = matched[: args.limit]
    summary = {
        "database": "bindingdb",
        "mode": "local-tsv",
        "query": {
            "uniprot_id": args.uniprot_id,
            "compound_name": args.compound_name,
            "target_name": args.target_name,
            "smiles": args.smiles,
            "affinity_type": args.affinity_type,
            "max_nm": args.max_nm,
            "input": str(path),
        },
    }
    return matched, summary, detail[: args.limit]


def bindingdb_remote_request(method: str, params: dict[str, Any], timeout: int) -> Any:
    req = require_requests()
    response = req.get(f"{BINDINGDB_BASE}/{method}", params=params, timeout=timeout, headers={"Accept": "application/json"})
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "json" in content_type:
        return response.json()
    text = response.text.strip()
    if not text:
        return []
    if text.startswith("<"):
        return text
    return text


def bindingdb_xml_rows(xml_text: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    for child in root:
        row: dict[str, Any] = {}
        for item in child:
            tag = item.tag.split("}", 1)[-1]
            if list(item):
                row[tag] = json.dumps(
                    {sub.tag.split("}", 1)[-1]: clean_text(sub.text) for sub in item},
                    ensure_ascii=False,
                )
            else:
                row[tag] = clean_text(item.text)
        if row:
            rows.append(row)
    return rows


def bindingdb_normalize_remote_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                return value
        return [payload]
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return []
        if text.startswith("<"):
            return bindingdb_xml_rows(text)
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) > 1 and ("\t" in lines[0] or "," in lines[0]):
            dialect = "\t" if "\t" in lines[0] else ","
            return list(csv.DictReader(lines, delimiter=dialect))
        return [{"raw_response": text}]
    return []


def run_bindingdb_remote(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if args.uniprot_id:
        method = "getLigandsByUniprotID"
        params = {
            "uniprot_id": args.uniprot_id,
            "affinity_type": args.affinity_type,
            "affinity_cutoff": args.max_nm,
            "response": "json",
        }
        query_desc = args.uniprot_id
    elif args.compound_name:
        method = "getAffinitiesByCompoundName"
        params = {
            "compound_name": args.compound_name,
            "response": "json",
            "max_results": args.limit,
        }
        query_desc = args.compound_name
    else:
        raise SystemExit("BindingDB remote mode currently requires --uniprot-id or --compound-name. Use --tsv for target-name or SMILES filters.")
    detail = bindingdb_remote_request(method, params, args.timeout)
    raw_rows = bindingdb_normalize_remote_payload(detail)
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        affinity_type, affinity_nm = bindingdb_best_affinity(row, args.affinity_type)
        if affinity_nm is not None and affinity_nm > args.max_nm:
            continue
        rows.append(bindingdb_summary_row(row, affinity_type, affinity_nm))
    rows = rows[: args.limit]
    summary = {
        "database": "bindingdb",
        "mode": "remote",
        "query": query_desc,
        "method": method,
        "affinity_type": args.affinity_type,
        "max_nm": args.max_nm,
    }
    return rows, summary, detail


def run_bindingdb(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    if not any([args.tsv, args.uniprot_id, args.compound_name, args.target_name, args.smiles]):
        raise SystemExit("bindingdb requires one of --tsv, --uniprot-id, --compound-name, --target-name, or --smiles")
    if args.tsv:
        return run_bindingdb_local(args)
    return run_bindingdb_remote(args)


def main() -> None:
    args = parse_args()
    if args.database == "pubchem":
        rows, summary, detail = run_pubchem(args)
    elif args.database == "chembl":
        rows, summary, detail = run_chembl(args)
    elif args.database == "openfda":
        rows, summary, detail = run_openfda(args)
    elif args.database == "clinicaltrials":
        rows, summary, detail = run_clinicaltrials(args)
    elif args.database == "openalex":
        rows, summary, detail = run_openalex(args)
    elif args.database == "bindingdb":
        rows, summary, detail = run_bindingdb(args)
    else:
        raise SystemExit(f"Unsupported database: {args.database}")
    finish(rows, summary, args, detail)


if __name__ == "__main__":
    main()
