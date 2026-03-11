#!/usr/bin/env python3
"""Fit a baseline statsmodels regression and export coefficient tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import statsmodels.api as sm


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
    parser.add_argument("--model", required=True, choices=["ols", "logit", "poisson"])
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--feature", action="append", default=[])
    parser.add_argument("--prediction-output", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.feature:
        raise SystemExit("at least one --feature is required")

    df = read_table(args.input)
    needed = [args.outcome, *args.feature]
    missing = [name for name in needed if name not in df.columns]
    if missing:
        raise SystemExit(f"missing columns: {', '.join(missing)}")

    work = df[needed].apply(pd.to_numeric, errors="coerce").dropna().copy()
    y = work[args.outcome]
    X = sm.add_constant(work[args.feature], has_constant="add")

    if args.model == "ols":
        results = sm.OLS(y, X).fit()
    elif args.model == "logit":
        results = sm.Logit(y, X).fit(disp=False)
    else:
        results = sm.GLM(y, X, family=sm.families.Poisson()).fit()

    conf = results.conf_int()
    conf.columns = ["ci_lower", "ci_upper"]
    coef_df = pd.DataFrame(
        {
            "term": results.params.index,
            "coefficient": results.params.values,
            "std_error": results.bse.values,
            "statistic": results.tvalues.values if hasattr(results, "tvalues") else results.params.values,
            "p_value": results.pvalues.values,
        }
    ).join(conf, how="left")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    coef_df.to_csv(args.output, index=False)

    prediction_path = None
    if args.prediction_output:
        pred_df = work.copy()
        pred_df["prediction"] = results.predict(X)
        args.prediction_output.parent.mkdir(parents=True, exist_ok=True)
        pred_df.to_csv(args.prediction_output, index=False)
        prediction_path = str(args.prediction_output)

    summary = {
        "input_path": str(args.input),
        "model": args.model,
        "outcome": args.outcome,
        "features": args.feature,
        "rows_used": int(len(work)),
        "output_path": str(args.output),
        "prediction_output": prediction_path,
        "aic": float(results.aic) if getattr(results, "aic", None) is not None else None,
        "bic": float(results.bic) if getattr(results, "bic", None) is not None else None,
        "pseudo_r2": float(results.prsquared) if hasattr(results, "prsquared") else None,
        "r_squared": float(results.rsquared) if hasattr(results, "rsquared") else None,
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
