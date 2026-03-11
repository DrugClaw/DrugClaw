#!/usr/bin/env python3
"""Run Kaplan-Meier summaries and a Cox PH baseline with statsmodels."""

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
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import SurvfuncRight


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
    parser.add_argument("--time-column", required=True)
    parser.add_argument("--event-column", required=True)
    parser.add_argument("--group-column")
    parser.add_argument("--covariate", action="append", default=[])
    parser.add_argument("--plot-output", required=True, type=Path)
    parser.add_argument("--km-output", required=True, type=Path)
    parser.add_argument("--cox-output", type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def km_records(time: pd.Series, event: pd.Series, label: str) -> tuple[list[dict[str, Any]], float | None, SurvfuncRight]:
    sf = SurvfuncRight(time.to_numpy(), event.to_numpy())
    records = [
        {
            "group": label,
            "time": float(t),
            "survival_probability": float(s),
        }
        for t, s in zip(sf.surv_times, sf.surv_prob)
    ]
    median = None
    for t, s in zip(sf.surv_times, sf.surv_prob):
        if s <= 0.5:
            median = float(t)
            break
    return records, median, sf


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    df = read_table(args.input)
    needed = [args.time_column, args.event_column]
    if args.group_column:
        needed.append(args.group_column)
    needed.extend(args.covariate)
    missing = [name for name in needed if name not in df.columns]
    if missing:
        raise SystemExit(f"missing columns: {', '.join(missing)}")

    work = df[needed].copy()
    work[args.time_column] = pd.to_numeric(work[args.time_column], errors="coerce")
    work[args.event_column] = pd.to_numeric(work[args.event_column], errors="coerce")
    for covariate in args.covariate:
        work[covariate] = pd.to_numeric(work[covariate], errors="coerce")
    work = work.dropna()
    work = work[work[args.time_column] >= 0].copy()
    if work.empty:
        raise SystemExit("no valid rows remain after filtering missing values and negative times")

    invalid_event_codes = sorted(set(work[args.event_column].unique()) - {0, 1})
    if invalid_event_codes:
        raise SystemExit(
            f"event column must be coded as 0/1 after numeric conversion; found invalid values: {invalid_event_codes}"
        )
    work[args.event_column] = work[args.event_column].astype(int)

    km_rows: list[dict[str, Any]] = []
    median_summary: list[dict[str, Any]] = []
    fig, ax = plt.subplots(figsize=(6, 4))

    if args.group_column:
        for label, group_df in work.groupby(args.group_column):
            records, median, sf = km_records(group_df[args.time_column], group_df[args.event_column], str(label))
            km_rows.extend(records)
            median_summary.append({"group": str(label), "n": int(len(group_df)), "median_survival": median})
            ax.step(sf.surv_times, sf.surv_prob, where="post", label=str(label))
    else:
        records, median, sf = km_records(work[args.time_column], work[args.event_column], "all")
        km_rows.extend(records)
        median_summary.append({"group": "all", "n": int(len(work)), "median_survival": median})
        ax.step(sf.surv_times, sf.surv_prob, where="post", label="all")

    ax.set_xlabel(args.time_column)
    ax.set_ylabel("Survival probability")
    ax.set_ylim(0, 1.02)
    ax.legend()
    args.plot_output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.plot_output, dpi=200)
    plt.close(fig)

    km_df = pd.DataFrame(km_rows)
    args.km_output.parent.mkdir(parents=True, exist_ok=True)
    km_df.to_csv(args.km_output, index=False)

    summary: dict[str, Any] = {
        "input_path": str(args.input),
        "rows_used": int(len(work)),
        "median_survival": median_summary,
        "plot_output": str(args.plot_output),
        "km_output": str(args.km_output),
    }

    if args.group_column:
        labels = list(map(str, work[args.group_column].astype(str).unique().tolist()))
        if len(labels) >= 2:
            stat, pvalue = sm.duration.survdiff(
                work[args.time_column].to_numpy(),
                work[args.event_column].to_numpy(),
                work[args.group_column].astype(str).to_numpy(),
            )
            summary["logrank"] = {"statistic": float(stat), "p_value": float(pvalue), "groups": labels}

    if args.covariate and args.cox_output:
        endog = work[args.time_column].to_numpy()
        exog = work[args.covariate].to_numpy()
        status = work[args.event_column].to_numpy()
        model = PHReg(endog, exog, status=status, ties="breslow")
        results = model.fit(disp=False)
        params = np.asarray(results.params)
        conf = results.conf_int()
        coef_df = pd.DataFrame(
            {
                "term": args.covariate,
                "coefficient": params,
                "hazard_ratio": np.exp(params),
                "ci_lower": np.exp(conf[:, 0]),
                "ci_upper": np.exp(conf[:, 1]),
                "p_value": np.asarray(results.pvalues),
            }
        )
        args.cox_output.parent.mkdir(parents=True, exist_ok=True)
        coef_df.to_csv(args.cox_output, index=False)
        summary["cox_output"] = str(args.cox_output)
    elif args.covariate:
        raise SystemExit("--cox-output is required when covariates are provided")

    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
