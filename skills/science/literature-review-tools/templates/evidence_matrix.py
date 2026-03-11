#!/usr/bin/env python3
"""Convert a paper table into an evidence matrix for review synthesis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


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
    parser.add_argument("--title-column", required=True)
    parser.add_argument("--question-column")
    parser.add_argument("--model-column")
    parser.add_argument("--intervention-column")
    parser.add_argument("--outcome-column")
    parser.add_argument("--finding-column")
    parser.add_argument("--evidence-type-column")
    parser.add_argument("--year-column")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    df = read_table(args.input)
    if args.title_column not in df.columns:
        raise SystemExit(f"missing title column: {args.title_column}")

    def column_or_blank(name: str | None) -> pd.Series:
        if name and name in df.columns:
            return df[name].fillna("").astype(str)
        return pd.Series([""] * len(df))

    matrix = pd.DataFrame(
        {
            "title": column_or_blank(args.title_column),
            "question": column_or_blank(args.question_column),
            "model_system": column_or_blank(args.model_column),
            "intervention": column_or_blank(args.intervention_column),
            "outcome": column_or_blank(args.outcome_column),
            "key_finding": column_or_blank(args.finding_column),
            "evidence_type": column_or_blank(args.evidence_type_column),
            "year": column_or_blank(args.year_column),
        }
    )
    matrix["title"] = matrix["title"].str.strip()
    matrix = matrix[matrix["title"] != ""].copy()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(args.output, index=False)

    summary = {
        "input_path": str(args.input),
        "rows": int(len(matrix)),
        "unique_questions": int(matrix["question"].replace("", pd.NA).dropna().nunique()),
        "unique_model_systems": int(matrix["model_system"].replace("", pd.NA).dropna().nunique()),
        "unique_interventions": int(matrix["intervention"].replace("", pd.NA).dropna().nunique()),
        "evidence_type_counts": matrix["evidence_type"].replace("", "unspecified").value_counts().to_dict(),
        "year_counts": matrix["year"].replace("", "unspecified").value_counts().sort_index().to_dict(),
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
