#!/usr/bin/env python3
"""Create a publication-style static figure with seaborn or matplotlib."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "drugclaw-mpl"))

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


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


def require_args(args: argparse.Namespace, names: list[str], kind: str) -> None:
    missing = [name for name in names if getattr(args, name) in {None, ""}]
    if missing:
        cli_names = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        raise SystemExit(f"{kind} requires {cli_names}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=["scatter", "line", "box", "violin", "bar", "heatmap"])
    parser.add_argument("--x-column")
    parser.add_argument("--y-column")
    parser.add_argument("--color-column")
    parser.add_argument("--value-column")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    df = read_table(args.input)

    sns.set_theme(style="whitegrid", context="paper")
    fig, ax = plt.subplots(figsize=(6, 4))

    if args.kind == "scatter":
        require_args(args, ["x_column", "y_column"], "scatter")
        sns.scatterplot(data=df, x=args.x_column, y=args.y_column, hue=args.color_column, ax=ax)
    elif args.kind == "line":
        require_args(args, ["x_column", "y_column"], "line")
        sns.lineplot(data=df, x=args.x_column, y=args.y_column, hue=args.color_column, ax=ax)
    elif args.kind == "box":
        require_args(args, ["x_column", "y_column"], "box")
        sns.boxplot(data=df, x=args.x_column, y=args.y_column, hue=args.color_column, ax=ax)
    elif args.kind == "violin":
        require_args(args, ["x_column", "y_column"], "violin")
        sns.violinplot(data=df, x=args.x_column, y=args.y_column, hue=args.color_column, ax=ax)
    elif args.kind == "bar":
        require_args(args, ["x_column", "y_column"], "bar")
        sns.barplot(data=df, x=args.x_column, y=args.y_column, hue=args.color_column, ax=ax)
    else:
        require_args(args, ["x_column", "y_column", "value_column"], "heatmap")
        pivot = df.pivot(index=args.y_column, columns=args.x_column, values=args.value_column)
        sns.heatmap(pivot, cmap="viridis", ax=ax)

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=300)
    plt.close(fig)

    summary = {
        "input_path": str(args.input),
        "kind": args.kind,
        "rows": int(len(df)),
        "output_path": str(args.output),
        "x_column": args.x_column,
        "y_column": args.y_column,
        "color_column": args.color_column,
        "value_column": args.value_column,
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
