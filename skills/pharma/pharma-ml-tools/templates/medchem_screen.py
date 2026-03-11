#!/usr/bin/env python3
"""Apply medicinal-chemistry rules and alert heuristics to a molecule table."""

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
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    import datamol as dm
    import medchem as mc

    df = read_table(args.input)
    if args.smiles_column not in df.columns:
        raise SystemExit(f"missing smiles column: {args.smiles_column}")

    ids = df[args.id_column].astype(str) if args.id_column and args.id_column in df.columns else df.index.astype(str)
    alert_filter = mc.structural.CommonAlertsFilters()

    rows: list[dict[str, Any]] = []
    invalid = 0
    for record_id, smiles in zip(ids, df[args.smiles_column].fillna("")):
        smiles = str(smiles).strip()
        row: dict[str, Any] = {"record_id": record_id, "input_smiles": smiles}
        try:
            mol = dm.to_mol(smiles)
            if mol is None:
                raise ValueError("invalid smiles")
            alert_raw = alert_filter.check_mol(mol)
            has_alerts = False
            alert_count = 0
            if isinstance(alert_raw, tuple) and alert_raw:
                has_alerts = bool(alert_raw[0])
                details = alert_raw[1] if len(alert_raw) > 1 else []
                alert_count = len(details) if hasattr(details, "__len__") else int(bool(has_alerts))
            else:
                has_alerts = bool(alert_raw)
                alert_count = int(has_alerts)
            row.update(
                {
                    "valid": True,
                    "rule_of_five": bool(mc.rules.basic_rules.rule_of_five(smiles)),
                    "rule_of_oprea": bool(mc.rules.basic_rules.rule_of_oprea(smiles)),
                    "rule_of_cns": bool(mc.rules.basic_rules.rule_of_cns(smiles)),
                    "rule_of_leadlike_soft": bool(mc.rules.basic_rules.rule_of_leadlike_soft(smiles)),
                    "common_alerts": has_alerts,
                    "common_alert_count": alert_count,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            invalid += 1
            row.update({"valid": False, "error": str(exc)})
        rows.append(row)

    out_df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    valid_df = out_df[out_df["valid"] == True] if "valid" in out_df.columns else out_df.iloc[0:0]  # noqa: E712
    summary = {
        "input_path": str(args.input),
        "rows": int(len(out_df)),
        "valid_rows": int(len(valid_df)),
        "invalid_rows": int(invalid),
        "rule_of_five_pass": int(valid_df["rule_of_five"].sum()) if not valid_df.empty else 0,
        "leadlike_pass": int(valid_df["rule_of_leadlike_soft"].sum()) if not valid_df.empty else 0,
        "common_alert_rows": int(valid_df["common_alerts"].sum()) if not valid_df.empty else 0,
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
