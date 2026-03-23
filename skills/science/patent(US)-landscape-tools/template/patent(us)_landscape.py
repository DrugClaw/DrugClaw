#!/usr/bin/env python3
"""Drug-patent landscape analysis from USPTO PatentsView and FDA Orange Book."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - optional at runtime
    requests = None

PATENTSVIEW_BASE = "https://api.patentsview.org/patents/query"
ORANGEBOOK_API = "https://api.fda.gov/drug/drugsfda.json"

CLAIM_PATTERNS = [
    (r"composition|compound|molecule|chemical.entity|NCE|novel.compound|active.ingredient", "NCE / composition-of-matter"),
    (r"formulation|dosage.form|tablet|capsule|injection|sustained.release|nanoparticle|liposom", "formulation"),
    (r"method.of.treat|therapeutic.use|method.of.use|treating.*disease|for.the.treatment", "method-of-use"),
    (r"polymorph|crystal.form|salt|co.?crystal|hydrate|solvate|amorphous", "polymorph / salt form"),
    (r"combination|co.?administration|synergistic|adjunct", "combination"),
    (r"antibody|biologic|recombinant|fusion.protein|monoclonal", "biologic"),
    (r"diagnos|biomarker|assay|companion.diagnostic|imaging.agent", "diagnostic"),
    (r"device|deliver|applicator|inhaler|auto.?injector", "device / delivery"),
    (r"process|synthesis|manufactur|preparation.of|method.of.making", "process / manufacturing"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drug-patent landscape search, classification, and expiry estimation"
    )
    parser.add_argument("--query", required=True, help="Drug name, target, mechanism, or keyword phrase")
    parser.add_argument("--mode", choices=["landscape", "expiry-timeline"], default="landscape")
    parser.add_argument("--cpc-filter", help="CPC subclass filter, e.g. A61K, A61P, C07D")
    parser.add_argument("--date-from", help="Earliest filing date YYYY-MM-DD")
    parser.add_argument("--date-to", help="Latest filing date YYYY-MM-DD")
    parser.add_argument("--max-results", type=int, default=200)
    parser.add_argument("--orange-book-query", help="Drug name for FDA Orange Book cross-reference")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", default="patents/patent_landscape.csv")
    parser.add_argument("--summary", default="patents/patent_landscape.json")
    parser.add_argument("--brief", help="Optional markdown brief output path")
    return parser.parse_args()


def require_requests():
    if requests is None:
        raise SystemExit("patent_landscape.py requires the requests library")
    return requests


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def classify_claim_type(title: str, abstract: str) -> str:
    text = f"{title} {abstract}".lower()
    for pattern, label in CLAIM_PATTERNS:
        if re.search(pattern, text):
            return label
    return "unclassified"


# ---------------------------------------------------------------------------
# PatentsView
# ---------------------------------------------------------------------------

def query_patentsview(query: str, max_results: int, cpc_filter: str | None,
                      date_from: str | None, date_to: str | None,
                      timeout: int) -> list[dict[str, Any]]:
    req = require_requests()
    criteria: list[dict] = [{"_text_any": {"patent_abstract": query}}]
    if cpc_filter:
        criteria.append({"_begins": {"cpc_subgroup_id": cpc_filter}})
    if date_from:
        criteria.append({"_gte": {"app_date": date_from}})
    if date_to:
        criteria.append({"_lte": {"app_date": date_to}})

    q = {"_and": criteria} if len(criteria) > 1 else criteria[0]
    payload = {
        "q": json.dumps(q),
        "f": json.dumps([
            "patent_number", "patent_title", "patent_date", "patent_abstract",
            "patent_type", "app_date", "app_number",
            "assignee_organization", "assignee_country",
            "cpc_subgroup_id", "cpc_subgroup_title",
        ]),
        "o": json.dumps({"page": 1, "per_page": min(max_results, 1000)}),
    }
    resp = req.get(PATENTSVIEW_BASE, params=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    patents: list[dict[str, Any]] = []
    for pat in data.get("patents") or []:
        assignees = pat.get("assignees") or [{}]
        org = clean_text(assignees[0].get("assignee_organization")) if assignees else ""
        country = clean_text(assignees[0].get("assignee_country")) if assignees else ""

        cpcs = pat.get("cpcs") or [{}]
        cpc_id = clean_text(cpcs[0].get("cpc_subgroup_id")) if cpcs else ""

        title = clean_text(pat.get("patent_title"))
        abstract = clean_text(pat.get("patent_abstract"))[:500]
        filing_date = clean_text(pat.get("app_date"))
        grant_date = clean_text(pat.get("patent_date"))
        app_number = clean_text(pat.get("app_number"))

        expiry_year = None
        if filing_date and len(filing_date) >= 4:
            try:
                expiry_year = int(filing_date[:4]) + 20
            except ValueError:
                pass

        patents.append({
            "patent_number": clean_text(pat.get("patent_number")),
            "title": title,
            "filing_date": filing_date,
            "grant_date": grant_date,
            "patent_type": clean_text(pat.get("patent_type")),
            "app_number": app_number,
            "assignee": org,
            "country": country,
            "cpc": cpc_id,
            "claim_type_guess": classify_claim_type(title, abstract),
            "estimated_expiry_year": expiry_year,
            "abstract_snippet": abstract[:300],
        })
    return patents


# ---------------------------------------------------------------------------
# Orange Book
# ---------------------------------------------------------------------------

def query_orange_book(drug_name: str, timeout: int) -> list[dict[str, Any]]:
    req = require_requests()
    params = {
        "search": f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"',
        "limit": 10,
    }
    try:
        resp = req.get(ORANGEBOOK_API, params=params, timeout=timeout)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        openfda = item.get("openfda", {})
        for prod in item.get("products") or []:
            results.append({
                "brand_name": "; ".join(openfda.get("brand_name", [])),
                "generic_name": "; ".join(openfda.get("generic_name", [])),
                "nda_number": clean_text(prod.get("application_number")),
                "dosage_form": clean_text(prod.get("dosage_form")),
                "route": clean_text(prod.get("route")),
                "marketing_status": clean_text(prod.get("marketing_status")),
            })
    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_landscape(patents: list[dict[str, Any]]) -> dict[str, Any]:
    assignee_counts = Counter(p["assignee"] for p in patents if p["assignee"])
    country_counts = Counter(p["country"] for p in patents if p["country"])
    claim_type_counts = Counter(p.get("claim_type_guess", "") for p in patents)

    year_counts: dict[str, int] = {}
    for p in patents:
        d = p.get("filing_date") or ""
        if len(d) >= 4:
            year_counts[d[:4]] = year_counts.get(d[:4], 0) + 1

    family_groups: dict[str, list[str]] = {}
    for p in patents:
        app = (p.get("app_number") or "")[:8]
        if app:
            family_groups.setdefault(app, []).append(p["patent_number"])

    expiry_years = [p["estimated_expiry_year"] for p in patents if p.get("estimated_expiry_year")]
    return {
        "total_patents": len(patents),
        "estimated_families": len(family_groups),
        "claim_type_distribution": dict(claim_type_counts),
        "top_assignees": [{"assignee": a, "count": c} for a, c in assignee_counts.most_common(15)],
        "country_distribution": dict(country_counts.most_common(10)),
        "filing_trend_by_year": dict(sorted(year_counts.items())),
        "expiry_window": {
            "earliest": min(expiry_years) if expiry_years else None,
            "latest": max(expiry_years) if expiry_years else None,
        },
    }


# ---------------------------------------------------------------------------
# Brief renderer
# ---------------------------------------------------------------------------

def render_brief(query: str, analysis: dict[str, Any],
                 orange_book: list[dict[str, Any]] | None) -> str:
    lines = ["# Drug-Patent Landscape Brief", ""]
    lines.append(f"**Query**: {query}")
    lines.append(f"**Retrieved**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Source**: USPTO PatentsView (US grants only)")
    lines.append(f"**Total patents**: {analysis['total_patents']}")
    lines.append(f"**Estimated families**: {analysis['estimated_families']}")
    lines.append("")

    lines.append("## Claim Type Distribution")
    for ct, cnt in sorted(analysis["claim_type_distribution"].items(), key=lambda x: -x[1]):
        lines.append(f"- {ct}: {cnt}")
    lines.append("")

    lines.append("## Top Assignees")
    lines.append("| Assignee | Patents |")
    lines.append("|----------|---------|")
    for a in analysis["top_assignees"][:15]:
        lines.append(f"| {a['assignee']} | {a['count']} |")
    lines.append("")

    lines.append("## Filing Trend")
    for yr, cnt in sorted(analysis["filing_trend_by_year"].items()):
        lines.append(f"- {yr}: {cnt}")
    lines.append("")

    ew = analysis.get("expiry_window", {})
    if ew.get("earliest"):
        lines.append("## Expiry Window (estimated)")
        lines.append(f"- Earliest: {ew['earliest']}")
        lines.append(f"- Latest: {ew['latest']}")
        lines.append("- Note: baseline filing+20yr only; PTE/PTA/SPC not computed.")
        lines.append("")

    if orange_book:
        lines.append("## Orange Book Cross-Reference")
        for ob in orange_book[:5]:
            lines.append(f"- {ob.get('brand_name', '')} / {ob.get('generic_name', '')} "
                         f"— NDA: {ob.get('nda_number', '')}, "
                         f"Form: {ob.get('dosage_form', '')}, "
                         f"Status: {ob.get('marketing_status', '')}")
        lines.append("")

    lines.append("## Caveats")
    lines.append("- PatentsView covers US granted patents only; EP/WO/CN/JP not queried.")
    lines.append("- Claim-type classification is heuristic from title/abstract, not claim text.")
    lines.append("- Expiry estimates do not account for PTE, PTA, SPC, or terminal disclaimers.")
    lines.append("- This is research intelligence, not freedom-to-operate legal counsel.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict[str, Any]], path: str) -> None:
    if not rows:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("no_results\n")
        return
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def write_json(path: str, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    print(f"Querying PatentsView: {args.query}")
    patents = query_patentsview(
        args.query, args.max_results, args.cpc_filter,
        args.date_from, args.date_to, args.timeout,
    )
    print(f"  Retrieved {len(patents)} patents")

    if args.mode == "expiry-timeline":
        patents.sort(key=lambda p: p.get("estimated_expiry_year") or 9999)

    analysis = analyze_landscape(patents)

    orange_book = None
    if args.orange_book_query:
        print(f"Cross-referencing Orange Book: {args.orange_book_query}")
        orange_book = query_orange_book(args.orange_book_query, args.timeout)
        print(f"  Orange Book entries: {len(orange_book)}")

    write_csv(patents, args.output)

    summary: dict[str, Any] = {
        "query": args.query,
        "mode": args.mode,
        "retrieval_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cpc_filter": args.cpc_filter,
        "date_range": {"from": args.date_from, "to": args.date_to},
        **analysis,
        "output": args.output,
    }
    if orange_book:
        summary["orange_book"] = orange_book
    write_json(args.summary, summary)

    if args.brief:
        md = render_brief(args.query, analysis, orange_book)
        Path(args.brief).parent.mkdir(parents=True, exist_ok=True)
        Path(args.brief).write_text(md, encoding="utf-8")
        print(f"Brief: {args.brief}")

    print(json.dumps({"output": args.output, "summary": args.summary, "result_count": len(patents)}, ensure_ascii=False))


if __name__ == "__main__":
    main()