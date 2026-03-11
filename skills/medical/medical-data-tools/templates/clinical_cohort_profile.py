#!/usr/bin/env python3
"""Profile clinical cohort tables from CSV/TSV/Parquet exports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional at runtime
    pd = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize clinical cohort tables for research use")
    parser.add_argument("--input", required=True, help="Input CSV, TSV, JSON, or Parquet file")
    parser.add_argument("--patient-id-column", required=True, help="Patient identifier column")
    parser.add_argument("--visit-id-column", help="Visit or encounter identifier column")
    parser.add_argument("--time-column", help="Timestamp column")
    parser.add_argument("--label-column", help="Target or outcome label column")
    parser.add_argument("--code-column", help="Diagnosis, procedure, or medication code column")
    parser.add_argument("--group-column", action="append", default=[], help="Optional stratification column, repeatable")
    parser.add_argument("--top-n", type=int, default=20, help="Top-N entries for label/code/group summaries")
    parser.add_argument("--sep", choices=[",", "tab", "auto"], default="auto")
    parser.add_argument("--output", default="medical/cohort_profile.csv")
    parser.add_argument("--summary", default="medical/cohort_profile.json")
    return parser.parse_args()


def require_pandas() -> None:
    if pd is None:
        raise SystemExit("pandas is required for clinical_cohort_profile.py")


def load_table(path: Path, sep: str):
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".json":
        return pd.read_json(path)
    if sep == "tab" or suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if sep == "," or suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_csv(path, sep=None, engine="python")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(pd, "isna") and pd.isna(value):
        return ""
    return str(value).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_metric(rows: list[dict[str, Any]], section: str, field: str, key: str, value: Any) -> None:
    rows.append({"section": section, "field": field, "key": clean_text(key), "value": value})


def add_value_counts(rows: list[dict[str, Any]], section: str, field: str, series, top_n: int, patient_series=None) -> list[dict[str, Any]]:
    counts = []
    value_counts = series.astype(str).fillna("").value_counts(dropna=False).head(top_n)
    for key, count in value_counts.items():
        patient_count = ""
        if patient_series is not None:
            mask = series.astype(str).fillna("") == key
            patient_count = int(patient_series[mask].nunique())
        append_metric(rows, section, field, key, int(count))
        counts.append({"key": clean_text(key), "count": int(count), "patient_count": patient_count})
    return counts


def main() -> None:
    args = parse_args()
    require_pandas()
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    frame = load_table(input_path, args.sep)

    required = [args.patient_id_column]
    optional = [args.visit_id_column, args.time_column, args.label_column, args.code_column, *args.group_column]
    missing = [name for name in [*required, *optional] if name and name not in frame.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {', '.join(missing)}")

    patient_series = frame[args.patient_id_column]
    rows: list[dict[str, Any]] = []
    append_metric(rows, "overall", "row_count", "", int(len(frame)))
    append_metric(rows, "overall", "column_count", "", int(len(frame.columns)))
    append_metric(rows, "overall", "patient_count", "", int(patient_series.nunique()))

    visit_count = None
    if args.visit_id_column:
        visit_count = int(frame[args.visit_id_column].nunique())
        append_metric(rows, "overall", "visit_count", "", visit_count)

    time_summary = {}
    if args.time_column:
        parsed = pd.to_datetime(frame[args.time_column], errors="coerce")
        valid = parsed.dropna()
        if not valid.empty:
            time_summary = {
                "min": valid.min().isoformat(),
                "max": valid.max().isoformat(),
            }
            append_metric(rows, "overall", "time_min", "", time_summary["min"])
            append_metric(rows, "overall", "time_max", "", time_summary["max"])

    label_summary = []
    if args.label_column:
        label_summary = add_value_counts(rows, "label_distribution", args.label_column, frame[args.label_column], args.top_n, patient_series)

    code_summary = []
    if args.code_column:
        code_summary = add_value_counts(rows, "code_distribution", args.code_column, frame[args.code_column], args.top_n, patient_series)

    group_summaries = {}
    for group_col in args.group_column:
        group_summaries[group_col] = add_value_counts(rows, "group_distribution", group_col, frame[group_col], args.top_n, patient_series)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)

    summary = {
        "tool": "clinical_cohort_profile",
        "input": str(input_path),
        "patient_id_column": args.patient_id_column,
        "visit_id_column": args.visit_id_column or "",
        "time_column": args.time_column or "",
        "label_column": args.label_column or "",
        "code_column": args.code_column or "",
        "group_columns": args.group_column,
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "patient_count": int(patient_series.nunique()),
        "visit_count": visit_count if visit_count is not None else "",
        "time_range": time_summary,
        "label_distribution": label_summary,
        "code_distribution": code_summary,
        "group_distributions": group_summaries,
        "output": str(output_path),
        "warning": "This is a cohort-level research summary. It does not produce patient-level recommendations or validated clinical predictions.",
    }
    write_json(summary_path, summary)
    print(json.dumps({"output": str(output_path), "summary": str(summary_path), "result_count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
