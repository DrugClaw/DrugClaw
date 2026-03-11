#!/usr/bin/env python3
"""Inspect BAM or CRAM files and report region-level counts with pysam."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_region(region: str) -> tuple[str, int | None, int | None]:
    if ":" not in region:
        return region, None, None
    contig, span = region.split(":", 1)
    start_s, end_s = span.replace(",", "").split("-", 1)
    return contig, max(int(start_s) - 1, 0), int(end_s)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bam", required=True, type=Path)
    parser.add_argument("--region", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    import pysam

    mode = "rc" if args.bam.suffix.lower() == ".cram" else "rb"
    rows: list[dict[str, Any]] = []
    with pysam.AlignmentFile(args.bam, mode) as handle:
        stats = handle.get_index_statistics() if handle.has_index() else []
        mapped = sum(item.mapped for item in stats)
        unmapped = sum(item.unmapped for item in stats)
        rows.append({"metric": "mapped_reads", "value": int(mapped)})
        rows.append({"metric": "unmapped_reads", "value": int(unmapped)})
        rows.append({"metric": "references", "value": len(handle.references)})
        rows.append({"metric": "has_index", "value": bool(handle.has_index())})
        region_rows = []
        for region in args.region:
            contig, start, end = parse_region(region)
            count = handle.count(contig=contig, start=start, end=end)
            region_rows.append({"region": region, "read_count": int(count)})

    out_df = pd.DataFrame(region_rows or [{"region": "all", "read_count": int(mapped)}])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    summary = {
        "input_path": str(args.bam),
        "mapped_reads": int(mapped),
        "unmapped_reads": int(unmapped),
        "references": int(rows[2]["value"]),
        "has_index": bool(rows[3]["value"]),
        "regions": region_rows,
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
