#!/usr/bin/env python3
"""Create an interactive Plotly chart and save it as HTML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise ValueError(f"unsupported input format: {path}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=["scatter", "line", "bar", "histogram", "box"])
    parser.add_argument("--x-column", required=True)
    parser.add_argument("--y-column")
    parser.add_argument("--color-column")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    df = read_table(args.input)

    common = {"data_frame": df, "x": args.x_column, "color": args.color_column}
    if args.kind == "scatter":
        fig = px.scatter(y=args.y_column, **common)
    elif args.kind == "line":
        fig = px.line(y=args.y_column, **common)
    elif args.kind == "bar":
        fig = px.bar(y=args.y_column, **common)
    elif args.kind == "histogram":
        fig = px.histogram(**common)
    else:
        fig = px.box(y=args.y_column, **common)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(args.output), include_plotlyjs="cdn")

    summary = {
        "input_path": str(args.input),
        "kind": args.kind,
        "rows": int(len(df)),
        "x_column": args.x_column,
        "y_column": args.y_column,
        "color_column": args.color_column,
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
