#!/usr/bin/env python3
"""Featurize molecules with molfeat and export a flat feature table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported input format: {path}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--smiles-column", required=True)
    parser.add_argument("--id-column")
    parser.add_argument("--featurizer", choices=["ecfp", "maccs", "rdkit2d"], default="ecfp")
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--bits", type=int, default=2048)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    from molfeat.calc import FPCalculator, RDKitDescriptors2D
    from molfeat.trans import MoleculeTransformer

    df = read_table(args.input)
    if args.smiles_column not in df.columns:
        raise SystemExit(f"missing smiles column: {args.smiles_column}")

    smiles = df[args.smiles_column].fillna("").astype(str)
    ids = df[args.id_column].astype(str) if args.id_column and args.id_column in df.columns else df.index.astype(str)

    if args.featurizer == "ecfp":
        calc = FPCalculator("ecfp", radius=args.radius, fpSize=args.bits)
    elif args.featurizer == "maccs":
        calc = FPCalculator("maccs")
    else:
        calc = RDKitDescriptors2D()

    transformer = MoleculeTransformer(calc, n_jobs=-1, ignore_errors=True)
    features = transformer(smiles.tolist())

    valid_rows: list[dict[str, Any]] = []
    invalid = 0
    for record_id, original_smiles, feat in zip(ids, smiles, features):
        if feat is None:
            invalid += 1
            continue
        arr = np.asarray(feat).reshape(-1)
        row = {
            "record_id": record_id,
            "input_smiles": original_smiles,
        }
        for i, value in enumerate(arr):
            row[f"feat_{i}"] = float(value)
        valid_rows.append(row)

    out_df = pd.DataFrame(valid_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    summary = {
        "input_path": str(args.input),
        "rows": int(len(df)),
        "valid_rows": int(len(out_df)),
        "invalid_rows": int(invalid),
        "featurizer": args.featurizer,
        "feature_count": int(max(out_df.shape[1] - 2, 0)) if not out_df.empty else 0,
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
