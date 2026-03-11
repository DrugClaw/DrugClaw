#!/usr/bin/env python3
"""Summarize and filter variants from a VCF or BCF file."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize and filter variants from a VCF or BCF file")
    parser.add_argument("--input", required=True, help="VCF, VCF.GZ, or BCF file")
    parser.add_argument("--sample", help="Optional sample name. Defaults to the first sample if present")
    parser.add_argument("--pass-only", action="store_true")
    parser.add_argument("--min-vaf", type=float)
    parser.add_argument("--max-vaf", type=float)
    parser.add_argument("--min-depth", type=int)
    parser.add_argument("--include-variant-type", action="append", default=[], help="Filter to variant types such as SNV, INS, DEL, SV")
    parser.add_argument("--exclude-consequence", action="append", default=[], help="Exclude consequences containing these terms")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of rows to export after filtering")
    parser.add_argument("--output", default="variant_report.csv")
    parser.add_argument("--summary", default="variant_report.json")
    return parser.parse_args()


def require_pysam() -> Any:
    try:
        import pysam
    except Exception as exc:
        raise SystemExit(f"variant_report.py requires pysam ({exc})")
    return pysam


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["chrom"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_variant_type(record: Any, alt: str) -> str:
    svtype = clean_text(record.info.get("SVTYPE"))
    if svtype:
        return svtype.upper()
    if alt.startswith("<") and alt.endswith(">"):
        return "SV"
    ref = clean_text(record.ref)
    if len(ref) == 1 and len(alt) == 1:
        return "SNV"
    if len(ref) == len(alt):
        return "MNV" if len(ref) > 1 else "SNV"
    if len(ref) < len(alt):
        return "INS"
    if len(ref) > len(alt):
        return "DEL"
    return "COMPLEX"


def parse_csq_fields(header: Any) -> list[str]:
    try:
        description = header.info["CSQ"].description
    except Exception:
        return []
    marker = "Format:"
    if marker not in description:
        return []
    return [item.strip() for item in description.split(marker, 1)[1].split("|")]


def parse_annotations(record: Any, csq_fields: list[str]) -> tuple[str, str, str]:
    ann = record.info.get("ANN")
    if ann:
        entry = ann[0] if isinstance(ann, tuple) else ann
        parts = clean_text(entry).split("|")
        consequence = parts[1] if len(parts) > 1 else ""
        gene = parts[3] if len(parts) > 3 else ""
        impact = parts[2] if len(parts) > 2 else ""
        return consequence, gene, impact
    csq = record.info.get("CSQ")
    if csq and csq_fields:
        entry = csq[0] if isinstance(csq, tuple) else csq
        parts = clean_text(entry).split("|")
        def at(name: str) -> str:
            try:
                idx = csq_fields.index(name)
            except ValueError:
                return ""
            return parts[idx] if idx < len(parts) else ""
        return at("Consequence"), first_nonempty(at("SYMBOL"), at("Gene")), at("IMPACT")
    consequence = first_nonempty(record.info.get("EFFECT"), record.info.get("Func.refGene"), record.info.get("Funcotator"))
    gene = first_nonempty(record.info.get("GENEINFO"), record.info.get("Gene.refGene"), record.info.get("GENE"))
    impact = clean_text(record.info.get("IMPACT"))
    return clean_text(consequence), clean_text(gene), impact


def get_sample_name(header: Any, requested: Optional[str]) -> str:
    samples = list(header.samples)
    if requested:
        if requested not in samples:
            raise SystemExit(f"Sample not found in VCF: {requested}")
        return requested
    return samples[0] if samples else ""


def info_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return info_number(value[0])
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    return number


def sample_metrics(record: Any, sample_name: str) -> tuple[Optional[float], Optional[int]]:
    if sample_name:
        sample = record.samples.get(sample_name)
        if sample is not None:
            af = info_number(sample.get("AF"))
            dp = sample.get("DP")
            if af is None:
                ad = sample.get("AD")
                if ad and len(ad) >= 2:
                    ref_count = ad[0] or 0
                    alt_count = sum(item or 0 for item in ad[1:])
                    total = ref_count + alt_count
                    if total > 0:
                        af = alt_count / total
            if dp is None:
                dp = record.info.get("DP")
            try:
                depth = int(dp) if dp is not None else None
            except Exception:
                depth = None
            return af, depth
    af = info_number(record.info.get("AF"))
    dp = record.info.get("DP")
    try:
        depth = int(dp) if dp is not None else None
    except Exception:
        depth = None
    return af, depth


def filters_pass(args: argparse.Namespace, row: dict[str, Any]) -> bool:
    if args.pass_only and clean_text(row.get("filter")) not in {"PASS", ".", ""}:
        return False
    vaf = row.get("vaf")
    if args.min_vaf is not None and (vaf is None or vaf < args.min_vaf):
        return False
    if args.max_vaf is not None and (vaf is None or vaf > args.max_vaf):
        return False
    depth = row.get("depth")
    if args.min_depth is not None and (depth is None or depth < args.min_depth):
        return False
    if args.include_variant_type:
        allowed = {item.upper() for item in args.include_variant_type}
        if clean_text(row.get("variant_type")).upper() not in allowed:
            return False
    excluded = [item.lower() for item in args.exclude_consequence if clean_text(item)]
    consequence = clean_text(row.get("consequence")).lower()
    if excluded and any(item in consequence for item in excluded):
        return False
    return True


def row_from_record(record: Any, sample_name: str, csq_fields: list[str]) -> dict[str, Any]:
    alt = clean_text(record.alts[0]) if record.alts else ""
    consequence, gene, impact = parse_annotations(record, csq_fields)
    vaf, depth = sample_metrics(record, sample_name)
    return {
        "chrom": clean_text(record.chrom),
        "pos": int(record.pos),
        "id": clean_text(record.id),
        "ref": clean_text(record.ref),
        "alt": alt,
        "variant_type": normalize_variant_type(record, alt),
        "filter": ";".join(record.filter.keys()) if record.filter.keys() else ".",
        "qual": None if record.qual is None else float(record.qual),
        "sample": sample_name,
        "vaf": vaf,
        "depth": depth,
        "gene": gene,
        "consequence": consequence,
        "impact": impact,
        "svtype": clean_text(record.info.get("SVTYPE")),
    }


def summarize(rows: list[dict[str, Any]], args: argparse.Namespace, sample_name: str, total_records: int) -> dict[str, Any]:
    variant_counts = Counter(clean_text(row.get("variant_type")) for row in rows)
    consequence_counts = Counter(clean_text(row.get("consequence")) for row in rows if clean_text(row.get("consequence")))
    gene_counts = Counter(clean_text(row.get("gene")).split("|")[0] for row in rows if clean_text(row.get("gene")))
    summary = {
        "input": args.input,
        "sample": sample_name,
        "total_records_seen": total_records,
        "records_after_filtering": len(rows),
        "pass_only": bool(args.pass_only),
        "min_vaf": args.min_vaf,
        "max_vaf": args.max_vaf,
        "min_depth": args.min_depth,
        "included_variant_types": args.include_variant_type,
        "excluded_consequence_terms": args.exclude_consequence,
        "variant_type_counts": dict(variant_counts),
        "top_consequences": consequence_counts.most_common(10),
        "top_genes": gene_counts.most_common(10),
        "output": args.output,
    }
    vafs = [row["vaf"] for row in rows if row.get("vaf") is not None]
    depths = [row["depth"] for row in rows if row.get("depth") is not None]
    if vafs:
        summary["vaf_range"] = [min(vafs), max(vafs)]
    if depths:
        summary["depth_range"] = [min(depths), max(depths)]
    return summary


def run(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pysam = require_pysam()
    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"Variant file not found: {path}")
    handle = pysam.VariantFile(str(path))
    sample_name = get_sample_name(handle.header, args.sample)
    csq_fields = parse_csq_fields(handle.header)
    rows: list[dict[str, Any]] = []
    total_records = 0
    for record in handle:
        total_records += 1
        row = row_from_record(record, sample_name, csq_fields)
        if not filters_pass(args, row):
            continue
        rows.append(row)
        if args.limit > 0 and len(rows) >= args.limit:
            break
    return rows, summarize(rows, args, sample_name, total_records)


def main() -> None:
    args = parse_args()
    rows, summary = run(args)
    write_csv(Path(args.output), rows)
    write_json(Path(args.summary), summary)
    print(json.dumps({"output": args.output, "summary": args.summary, "result_count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
