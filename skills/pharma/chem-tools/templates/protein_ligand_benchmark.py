#!/usr/bin/env python3
"""Benchmark structure-aware protein-ligand affinity models."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from chem_ml_utils import estimator_for, predict_with_uncertainty, save_model_bundle
from protein_ligand_affinity import feature_matrix, read_rows, regression_metrics



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark structure-aware affinity models on PDBbind-style datasets")
    parser.add_argument("--input", required=True, help="Normalized CSV/TSV with complex/receptor/ligand paths and affinity")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--target-column", default="affinity")
    parser.add_argument("--complex-path-column", default="complex_path")
    parser.add_argument("--receptor-path-column", default="receptor_path")
    parser.add_argument("--ligand-path-column", default="ligand_path")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--group-column", default="target_group")
    parser.add_argument("--algorithm", default="rf", choices=["rf", "et", "gbr", "ridge"])
    parser.add_argument("--split", default="group", choices=["group", "random"])
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--contact-cutoff", type=float, default=6.0)
    parser.add_argument("--pocket-cutoff", type=float, default=8.0)
    parser.add_argument("--disable-ligand-descriptors", action="store_true", default=False)
    parser.add_argument("--features-output", default="protein_ligand_benchmark_features.csv")
    parser.add_argument("--metrics-output", default="protein_ligand_benchmark_metrics.json")
    parser.add_argument("--predictions-output", default="protein_ligand_benchmark_predictions.csv")
    parser.add_argument("--folds-output", default="protein_ligand_benchmark_folds.csv")
    parser.add_argument("--model-output", help="Optional final model bundle trained on all valid structures")
    return parser.parse_args()



def read_target_table(path: str, *, id_column: str, target_column: str) -> pd.DataFrame:
    table = pd.read_csv(path, sep="\t" if path.endswith(".tsv") else ",")
    if target_column not in table.columns:
        raise SystemExit(f"Missing target column: {target_column}")
    if id_column not in table.columns:
        table[id_column] = [f"row_{index + 1}" for index in range(len(table))]
    return table



def make_group_values(frame: pd.DataFrame, *, group_column: str) -> list[str]:
    if group_column in frame.columns:
        values = [str(value).strip() if str(value).strip() and str(value).strip().lower() != "nan" else "ungrouped" for value in frame[group_column].tolist()]
        if len(set(values)) > 1:
            return values
    for fallback in ["target_name", "protein_id", "best_receptor", "best_receptor_slug"]:
        if fallback in frame.columns:
            values = [str(value).strip() if str(value).strip() and str(value).strip().lower() != "nan" else "ungrouped" for value in frame[fallback].tolist()]
            if len(set(values)) > 1:
                return values
    raise SystemExit(f"Group split requested but no usable grouping column was found. Tried: {group_column}, target_name, protein_id")



def mean_std(metrics: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    keys = sorted({key for row in metrics for key in row.keys()} - {"fold", "train_size", "test_size"})
    summary: dict[str, dict[str, float]] = {}
    for key in keys:
        values = [float(row[key]) for row in metrics if key in row and math.isfinite(float(row[key]))]
        if not values:
            continue
        summary[key] = {"mean": float(np.mean(values)), "std": float(np.std(values))}
    return summary



def holdout_indices(*, split: str, groups: list[str], row_count: int, test_size: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    indices = np.arange(row_count)
    if split == "random":
        from sklearn.model_selection import train_test_split

        train_idx, test_idx = train_test_split(indices, test_size=test_size, random_state=seed)
        return np.asarray(train_idx), np.asarray(test_idx)
    from sklearn.model_selection import GroupShuffleSplit

    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(indices, groups=groups))
    return np.asarray(train_idx), np.asarray(test_idx)



def fold_rows(X: np.ndarray, y: np.ndarray, *, split: str, groups: list[str], algorithm: str, cv_folds: int, seed: int) -> list[dict[str, Any]]:
    if cv_folds < 2 or len(y) < cv_folds:
        return []
    if split == "group":
        from sklearn.model_selection import GroupKFold

        unique_groups = len(set(groups))
        if unique_groups < 2:
            return []
        splitter = GroupKFold(n_splits=min(cv_folds, unique_groups))
        iterator = splitter.split(X, y, groups=groups)
    else:
        from sklearn.model_selection import KFold

        splitter = KFold(n_splits=cv_folds, shuffle=True, random_state=seed)
        iterator = splitter.split(X, y)
    rows: list[dict[str, Any]] = []
    for fold_index, (train_idx, test_idx) in enumerate(iterator, 1):
        estimator = estimator_for("regression", algorithm)
        estimator.fit(X[train_idx], y[train_idx])
        predictions, uncertainty = predict_with_uncertainty(estimator, X[test_idx], task="regression")
        metrics = regression_metrics(y[test_idx].astype(np.float32), predictions.astype(np.float32))
        if uncertainty is not None:
            metrics["uncertainty_mean"] = float(np.mean(uncertainty))
        rows.append({"fold": fold_index, **metrics, "train_size": int(len(train_idx)), "test_size": int(len(test_idx))})
    return rows



def main() -> int:
    args = parse_args()
    table = read_target_table(args.input, id_column=args.id_column, target_column=args.target_column)
    rows = read_rows(
        input_path=args.input,
        sample_id="sample_1",
        complex_path=None,
        receptor_path=None,
        ligand_path=None,
        smiles=None,
        id_column=args.id_column,
        receptor_path_column=args.receptor_path_column,
        ligand_path_column=args.ligand_path_column,
        complex_path_column=args.complex_path_column,
        smiles_column=args.smiles_column,
    )
    X, valid_rows, invalid_rows, feature_names, feature_rows = feature_matrix(
        rows,
        contact_cutoff=args.contact_cutoff,
        pocket_cutoff=args.pocket_cutoff,
        include_ligand_descriptors=not args.disable_ligand_descriptors,
    )
    if len(valid_rows) < 6:
        raise SystemExit("Need at least 6 valid structure rows to run benchmark splits.")

    row_map = {str(row[args.id_column]): row.to_dict() for _, row in table.iterrows()}
    valid_meta = [row_map[row.sample_id] for row in valid_rows]
    y = np.asarray([float(meta[args.target_column]) for meta in valid_meta], dtype=np.float32)
    groups = make_group_values(pd.DataFrame(valid_meta), group_column=args.group_column)
    train_idx, test_idx = holdout_indices(split=args.split, groups=groups, row_count=len(valid_rows), test_size=args.test_size, seed=args.seed)

    estimator = estimator_for("regression", args.algorithm)
    estimator.fit(X[train_idx], y[train_idx])
    holdout_predictions, holdout_uncertainty = predict_with_uncertainty(estimator, X[test_idx], task="regression")
    holdout_metrics = regression_metrics(y[test_idx], holdout_predictions.astype(np.float32))
    if holdout_uncertainty is not None:
        holdout_metrics["uncertainty_mean"] = float(np.mean(holdout_uncertainty))
    fold_metric_rows = fold_rows(X, y, split=args.split, groups=groups, algorithm=args.algorithm, cv_folds=args.cv_folds, seed=args.seed)
    fold_summary = mean_std(fold_metric_rows)

    features_output = Path(args.features_output)
    features_output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(feature_rows).to_csv(features_output, index=False)

    prediction_rows: list[dict[str, Any]] = []
    test_lookup = {int(index): position for position, index in enumerate(test_idx.tolist())}
    test_set = set(int(index) for index in test_idx.tolist())
    for index, row in enumerate(valid_rows):
        meta = valid_meta[index]
        output = {
            "id": row.sample_id,
            "split": "test" if index in test_set else "train",
            "group": groups[index],
            "true_affinity": float(y[index]),
            "complex_path": str(row.complex_path) if row.complex_path else "",
            "receptor_path": str(row.receptor_path) if row.receptor_path else "",
            "ligand_path": str(row.ligand_path) if row.ligand_path else "",
            "smiles": row.smiles or "",
        }
        for key in ["target_name", "protein_id", "release_year", "resolution"]:
            if key in meta:
                output[key] = meta[key]
        if index in test_set:
            pred_index = test_lookup[index]
            output["predicted_affinity"] = float(holdout_predictions[pred_index])
            if holdout_uncertainty is not None:
                output["prediction_uncertainty"] = float(holdout_uncertainty[pred_index])
        prediction_rows.append(output)
    predictions_output = Path(args.predictions_output)
    predictions_output.parent.mkdir(parents=True, exist_ok=True)
    with predictions_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in prediction_rows for key in row.keys()}))
        writer.writeheader()
        writer.writerows(prediction_rows)

    folds_output = Path(args.folds_output)
    folds_output.parent.mkdir(parents=True, exist_ok=True)
    if fold_metric_rows:
        with folds_output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fold_metric_rows[0].keys()))
            writer.writeheader()
            writer.writerows(fold_metric_rows)
    else:
        pd.DataFrame([], columns=["fold", "train_size", "test_size"]).to_csv(folds_output, index=False)

    metrics_payload = {
        "task": "regression",
        "split": args.split,
        "algorithm": args.algorithm,
        "contact_cutoff": args.contact_cutoff,
        "pocket_cutoff": args.pocket_cutoff,
        "include_ligand_descriptors": bool(not args.disable_ligand_descriptors),
        "valid_rows": len(valid_rows),
        "invalid_rows": invalid_rows,
        "group_count": len(set(groups)),
        "feature_count": len(feature_names),
        "holdout": holdout_metrics,
        "cross_validation": fold_summary,
        "train_size": int(len(train_idx)),
        "test_size": int(len(test_idx)),
    }
    metrics_output = Path(args.metrics_output)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.model_output:
        final_model = estimator_for("regression", args.algorithm)
        final_model.fit(X, y)
        save_model_bundle(
            args.model_output,
            {
                "task": "regression",
                "model_kind": "protein_ligand_benchmark",
                "estimator": final_model,
                "feature_names": feature_names,
                "contact_cutoff": args.contact_cutoff,
                "pocket_cutoff": args.pocket_cutoff,
                "include_ligand_descriptors": not args.disable_ligand_descriptors,
                "benchmark_metrics": metrics_payload,
            },
        )
        print(f"saved model: {args.model_output}")

    print(f"saved features: {features_output}")
    print(f"saved metrics: {metrics_output}")
    print(f"saved predictions: {predictions_output}")
    print(f"saved folds: {folds_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
