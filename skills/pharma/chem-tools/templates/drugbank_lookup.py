#!/usr/bin/env python3
"""Search DrugBank locally or online, export structures, and summarize properties."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    import requests
except Exception:  # pragma: no cover - optional at runtime
    requests = None


COLUMN_ALIASES = {
    "drugbank_id": ["drugbank_id", "drugbank id", "drugbank-id", "drugbank primary id", "primary_drugbank_id"],
    "name": ["name", "drug_name", "drug name", "common_name"],
    "description": ["description"],
    "indication": ["indication"],
    "pharmacodynamics": ["pharmacodynamics"],
    "mechanism_of_action": ["mechanism_of_action", "mechanism of action", "mechanism-of-action"],
    "smiles": ["smiles", "canonical_smiles", "calculated_smiles"],
    "inchi": ["inchi"],
    "inchikey": ["inchikey", "inchi_key", "inchi-key"],
    "cas_number": ["cas_number", "cas number", "cas-number", "cas"],
    "formula": ["formula", "molecular_formula", "molecular formula"],
    "molecular_weight": ["molecular_weight", "molecular weight", "average_mass", "monoisotopic_mass", "monisotopic_mass"],
    "drug_type": ["drug_type", "type"],
    "groups": ["groups", "group"],
    "synonyms": ["synonyms", "synonym"],
    "brand_names": ["brand_names", "brand names", "brands", "brand_name"],
    "pubchem_cid": ["pubchem_cid", "pubchem cid", "pubchem compound id", "pubchem compound identifier"],
    "chembl_id": ["chembl_id", "chembl", "chembl id"],
    "sdf_path": ["sdf_path", "structure_path", "sdf file", "structure_file"],
    "mol_path": ["mol_path", "mol_file", "mol2_path", "mol_path"],
}
LIST_FIELDS = {"groups", "synonyms", "brand_names", "atc_codes", "targets"}
TEXT_FIELDS = [
    "drugbank_id",
    "name",
    "description",
    "indication",
    "pharmacodynamics",
    "mechanism_of_action",
    "smiles",
    "inchi",
    "inchikey",
    "cas_number",
    "formula",
    "molecular_weight",
    "drug_type",
    "pubchem_cid",
    "chembl_id",
    "sdf_path",
    "mol_path",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search DrugBank exports or the online discovery API")
    parser.add_argument("--mode", default="auto", choices=["auto", "local", "online"])
    parser.add_argument("--catalog", help="DrugBank CSV/TSV/JSON/XML export path")
    parser.add_argument("--query", help="Drug name, synonym, or brand name")
    parser.add_argument("--drugbank-id", help="DrugBank accession such as DB00619")
    parser.add_argument("--api-key", help="DrugBank API key; can also come from DRUGBANK_API_KEY")
    parser.add_argument("--api-token", help="DrugBank bearer token; can also come from DRUGBANK_API_TOKEN")
    parser.add_argument("--api-base-url", help="Discovery API base URL; defaults by auth method")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", default="drugbank_hits.csv")
    parser.add_argument("--summary", default="drugbank_summary.json")
    parser.add_argument("--top-hit-json", help="Write the best match as JSON")
    parser.add_argument("--smiles-output", help="Write top-hit SMILES to a .smi file")
    parser.add_argument("--sdf-output", help="Write top-hit structure to an SDF file when SMILES or structure paths are available")
    parser.add_argument("--copy-structure", action="store_true", default=False, help="Prefer copying an existing structure path when present")
    return parser.parse_args()



def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()



def split_multi(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    separators = [";", "|", "||"]
    for separator in separators:
        if separator in text:
            return [item.strip() for item in text.split(separator) if item.strip()]
    return [text]



def unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = clean_text(value)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(clean)
    return output



def extract_texts(value: Any, *, preferred_keys: tuple[str, ...] = ("name", "value", "title", "term", "id", "drugbank_id")) -> list[str]:
    results: list[str] = []
    if value is None:
        return results
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = clean_text(value.get(key))
            if candidate:
                results.append(candidate)
        if not results:
            for candidate in value.values():
                results.extend(extract_texts(candidate, preferred_keys=preferred_keys))
        return unique_texts(results)
    if isinstance(value, list):
        for item in value:
            results.extend(extract_texts(item, preferred_keys=preferred_keys))
        return unique_texts(results)
    clean = clean_text(value)
    return [clean] if clean else []



def first_nonempty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""



def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {key: "" for key in TEXT_FIELDS}
    for logical, aliases in COLUMN_ALIASES.items():
        for key, value in raw.items():
            if key.lower().strip() in aliases:
                normalized[logical] = value
                break
    for key in LIST_FIELDS:
        normalized[key] = split_multi(raw.get(key, normalized.get(key)))
    for key in TEXT_FIELDS:
        normalized[key] = clean_text(normalized.get(key) or raw.get(key))
    if not normalized.get("drugbank_id"):
        for key, value in raw.items():
            text = clean_text(value).upper()
            if text.startswith("DB") and len(text) >= 7:
                normalized["drugbank_id"] = text
                break
    return normalized



def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]



def first_text(parent: ET.Element, path: str) -> str:
    node = parent.find(path)
    if node is None or node.text is None:
        return ""
    return node.text.strip()



def collect_texts(parent: ET.Element, path: str) -> list[str]:
    values: list[str] = []
    for node in parent.findall(path):
        if node.text and node.text.strip():
            values.append(node.text.strip())
    return values



def property_map(drug: ET.Element, container_name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for prop in drug.findall(f"{{*}}{container_name}/{{*}}property"):
        kind = first_text(prop, "{*}kind").lower().replace(" ", "_")
        value = first_text(prop, "{*}value")
        if kind and value:
            values[kind] = value
    return values



def external_identifier_map(drug: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in drug.findall("{*}external-identifiers/{*}external-identifier"):
        resource = first_text(item, "{*}resource").lower()
        identifier = first_text(item, "{*}identifier")
        if resource and identifier:
            values[resource] = identifier
    return values



def parse_drugbank_xml(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    context = ET.iterparse(path, events=("end",))
    for _, element in context:
        if strip_ns(element.tag) != "drug":
            continue
        ids = []
        for item in element.findall("{*}drugbank-id"):
            text = clean_text(item.text)
            if text:
                ids.append(text)
        calculated = property_map(element, "calculated-properties")
        experimental = property_map(element, "experimental-properties")
        external_ids = external_identifier_map(element)
        record = {
            "drugbank_id": ids[0] if ids else "",
            "name": first_text(element, "{*}name"),
            "description": first_text(element, "{*}description"),
            "indication": first_text(element, "{*}indication"),
            "pharmacodynamics": first_text(element, "{*}pharmacodynamics"),
            "mechanism_of_action": first_text(element, "{*}mechanism-of-action"),
            "smiles": calculated.get("smiles", ""),
            "inchi": calculated.get("inchi", ""),
            "inchikey": calculated.get("inchi_key", calculated.get("inchi-key", "")),
            "cas_number": first_text(element, "{*}cas-number"),
            "formula": calculated.get("molecular_formula", experimental.get("molecular_formula", "")),
            "molecular_weight": experimental.get("molecular_weight", calculated.get("molecular_weight", "")),
            "drug_type": clean_text(element.get("type")),
            "groups": collect_texts(element, "{*}groups/{*}group"),
            "synonyms": collect_texts(element, "{*}synonyms/{*}synonym"),
            "brand_names": collect_texts(element, "{*}brands/{*}brand/{*}name"),
            "pubchem_cid": external_ids.get("pubchem compound", ""),
            "chembl_id": external_ids.get("chembl", ""),
            "atc_codes": [node.get("code", "") for node in element.findall("{*}atc-codes/{*}atc-code") if node.get("code")],
            "targets": [first_text(target, "{*}name") for target in element.findall("{*}targets/{*}target") if first_text(target, "{*}name")],
        }
        rows.append(record)
        element.clear()
    if not rows:
        raise SystemExit(f"No drug records parsed from {path}")
    return rows



def load_catalog(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return parse_drugbank_xml(path)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("rows") or payload.get("drugs") or payload.get("records") or []
        return [normalize_record(item) for item in payload]
    frame = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    return [normalize_record(row.to_dict()) for _, row in frame.iterrows()]



def require_requests() -> None:
    if requests is None:
        raise SystemExit("requests is required for online DrugBank lookup")



def resolve_api_settings(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    api_key = clean_text(args.api_key) or clean_text(os.environ.get("DRUGBANK_API_KEY"))
    api_token = clean_text(args.api_token) or clean_text(os.environ.get("DRUGBANK_API_TOKEN"))
    if not api_key and not api_token:
        raise SystemExit("Online DrugBank lookup requires --api-key, --api-token, DRUGBANK_API_KEY, or DRUGBANK_API_TOKEN")
    if api_token:
        base_url = clean_text(args.api_base_url) or clean_text(os.environ.get("DRUGBANK_API_BASE_URL")) or "https://api-js.drugbank.com/discovery/v1"
        return base_url.rstrip("/"), {"Authorization": f"Bearer {api_token}"}
    base_url = clean_text(args.api_base_url) or clean_text(os.environ.get("DRUGBANK_API_BASE_URL")) or "https://api.drugbank.com/discovery/v1"
    return base_url.rstrip("/"), {"Authorization": api_key}



def resolve_mode(args: argparse.Namespace) -> str:
    if args.mode != "auto":
        return args.mode
    if args.catalog:
        return "local"
    if clean_text(args.api_key) or clean_text(args.api_token) or clean_text(os.environ.get("DRUGBANK_API_KEY")) or clean_text(os.environ.get("DRUGBANK_API_TOKEN")):
        return "online"
    raise SystemExit("Provide --catalog for local lookup or DrugBank API credentials for online lookup")



def request_json(url: str, *, headers: dict[str, str], params: Optional[dict[str, Any]] = None) -> Any:
    require_requests()
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        body = response.text[:1000].strip()
        raise SystemExit(f"DrugBank API request failed: HTTP {response.status_code} for {url}\n{body}")
    return response.json()



def calculated_property_map_from_payload(raw: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in ["calculated_properties", "experimental_properties", "properties"]:
        payload = raw.get(key)
        if isinstance(payload, dict):
            for inner_key, inner_value in payload.items():
                text = clean_text(inner_value)
                if text:
                    values[inner_key.lower().replace(" ", "_")] = text
        elif isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                kind = first_nonempty(item.get("kind"), item.get("name"), item.get("property"), item.get("title")).lower().replace(" ", "_")
                value = first_nonempty(item.get("value"), item.get("text"), item.get("content"))
                if kind and value:
                    values[kind] = value
    return values



def external_id_map_from_payload(raw: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    payload = raw.get("external_identifiers") or raw.get("external_ids") or raw.get("identifiers")
    if isinstance(payload, dict):
        for key, value in payload.items():
            text = clean_text(value)
            if text:
                values[key.lower()] = text
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            resource = first_nonempty(item.get("resource"), item.get("source"), item.get("name"), item.get("kind")).lower()
            identifier = first_nonempty(item.get("identifier"), item.get("value"), item.get("id"))
            if resource and identifier:
                values[resource] = identifier
    return values



def normalize_online_record(raw: dict[str, Any]) -> dict[str, Any]:
    calc = calculated_property_map_from_payload(raw)
    external = external_id_map_from_payload(raw)
    groups = extract_texts(raw.get("groups"))
    synonyms = extract_texts(raw.get("synonyms"))
    brand_names = unique_texts(
        extract_texts(raw.get("brand_names"))
        + extract_texts(raw.get("brands"))
        + extract_texts(raw.get("international_brands"))
        + extract_texts(raw.get("products"), preferred_keys=("name", "brand_name", "product_name", "display_name"))
    )
    targets = extract_texts(raw.get("targets"), preferred_keys=("name", "gene_name", "id"))
    pubchem_cid = first_nonempty(
        raw.get("pubchem_cid"),
        external.get("pubchem compound"),
        external.get("pubchem cid"),
        external.get("pubchem compound id"),
    )
    chembl_id = first_nonempty(raw.get("chembl_id"), external.get("chembl"), external.get("chembl id"))
    molecular_weight = first_nonempty(
        raw.get("molecular_weight"),
        raw.get("average_mass"),
        raw.get("monoisotopic_mass"),
        calc.get("molecular_weight"),
        calc.get("average_mass"),
    )
    return {
        "drugbank_id": first_nonempty(raw.get("drugbank_id"), raw.get("id")),
        "name": first_nonempty(raw.get("name"), raw.get("drug_name")),
        "description": first_nonempty(raw.get("description"), raw.get("simple_description"), raw.get("clinical_description")),
        "indication": clean_text(raw.get("indication")),
        "pharmacodynamics": clean_text(raw.get("pharmacodynamics")),
        "mechanism_of_action": first_nonempty(raw.get("mechanism_of_action"), raw.get("mechanism-of-action")),
        "smiles": first_nonempty(raw.get("smiles"), calc.get("smiles"), calc.get("canonical_smiles")),
        "inchi": first_nonempty(raw.get("inchi"), calc.get("inchi")),
        "inchikey": first_nonempty(raw.get("inchikey"), raw.get("inchi_key"), calc.get("inchi_key"), calc.get("inchi-key")),
        "cas_number": first_nonempty(raw.get("cas_number"), raw.get("cas")),
        "formula": first_nonempty(raw.get("formula"), raw.get("molecular_formula"), calc.get("molecular_formula")),
        "molecular_weight": clean_text(molecular_weight),
        "drug_type": first_nonempty(raw.get("type"), raw.get("drug_type")),
        "pubchem_cid": clean_text(pubchem_cid),
        "chembl_id": clean_text(chembl_id),
        "sdf_path": clean_text(raw.get("sdf_path")),
        "mol_path": clean_text(raw.get("mol_path")),
        "groups": groups,
        "synonyms": synonyms,
        "brand_names": brand_names,
        "atc_codes": extract_texts(raw.get("atc_codes"), preferred_keys=("code", "name", "value")),
        "targets": targets,
    }



def extract_online_records(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["drugs", "results", "data", "items"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []



def fetch_online_drug(base_url: str, headers: dict[str, str], drugbank_id: str) -> Optional[dict[str, Any]]:
    payload = request_json(f"{base_url}/drugs/{drugbank_id}", headers=headers)
    if payload is None:
        return None
    records = extract_online_records(payload)
    if not records:
        return None
    return records[0]



def search_score(record: dict[str, Any], *, query: str, drugbank_id: str) -> float:
    score = 0.0
    query_clean = query.strip().lower()
    id_clean = drugbank_id.strip().upper()
    if id_clean and record.get("drugbank_id", "").upper() == id_clean:
        score += 100.0
    if not query_clean:
        return score
    name = record.get("name", "").lower()
    if name == query_clean:
        score += 90.0
    elif query_clean in name:
        score += 55.0
    description_blob = " ".join([record.get("description", ""), record.get("indication", ""), record.get("mechanism_of_action", "")]).lower()
    if query_clean and query_clean in description_blob:
        score += 5.0
    for synonym in record.get("synonyms", []):
        synonym_clean = synonym.lower()
        if synonym_clean == query_clean:
            score += 80.0
        elif query_clean in synonym_clean:
            score += 40.0
    for brand in record.get("brand_names", []):
        brand_clean = brand.lower()
        if brand_clean == query_clean:
            score += 70.0
        elif query_clean in brand_clean:
            score += 35.0
    if query_clean and query_clean == record.get("drugbank_id", "").lower():
        score += 95.0
    return score



def search_online(args: argparse.Namespace) -> tuple[list[tuple[float, dict[str, Any]]], int, str]:
    base_url, headers = resolve_api_settings(args)
    if args.drugbank_id:
        detail = fetch_online_drug(base_url, headers, args.drugbank_id.upper())
        if detail is None:
            return [], 0, base_url
        record = normalize_online_record(detail)
        return [(100.0, record)], 1, base_url
    payload = request_json(f"{base_url}/drugs", headers=headers, params={"q": args.query})
    raw_records = extract_online_records(payload)
    scored: list[tuple[float, dict[str, Any]]] = []
    for raw in raw_records:
        record = normalize_online_record(raw)
        score = search_score(record, query=args.query or "", drugbank_id="")
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], item[1].get("name", ""), item[1].get("drugbank_id", "")))
    enriched: list[tuple[float, dict[str, Any]]] = []
    for score, record in scored[: max(1, args.limit)]:
        drugbank_id = clean_text(record.get("drugbank_id"))
        if drugbank_id:
            detail = fetch_online_drug(base_url, headers, drugbank_id)
            if detail is not None:
                enriched_record = normalize_online_record(detail)
                for key, value in record.items():
                    if key not in enriched_record or not enriched_record[key]:
                        enriched_record[key] = value
                record = enriched_record
        enriched.append((score, record))
    return enriched, len(scored), base_url



def serialize_record(record: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if record is None:
        return None
    output: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, list):
            output[key] = "; ".join(item for item in value if clean_text(item))
        else:
            output[key] = clean_text(value)
    return output



def generate_sdf_from_smiles(smiles: str, dest: Path) -> None:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise SystemExit(f"Top hit SMILES could not be parsed: {smiles}")
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    AllChem.MMFFOptimizeMolecule(mol)
    writer = Chem.SDWriter(str(dest))
    writer.write(mol)
    writer.close()



def maybe_export_structure(record: dict[str, Any], *, sdf_output: str | None, smiles_output: str | None, copy_structure: bool, catalog_dir: Path | None) -> None:
    if smiles_output:
        smiles = clean_text(record.get("smiles"))
        if not smiles:
            raise SystemExit("Top hit does not expose SMILES; cannot write --smiles-output")
        output = Path(smiles_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(smiles + "\n", encoding="utf-8")
    if not sdf_output:
        return
    output = Path(sdf_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if copy_structure and catalog_dir is not None:
        for field in ["sdf_path", "mol_path"]:
            candidate = clean_text(record.get(field))
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = catalog_dir / path
            if path.exists():
                shutil.copy2(path, output)
                return
    smiles = clean_text(record.get("smiles"))
    if smiles:
        generate_sdf_from_smiles(smiles, output)
        return
    raise SystemExit("Top hit does not provide a copyable structure path or SMILES for SDF export")



def main() -> int:
    args = parse_args()
    if not args.query and not args.drugbank_id:
        raise SystemExit("Provide --query or --drugbank-id")
    mode = resolve_mode(args)
    catalog_dir: Path | None = None
    api_base_url = ""
    if mode == "local":
        if not args.catalog:
            raise SystemExit("Local DrugBank lookup requires --catalog")
        catalog = Path(args.catalog).expanduser().resolve()
        if not catalog.exists():
            raise SystemExit(f"Catalog not found: {catalog}")
        catalog_dir = catalog.parent
        records = load_catalog(catalog)
        scored = []
        for record in records:
            score = search_score(record, query=args.query or "", drugbank_id=args.drugbank_id or "")
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1].get("name", ""), item[1].get("drugbank_id", "")))
        total_hits = len(scored)
        limited = scored[: max(1, args.limit)]
    else:
        limited, total_hits, api_base_url = search_online(args)
        catalog = None

    output_rows = [serialize_record(record) | {"match_score": round(score, 3)} for score, record in limited]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_rows:
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in output_rows for key in row.keys()}))
            writer.writeheader()
            writer.writerows(output_rows)
    else:
        pd.DataFrame([], columns=["drugbank_id", "name", "match_score"]).to_csv(output, index=False)

    top_hit = limited[0][1] if limited else None
    if top_hit and args.top_hit_json:
        top_hit_path = Path(args.top_hit_json)
        top_hit_path.parent.mkdir(parents=True, exist_ok=True)
        top_hit_path.write_text(json.dumps(top_hit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if top_hit and (args.sdf_output or args.smiles_output):
        maybe_export_structure(top_hit, sdf_output=args.sdf_output, smiles_output=args.smiles_output, copy_structure=args.copy_structure, catalog_dir=catalog_dir)

    summary = {
        "mode": mode,
        "catalog": str(catalog) if mode == "local" and catalog is not None else "",
        "api_base_url": api_base_url,
        "query": args.query or "",
        "drugbank_id": args.drugbank_id or "",
        "total_hits": total_hits,
        "returned_hits": len(limited),
        "top_hit": serialize_record(top_hit),
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved hits: {output}")
    print(f"saved summary: {summary_path}")
    if args.top_hit_json and top_hit:
        print(f"saved top hit: {args.top_hit_json}")
    if args.smiles_output and top_hit:
        print(f"saved smiles: {args.smiles_output}")
    if args.sdf_output and top_hit:
        print(f"saved structure: {args.sdf_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
