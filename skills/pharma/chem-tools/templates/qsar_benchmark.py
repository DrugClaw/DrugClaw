#!/usr/bin/env python3
"""Benchmark ligand-only QSAR baselines with random or scaffold splits."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from chem_ml_utils import (
    align_targets_to_valid_rows,
    build_feature_matrix,
    estimator_for,
    infer_task_from_targets,
    load_smiles_rows,
    predict_with_uncertainty,
    resolve_class_label,
    save_model_bundle,
    scaffold_for_smiles,
    scaffold_split_indices,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark QSAR models on normalized SMILES datasets")
    parser.add_argument("--input", required=True, help="CSV/TSV dataset containing SMILES and target")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--target-column", default="target")
    parser.add_argument("--task", default="auto", choices=["auto", "classification", "regression"])
    parser.add_argument("--positive-label")
    parser.add_argument("--feature-backend", default="rdkit-morgan", choices=["rdkit-morgan", "rdkit-maccs", "deepchem-circular"])
    parser.add_argument("--fingerprint-size", type=int, default=2048)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--algorithm", default="rf")
    parser.add_argument("--include-descriptors", action="store_true", default=False)
    parser.add_argument("--split", default="scaffold", choices=["scaffold", "random"])
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--metrics-output", default="qsar_benchmark_metrics.json")
    parser.add_argument("--predictions-output", default="qsar_benchmark_predictions.csv")
    parser.add_argument("--folds-output", default="qsar_benchmark_folds.csv")
    parser.add_argument("--model-output", help="Optional model bundle trained on all valid data")
    return parser.parse_args()


def read_targets(path: str, smiles_column: str, id_column: str, target_column: str) -> tuple[list, np.ndarray]:
    table = pd.read_csv(path, sep="\t" if path.endswith(".tsv") else ",")
    if target_column not in table.columns:
        raise SystemExit(f"Missing target column: {target_column}")
    rows = load_smiles_rows(input_path=path, smiles=None, smiles_column=smiles_column, id_column=id_column)
    target_map = {
        (str(table.iloc[index][id_column]) if id_column in table.columns else f"row_{index + 1}"): table.iloc[index][target_column]
        for index in range(len(table))
    }
    values = [target_map[row.mol_id] for row in rows]
    return rows, np.asarray(values, dtype=object)


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    metrics = {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
    }
    try:
        from scipy.stats import spearmanr

        metrics["spearman"] = float(spearmanr(y_true, y_pred).statistic)
    except Exception:
        pass
    return metrics


def classification_metrics(y_true, y_pred, y_score=None) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
    }
    if y_score is not None and len(set(y_true)) == 2:
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_score))
        except Exception:
            pass
    return metrics


def make_holdout_indices(rows, task: str, targets: np.ndarray, split: str, test_size: float, seed: int) -> tuple[list[int], list[int], list[str]]:
    if split == "scaffold":
        train_idx, test_idx, scaffolds = scaffold_split_indices(rows, test_size=test_size)
        return train_idx, test_idx, scaffolds
    from sklearn.model_selection import train_test_split

    indices = np.arange(len(rows))
    stratify = None
    if task == "classification":
        counts = Counter(targets.tolist())
        if len(counts) > 1 and min(counts.values()) >= 2:
            stratify = targets
    train_idx, test_idx = train_test_split(indices, test_size=test_size, random_state=seed, stratify=stratify)
    scaffolds = [scaffold_for_smiles(row.smiles) for row in rows]
    return list(train_idx), list(test_idx), scaffolds


def fold_summaries(X, y, rows, task: str, algorithm: str, split: str, cv_folds: int, seed: int, positive_label: Any | None) -> list[dict[str, Any]]:
    if cv_folds < 2 or len(rows) < cv_folds:
        return []
    if split == "scaffold":
        from sklearn.model_selection import GroupKFold

        groups = [scaffold_for_smiles(row.smiles) for row in rows]
        unique_groups = len(set(groups))
        if unique_groups < 2:
            return []
        splitter = GroupKFold(n_splits=min(cv_folds, unique_groups))
        iterator = splitter.split(X, y, groups=groups)
    else:
        if task == "classification":
            from sklearn.model_selection import StratifiedKFold

            counts = Counter(y.tolist())
            if len(counts) < 2 or min(counts.values()) < cv_folds:
                return []
            splitter = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
            iterator = splitter.split(X, y)
        else:
            from sklearn.model_selection import KFold

            splitter = KFold(n_splits=cv_folds, shuffle=True, random_state=seed)
            iterator = splitter.split(X, y)

    folds: list[dict[str, Any]] = []
    for fold_index, (train_idx, test_idx) in enumerate(iterator, 1):
        estimator = estimator_for(task, algorithm)
        estimator.fit(X[train_idx], y[train_idx])
        predictions, _ = predict_with_uncertainty(estimator, X[test_idx], task=task, positive_label=positive_label)
        if task == "classification":
            y_score = None
            if hasattr(estimator, "predict_proba") and len(getattr(estimator, "classes_", [])) == 2:
                label = resolve_class_label(estimator.classes_, positive_label)
                label_index = list(estimator.classes_).index(label)
                y_score = estimator.predict_proba(X[test_idx])[:, label_index]
            metrics = classification_metrics(y[test_idx], predictions, y_score)
        else:
            metrics = regression_metrics(y[test_idx].astype(np.float32), predictions.astype(np.float32))
        folds.append({"fold": fold_index, **metrics, "train_size": int(len(train_idx)), "test_size": int(len(test_idx))})
    return folds


def mean_std(metrics: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    keys = sorted({key for row in metrics for key in row.keys()} - {"fold", "train_size", "test_size"})
    summary: dict[str, dict[str, float]] = {}
    for key in keys:
        values = [float(row[key]) for row in metrics if key in row]
        if not values:
            continue
        summary[key] = {"mean": float(np.mean(values)), "std": float(np.std(values))}
    return summary


def main() -> int:
    args = parse_args()
    rows, raw_targets = read_targets(args.input, args.smiles_column, args.id_column, args.target_column)
    task = infer_task_from_targets(raw_targets.tolist()) if args.task == "auto" else args.task
    X, valid_rows, invalid_rows, feature_names, descriptor_rows = build_feature_matrix(
        rows,
        feature_backend=args.feature_backend,
        fingerprint_size=args.fingerprint_size,
        radius=args.radius,
        include_descriptors=args.include_descriptors,
    )
    valid_targets = np.asarray(align_targets_to_valid_rows(rows, raw_targets, valid_rows), dtype=object)
    if len(valid_rows) < 6:
        raise SystemExit("Need at least 6 valid molecules to run benchmark splits.")

    if task == "regression":
        y = valid_targets.astype(np.float32)
        positive_label = None
    else:
        y = valid_targets
        positive_label = args.positive_label
        if len(set(y.tolist())) < 2:
            raise SystemExit("Classification benchmark requires at least two label classes.")

    train_idx, test_idx, scaffolds = make_holdout_indices(valid_rows, task, y, args.split, args.test_size, args.seed)
    estimator = estimator_for(task, args.algorithm)
    estimator.fit(X[train_idx], y[train_idx])
    holdout_predictions, uncertainty = predict_with_uncertainty(estimator, X[test_idx], task=task, positive_label=positive_label)
    holdout_metrics: dict[str, float]
    positive_label_value = None
    y_score = None
    if task == "classification":
        if hasattr(estimator, "predict_proba") and len(getattr(estimator, "classes_", [])) == 2:
            positive_label_value = resolve_class_label(estimator.classes_, positive_label)
            label_index = list(estimator.classes_).index(positive_label_value)
            y_score = estimator.predict_proba(X[test_idx])[:, label_index]
        holdout_metrics = classification_metrics(y[test_idx], holdout_predictions, y_score)
    else:
        holdout_metrics = regression_metrics(y[test_idx], holdout_predictions.astype(np.float32))

    fold_rows = fold_summaries(X, y, valid_rows, task, args.algorithm, args.split, args.cv_folds, args.seed, positive_label_value or positive_label)
    fold_summary = mean_std(fold_rows)

    prediction_rows: list[dict[str, Any]] = []
    test_set = set(test_idx)
    test_prediction_map = {index: pos for pos, index in enumerate(test_idx)}
    for index, row in enumerate(valid_rows):
        base = {
            "id": row.mol_id,
            "smiles": row.smiles,
            "scaffold": scaffolds[index],
            "split": "test" if index in test_set else "train",
            "true_target": y[index].item() if hasattr(y[index], "item") else y[index],
        }
        descriptor_row = descriptor_rows[index] if index < len(descriptor_rows) else {}
        base.update({key: value for key, value in descriptor_row.items() if key not in {"id", "smiles"}})
        if index in test_set:
            pred_index = test_prediction_map[index]
            if task == "classification":
                base["predicted_label"] = holdout_predictions[pred_index].item() if hasattr(holdout_predictions[pred_index], "item") else holdout_predictions[pred_index]
                if y_score is not None:
                    base["predicted_active_probability"] = float(y_score[pred_index])
            else:
                base["predicted_target"] = float(holdout_predictions[pred_index])
            if uncertainty is not None:
                base["prediction_uncertainty"] = float(uncertainty[pred_index])
        prediction_rows.append(base)

    predictions_output = Path(args.predictions_output)
    predictions_output.parent.mkdir(parents=True, exist_ok=True)
    with predictions_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in prediction_rows for key in row.keys()}))
        writer.writeheader()
        writer.writerows(prediction_rows)

    folds_output = Path(args.folds_output)
    folds_output.parent.mkdir(parents=True, exist_ok=True)
    if fold_rows:
        with folds_output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fold_rows[0].keys()))
            writer.writeheader()
            writer.writerows(fold_rows)
    else:
        pd.DataFrame([], columns=["fold", "train_size", "test_size"]).to_csv(folds_output, index=False)

    metrics_payload = {
        "task": task,
        "split": args.split,
        "algorithm": args.algorithm,
        "feature_backend": args.feature_backend,
        "include_descriptors": bool(args.include_descriptors),
        "valid_rows": len(valid_rows),
        "invalid_rows": invalid_rows,
        "holdout": holdout_metrics,
        "cross_validation": fold_summary,
        "test_size": len(test_idx),
        "train_size": len(train_idx),
        "positive_label": positive_label_value,
        "feature_count": len(feature_names),
    }
    metrics_output = Path(args.metrics_output)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.model_output:
        final_model = estimator_for(task, args.algorithm)
        final_model.fit(X, y)
        save_model_bundle(
            args.model_output,
            {
                "task": task,
                "model_kind": "qsar_benchmark",
                "estimator": final_model,
                "feature_backend": args.feature_backend,
                "fingerprint_size": args.fingerprint_size,
                "radius": args.radius,
                "include_descriptors": args.include_descriptors,
                "feature_names": feature_names,
                "positive_label": positive_label_value,
                "benchmark_metrics": metrics_payload,
            },
        )
        print(f"saved model: {args.model_output}")

    print(f"saved metrics: {metrics_output}")
    print(f"saved predictions: {predictions_output}")
    print(f"saved folds: {folds_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
