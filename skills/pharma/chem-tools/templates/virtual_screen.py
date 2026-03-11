#!/usr/bin/env python3
"""Rank a ligand library with ADMET, activity, affinity, and docking signals."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd
from chem_ml_utils import (
    build_feature_matrix,
    load_model_bundle,
    load_smiles_rows,
    normalize_series,
    resolve_class_label,
)


def merge_optional_table(path: str | None, id_column: str) -> dict[str, dict]:
    if not path:
        return {}
    table = pd.read_csv(path, sep="\t" if path.endswith(".tsv") else ",")
    candidate_columns = [id_column, "id", "ligand_id", "molecule_id"]
    resolved = next((column for column in candidate_columns if column in table.columns), None)
    if resolved is None:
        raise SystemExit(f"Missing id column {id_column} in {path}")
    return {str(row[resolved]): row.to_dict() for _, row in table.iterrows()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Virtual screening ranker for ligand libraries")
    parser.add_argument("--input", help="Library CSV/TSV/text input")
    parser.add_argument("--smiles", nargs="*", help="Inline SMILES library")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--admet-csv", help="Optional ADMET results from admet_screen.py")
    parser.add_argument("--affinity-csv", help="Optional affinity predictions CSV")
    parser.add_argument("--affinity-id-column", default="id")
    parser.add_argument("--affinity-score-column", default="predicted_affinity")
    parser.add_argument("--affinity-model", help="Model bundle from binding_affinity_predict.py")
    parser.add_argument("--bioactivity-model", help="Model bundle from bioactivity_predict.py")
    parser.add_argument("--docking-csv", help="Optional docking summary CSV")
    parser.add_argument("--docking-id-column", default="id")
    parser.add_argument("--docking-score-column", default="score_kcal_mol")
    parser.add_argument("--affinity-weight", type=float, default=0.35)
    parser.add_argument("--activity-weight", type=float, default=0.35)
    parser.add_argument("--admet-weight", type=float, default=0.20)
    parser.add_argument("--docking-weight", type=float, default=0.10)
    parser.add_argument("--affinity-direction", choices=["higher-better", "lower-better"], default="higher-better")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--output", default="virtual_screen_ranked.csv")
    parser.add_argument("--summary", default="virtual_screen_summary.json")
    args = parser.parse_args()

    rows = load_smiles_rows(
        input_path=args.input,
        smiles=args.smiles,
        smiles_column=args.smiles_column,
        id_column=args.id_column,
    )
    table_rows = [{"id": row.mol_id, "smiles": row.smiles} for row in rows]
    by_id = {row["id"]: row for row in table_rows}

    admet_table = merge_optional_table(args.admet_csv, args.id_column)
    for mol_id, row in by_id.items():
        if mol_id in admet_table:
            row.update(admet_table[mol_id])

    affinity_table = merge_optional_table(args.affinity_csv, args.affinity_id_column)
    for mol_id, row in by_id.items():
        if mol_id not in affinity_table:
            continue
        raw_value = affinity_table[mol_id].get(args.affinity_score_column)
        if raw_value in {None, ""}:
            continue
        try:
            row["predicted_affinity"] = float(raw_value)
            row["predicted_affinity_source"] = "affinity_csv"
        except Exception:
            continue

    if args.affinity_model:
        affinity_bundle = load_model_bundle(args.affinity_model)
        X, valid_rows, invalid_rows, _, _ = build_feature_matrix(
            rows,
            feature_backend=affinity_bundle["feature_backend"],
            fingerprint_size=affinity_bundle["fingerprint_size"],
            radius=affinity_bundle["radius"],
            include_descriptors=affinity_bundle["include_descriptors"],
        )
        preds = affinity_bundle["estimator"].predict(X)
        for row, pred in zip(valid_rows, preds):
            if by_id[row.mol_id].get("predicted_affinity") is None:
                by_id[row.mol_id]["predicted_affinity"] = float(pred)
                by_id[row.mol_id]["predicted_affinity_source"] = "affinity_model"
        for invalid in invalid_rows:
            if by_id[invalid["id"]].get("predicted_affinity") is None:
                by_id[invalid["id"]]["predicted_affinity"] = None

    if args.bioactivity_model:
        bio_bundle = load_model_bundle(args.bioactivity_model)
        X, valid_rows, invalid_rows, _, _ = build_feature_matrix(
            rows,
            feature_backend=bio_bundle["feature_backend"],
            fingerprint_size=bio_bundle["fingerprint_size"],
            radius=bio_bundle["radius"],
            include_descriptors=bio_bundle["include_descriptors"],
        )
        estimator = bio_bundle["estimator"]
        if bio_bundle["task"] == "classification":
            probs = estimator.predict_proba(X) if hasattr(estimator, "predict_proba") else None
            positive_label = resolve_class_label(estimator.classes_, bio_bundle.get("positive_label"))
            positive_index = list(estimator.classes_).index(positive_label) if probs is not None else None
            labels = estimator.predict(X)
            for index, row in enumerate(valid_rows):
                by_id[row.mol_id]["predicted_bioactivity_label"] = labels[index]
                if probs is not None and positive_index is not None:
                    by_id[row.mol_id]["predicted_bioactivity_probability"] = float(probs[index][positive_index])
                else:
                    by_id[row.mol_id]["predicted_bioactivity_probability"] = 1.0 if labels[index] == positive_label else 0.0
        else:
            preds = estimator.predict(X)
            for row, pred in zip(valid_rows, preds):
                by_id[row.mol_id]["predicted_bioactivity"] = float(pred)
        for invalid in invalid_rows:
            by_id[invalid["id"]]["predicted_bioactivity_probability"] = None

    docking_table = merge_optional_table(args.docking_csv, args.docking_id_column)
    for mol_id, row in by_id.items():
        if mol_id in docking_table and args.docking_score_column in docking_table[mol_id]:
            row["docking_score"] = docking_table[mol_id][args.docking_score_column]

    affinity_values = [float(row["predicted_affinity"]) for row in table_rows if row.get("predicted_affinity") is not None]
    activity_values = [float(row.get("predicted_bioactivity_probability", row.get("predicted_bioactivity", 0.0))) for row in table_rows if row.get("predicted_bioactivity_probability") is not None or row.get("predicted_bioactivity") is not None]
    admet_values = [float(row["admet_score"]) for row in table_rows if row.get("admet_score") is not None]
    docking_values = [float(row["docking_score"]) for row in table_rows if row.get("docking_score") is not None]

    affinity_scaled = normalize_series(affinity_values, higher_is_better=args.affinity_direction == "higher-better") if affinity_values else []
    activity_scaled = normalize_series(activity_values, higher_is_better=True) if activity_values else []
    admet_scaled = normalize_series(admet_values, higher_is_better=True) if admet_values else []
    docking_scaled = normalize_series(docking_values, higher_is_better=False) if docking_values else []

    affinity_iter = iter(affinity_scaled)
    activity_iter = iter(activity_scaled)
    admet_iter = iter(admet_scaled)
    docking_iter = iter(docking_scaled)
    for row in table_rows:
        components = []
        if row.get("predicted_affinity") is not None:
            value = next(affinity_iter)
            row["affinity_component"] = value
            components.append((value, args.affinity_weight))
        if row.get("predicted_bioactivity_probability") is not None or row.get("predicted_bioactivity") is not None:
            value = next(activity_iter)
            row["bioactivity_component"] = value
            components.append((value, args.activity_weight))
        if row.get("admet_score") is not None:
            value = next(admet_iter)
            row["admet_component"] = value
            components.append((value, args.admet_weight))
        if row.get("docking_score") is not None:
            value = next(docking_iter)
            row["docking_component"] = value
            components.append((value, args.docking_weight))
        total_weight = sum(weight for _, weight in components)
        row["screen_score"] = sum(value * weight for value, weight in components) / total_weight if total_weight else 0.0

    ranked = sorted(table_rows, key=lambda row: row["screen_score"], reverse=True)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = sorted({key for row in ranked for key in row.keys()})
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ranked)

    summary = {
        "total": len(ranked),
        "top_n": args.top_n,
        "top_ids": [row["id"] for row in ranked[: args.top_n]],
        "used_affinity_csv": bool(args.affinity_csv),
        "used_affinity_model": bool(args.affinity_model),
        "used_bioactivity_model": bool(args.bioactivity_model),
        "used_admet_table": bool(args.admet_csv),
        "used_docking_csv": bool(args.docking_csv),
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved ranked screen: {output_path}")
    print(f"saved summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
