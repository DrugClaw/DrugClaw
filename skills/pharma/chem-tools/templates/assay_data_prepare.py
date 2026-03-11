#!/usr/bin/env python3
"""Normalize medicinal chemistry assay tables into DrugClaw-friendly training data."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Optional

import pandas as pd

COMMON_BINDINGDB_COLUMNS = ["Ki (nM)", "Kd (nM)", "IC50 (nM)", "EC50 (nM)"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize ChEMBL/BindingDB/MoleculeNet/generic assay tables")
    parser.add_argument("--input", required=True, help="CSV/TSV input table")
    parser.add_argument("--source", default="auto", choices=["auto", "chembl", "bindingdb", "moleculenet", "generic"])
    parser.add_argument("--task", default="auto", choices=["auto", "classification", "regression"])
    parser.add_argument("--smiles-column")
    parser.add_argument("--id-column")
    parser.add_argument("--target-column")
    parser.add_argument("--target-name-column")
    parser.add_argument("--unit-column")
    parser.add_argument("--relation-column")
    parser.add_argument("--assay-column")
    parser.add_argument("--activity-threshold", type=float, help="Threshold for numeric classification tasks")
    parser.add_argument("--threshold-direction", default=">=", choices=[">=", "<="])
    parser.add_argument("--label-positive", default="active")
    parser.add_argument("--label-negative", default="inactive")
    parser.add_argument("--convert-nm-to-pactivity", action="store_true", help="Convert nM values to -log10(M) scale")
    parser.add_argument("--drop-duplicates", action="store_true")
    parser.add_argument("--output", default="normalized_assay.csv")
    parser.add_argument("--summary", default="normalized_assay.json")
    return parser.parse_args()


def read_table(path: str) -> pd.DataFrame:
    sep = "\t" if path.endswith(".tsv") else ","
    return pd.read_csv(path, sep=sep)


def detect_source(frame: pd.DataFrame, requested: str) -> str:
    if requested != "auto":
        return requested
    columns = set(frame.columns)
    if {"canonical_smiles", "standard_value"} <= columns or {"molecule_chembl_id", "canonical_smiles"} <= columns:
        return "chembl"
    if "Ligand SMILES" in columns and any(column in columns for column in COMMON_BINDINGDB_COLUMNS):
        return "bindingdb"
    if "smiles" in columns:
        return "moleculenet"
    return "generic"


def resolve_columns(frame: pd.DataFrame, args: argparse.Namespace, source: str) -> dict[str, Optional[str]]:
    columns = frame.columns
    if source == "chembl":
        target_column = args.target_column or ("pchembl_value" if "pchembl_value" in columns else "standard_value")
        measurement_column = "standard_type" if "standard_type" in columns else None
        return {
            "id": args.id_column or ("molecule_chembl_id" if "molecule_chembl_id" in columns else "id" if "id" in columns else None),
            "smiles": args.smiles_column or ("canonical_smiles" if "canonical_smiles" in columns else "smiles"),
            "target": target_column,
            "measurement": measurement_column,
            "target_name": args.target_name_column or ("target_pref_name" if "target_pref_name" in columns else None),
            "unit": args.unit_column or ("standard_units" if "standard_units" in columns else None),
            "relation": args.relation_column or ("standard_relation" if "standard_relation" in columns else None),
            "assay": args.assay_column or ("assay_chembl_id" if "assay_chembl_id" in columns else None),
        }
    if source == "bindingdb":
        target_column = args.target_column
        if not target_column:
            target_column = next((column for column in COMMON_BINDINGDB_COLUMNS if column in columns), None)
        measurement = target_column.split("(")[0].strip() if target_column else None
        return {
            "id": args.id_column or (
                "Ligand Name" if "Ligand Name" in columns else "BindingDB Ligand Name" if "BindingDB Ligand Name" in columns else None
            ),
            "smiles": args.smiles_column or "Ligand SMILES",
            "target": target_column,
            "measurement": measurement,
            "target_name": args.target_name_column or ("Target Name" if "Target Name" in columns else None),
            "unit": args.unit_column or None,
            "relation": args.relation_column or None,
            "assay": args.assay_column or ("BindingDB Reactant_set_id" if "BindingDB Reactant_set_id" in columns else None),
        }
    if source == "moleculenet":
        fallback_target = args.target_column
        if not fallback_target:
            candidate_columns = [
                column
                for column in columns
                if column not in {"smiles", "id", "mol_id", "molecule_id", "compound_id"}
            ]
            fallback_target = candidate_columns[0] if candidate_columns else None
        return {
            "id": args.id_column or ("id" if "id" in columns else "mol_id" if "mol_id" in columns else "molecule_id" if "molecule_id" in columns else None),
            "smiles": args.smiles_column or "smiles",
            "target": fallback_target,
            "measurement": fallback_target,
            "target_name": args.target_name_column or None,
            "unit": args.unit_column or None,
            "relation": args.relation_column or None,
            "assay": args.assay_column or None,
        }
    return {
        "id": args.id_column or ("id" if "id" in columns else None),
        "smiles": args.smiles_column or "smiles",
        "target": args.target_column or ("target" if "target" in columns else None),
        "measurement": args.target_column or ("target" if "target" in columns else None),
        "target_name": args.target_name_column or None,
        "unit": args.unit_column or None,
        "relation": args.relation_column or None,
        "assay": args.assay_column or None,
    }


def clean_string(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def maybe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed):
        return None
    return parsed


def choose_task(values: list[Any], requested: str) -> str:
    if requested != "auto":
        return requested
    numeric = [maybe_float(value) for value in values]
    if all(value is not None for value in numeric):
        unique = {round(value or 0.0, 8) for value in numeric}
        if unique <= {0.0, 1.0}:
            return "classification"
        return "regression" if len(unique) > 4 else "classification"
    return "classification"


def convert_numeric_target(
    value: float,
    *,
    unit: str,
    measurement: str,
    target_column: str,
    convert_nm_to_pactivity: bool,
) -> tuple[float, str]:
    normalized_unit = unit.lower()
    normalized_measurement = measurement.lower()
    normalized_target_column = target_column.lower()
    if normalized_target_column == "pchembl_value" or normalized_measurement == "pactivity":
        return value, measurement or "pactivity"
    if convert_nm_to_pactivity and value > 0 and (normalized_unit == "nm" or "(nm)" in normalized_measurement or normalized_measurement in {"ki", "kd", "ic50", "ec50"}):
        return 9.0 - math.log10(value), "pactivity"
    return value, measurement or "target"


def classify_numeric(value: float, threshold: float, direction: str, positive: str, negative: str) -> str:
    if direction == ">=":
        return positive if value >= threshold else negative
    return positive if value <= threshold else negative


def validate_smiles(smiles: str) -> bool:
    try:
        from rdkit import Chem
    except Exception:
        return bool(smiles)
    return Chem.MolFromSmiles(smiles) is not None


def main() -> int:
    args = parse_args()
    frame = read_table(args.input)
    source = detect_source(frame, args.source)
    columns = resolve_columns(frame, args, source)
    if not columns["smiles"] or columns["smiles"] not in frame.columns:
        raise SystemExit(f"Could not resolve smiles column for source={source}")
    if not columns["target"] or columns["target"] not in frame.columns:
        raise SystemExit(f"Could not resolve target column for source={source}")

    raw_targets = frame[columns["target"]].tolist()
    task = choose_task(raw_targets, args.task)
    threshold = args.activity_threshold
    if task == "classification" and threshold is None:
        numeric = [maybe_float(value) for value in raw_targets]
        if all(value is not None for value in numeric):
            unique = {round(value or 0.0, 8) for value in numeric}
            if unique <= {0.0, 1.0}:
                threshold = 0.5
            elif args.convert_nm_to_pactivity:
                threshold = 6.0

    normalized_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    dropped_duplicates = 0
    seen_keys: set[tuple[str, str]] = set()
    for index, row in frame.iterrows():
        smiles = clean_string(row[columns["smiles"]])
        raw_target = row[columns["target"]]
        if not smiles or clean_string(raw_target) == "":
            invalid_rows.append({"row": int(index) + 1, "reason": "missing_smiles_or_target"})
            continue
        if not validate_smiles(smiles):
            invalid_rows.append({"row": int(index) + 1, "reason": "invalid_smiles", "smiles": smiles})
            continue
        mol_id = clean_string(row[columns["id"]]) if columns["id"] and columns["id"] in frame.columns else f"row_{index + 1}"
        assay = clean_string(row[columns["assay"]]) if columns["assay"] and columns["assay"] in frame.columns else ""
        relation = clean_string(row[columns["relation"]]) if columns["relation"] and columns["relation"] in frame.columns else ""
        unit = clean_string(row[columns["unit"]]) if columns["unit"] and columns["unit"] in frame.columns else ""
        target_name = clean_string(row[columns["target_name"]]) if columns["target_name"] and columns["target_name"] in frame.columns else ""
        measurement = clean_string(row[columns["measurement"]]) if columns["measurement"] and columns["measurement"] in frame.columns else columns["target"]
        value_numeric = maybe_float(raw_target)
        target_value: Any = clean_string(raw_target)
        if value_numeric is not None:
            transformed_value, measurement = convert_numeric_target(
                value_numeric,
                unit=unit,
                measurement=measurement,
                target_column=columns["target"],
                convert_nm_to_pactivity=args.convert_nm_to_pactivity,
            )
            if task == "classification":
                if threshold is None:
                    raise SystemExit("Numeric classification tasks require --activity-threshold, binary labels, or --convert-nm-to-pactivity")
                target_value = classify_numeric(
                    transformed_value,
                    threshold,
                    args.threshold_direction,
                    args.label_positive,
                    args.label_negative,
                )
            else:
                target_value = round(float(transformed_value), 6)
        elif task == "regression":
            invalid_rows.append({"row": int(index) + 1, "reason": "non_numeric_regression_target", "value": clean_string(raw_target)})
            continue

        dedupe_key = (smiles, str(target_value))
        if args.drop_duplicates and dedupe_key in seen_keys:
            dropped_duplicates += 1
            continue
        seen_keys.add(dedupe_key)
        normalized_rows.append(
            {
                "id": mol_id,
                "smiles": smiles,
                "target": target_value,
                "task": task,
                "source": source,
                "assay": assay,
                "target_name": target_name,
                "measurement_type": measurement,
                "unit": unit,
                "relation": relation,
                "input_target_column": columns["target"],
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(normalized_rows).to_csv(output_path, index=False)

    summary = {
        "source": source,
        "task": task,
        "count": len(normalized_rows),
        "invalid_count": len(invalid_rows),
        "dropped_duplicates": dropped_duplicates,
        "smiles_column": columns["smiles"],
        "target_column": columns["target"],
        "activity_threshold": threshold,
        "threshold_direction": args.threshold_direction if threshold is not None else None,
        "convert_nm_to_pactivity": bool(args.convert_nm_to_pactivity),
        "invalid_rows": invalid_rows[:50],
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved normalized dataset: {output_path}")
    print(f"saved summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
