#!/usr/bin/env python3
"""Run a basic statistical test and export machine-readable results."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


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
    path.write_text(json.dumps(sanitize_json(payload), indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return [sanitize_json(item) for item in value.tolist()]
    if isinstance(value, np.floating | float):
        return None if math.isnan(float(value)) or math.isinf(float(value)) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    pooled = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--test",
        required=True,
        choices=["independent_ttest", "paired_ttest", "mannwhitney", "chi_square", "pearson", "spearman"],
    )
    parser.add_argument("--value-column")
    parser.add_argument("--value-column-b")
    parser.add_argument("--group-column")
    parser.add_argument("--group-a")
    parser.add_argument("--group-b")
    parser.add_argument("--x-column")
    parser.add_argument("--y-column")
    parser.add_argument("--category-column")
    parser.add_argument("--outcome-column")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    df = read_table(args.input)

    result: dict[str, Any] = {"test": args.test, "input_path": str(args.input)}
    row_outputs: list[dict[str, Any]] = []

    if args.test in {"independent_ttest", "mannwhitney"}:
        if not all([args.value_column, args.group_column, args.group_a, args.group_b]):
            raise SystemExit("group comparison needs --value-column, --group-column, --group-a, and --group-b")
        group_a = pd.to_numeric(df.loc[df[args.group_column] == args.group_a, args.value_column], errors="coerce").dropna().to_numpy()
        group_b = pd.to_numeric(df.loc[df[args.group_column] == args.group_b, args.value_column], errors="coerce").dropna().to_numpy()
        if len(group_a) == 0 or len(group_b) == 0:
            raise SystemExit("one or both groups are empty")
        if args.test == "independent_ttest":
            stat, pvalue = stats.ttest_ind(group_a, group_b, equal_var=False)
            effect = cohens_d(group_a, group_b)
            result.update({"statistic": float(stat), "p_value": float(pvalue), "effect_size": effect, "effect_size_name": "cohens_d"})
        else:
            stat, pvalue = stats.mannwhitneyu(group_a, group_b, alternative="two-sided")
            result.update({"statistic": float(stat), "p_value": float(pvalue)})
        row_outputs = [
            {"group": args.group_a, "n": int(len(group_a)), "mean": float(group_a.mean()), "median": float(np.median(group_a)), "std": float(group_a.std(ddof=1)) if len(group_a) > 1 else 0.0},
            {"group": args.group_b, "n": int(len(group_b)), "mean": float(group_b.mean()), "median": float(np.median(group_b)), "std": float(group_b.std(ddof=1)) if len(group_b) > 1 else 0.0},
        ]
    elif args.test == "paired_ttest":
        if not args.value_column or not args.value_column_b:
            raise SystemExit("paired_ttest needs --value-column and --value-column-b")
        a = pd.to_numeric(df[args.value_column], errors="coerce")
        b = pd.to_numeric(df[args.value_column_b], errors="coerce")
        pair_df = pd.DataFrame({"a": a, "b": b}).dropna()
        if len(pair_df) < 2:
            raise SystemExit("paired_ttest needs at least 2 complete pairs")
        stat, pvalue = stats.ttest_rel(pair_df["a"], pair_df["b"])
        diffs = pair_df["a"] - pair_df["b"]
        result.update({"statistic": float(stat), "p_value": float(pvalue), "mean_difference": float(diffs.mean())})
        row_outputs = [{"n_pairs": int(len(pair_df)), "mean_a": float(pair_df['a'].mean()), "mean_b": float(pair_df['b'].mean())}]
    elif args.test == "chi_square":
        if not args.category_column or not args.outcome_column:
            raise SystemExit("chi_square needs --category-column and --outcome-column")
        table = pd.crosstab(df[args.category_column], df[args.outcome_column])
        stat, pvalue, dof, _ = stats.chi2_contingency(table)
        result.update({"statistic": float(stat), "p_value": float(pvalue), "degrees_of_freedom": int(dof)})
        row_outputs = table.reset_index().to_dict(orient="records")
    else:
        if not args.x_column or not args.y_column:
            raise SystemExit("correlation tests need --x-column and --y-column")
        pair_df = df[[args.x_column, args.y_column]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair_df) < 2:
            raise SystemExit("correlation tests need at least 2 complete observations")
        if args.test == "pearson":
            stat, pvalue = stats.pearsonr(pair_df[args.x_column], pair_df[args.y_column])
        else:
            stat, pvalue = stats.spearmanr(pair_df[args.x_column], pair_df[args.y_column])
        result.update({"statistic": float(stat), "p_value": float(pvalue), "n": int(len(pair_df))})
        row_outputs = [{"x_column": args.x_column, "y_column": args.y_column, "n": int(len(pair_df))}]

    out_df = pd.DataFrame(row_outputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)
    result["output_path"] = str(args.output)
    write_json(args.summary, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
