#!/usr/bin/env python3
"""Profile an AnnData h5ad dataset for quick single-cell triage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--cell-type-column")
    parser.add_argument("--group-column", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    import anndata as ad

    adata = ad.read_h5ad(args.input)
    rows: list[dict[str, Any]] = [
        {"metric": "n_obs", "value": int(adata.n_obs)},
        {"metric": "n_vars", "value": int(adata.n_vars)},
        {"metric": "obs_columns", "value": ",".join(map(str, adata.obs.columns.tolist()))},
        {"metric": "var_columns", "value": ",".join(map(str, adata.var.columns.tolist()))},
    ]

    if args.cell_type_column and args.cell_type_column in adata.obs.columns:
        counts = adata.obs[args.cell_type_column].astype(str).value_counts().head(20)
        rows.extend(
            {
                "metric": f"cell_type::{name}",
                "value": int(count),
            }
            for name, count in counts.items()
        )

    group_summaries: dict[str, list[dict[str, Any]]] = {}
    for column in args.group_column:
        if column not in adata.obs.columns:
            continue
        counts = adata.obs[column].astype(str).value_counts().head(20)
        group_summaries[column] = [{"name": name, "count": int(count)} for name, count in counts.items()]
        rows.extend(
            {
                "metric": f"group::{column}::{name}",
                "value": int(count),
            }
            for name, count in counts.items()
        )

    out_df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    summary = {
        "input_path": str(args.input),
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "obs_columns": list(map(str, adata.obs.columns.tolist())),
        "var_columns": list(map(str, adata.var.columns.tolist())),
        "cell_type_column": args.cell_type_column if args.cell_type_column in adata.obs.columns else None,
        "group_summaries": group_summaries,
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
