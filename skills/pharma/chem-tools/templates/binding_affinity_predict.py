#!/usr/bin/env python3
"""Train or apply a ligand binding affinity model from SMILES."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from chem_ml_utils import (
    align_targets_to_valid_rows,
    build_feature_matrix,
    estimator_for,
    load_model_bundle,
    load_smiles_rows,
    save_model_bundle,
)


def read_training_table(path: str, smiles_column: str, id_column: str, target_column: str):
    import pandas as pd

    table = pd.read_csv(path, sep="\t" if path.endswith(".tsv") else ",")
    if target_column not in table.columns:
        raise SystemExit(f"Missing target column: {target_column}")
    rows = load_smiles_rows(input_path=path, smiles=None, smiles_column=smiles_column, id_column=id_column)
    target_map = {
        (str(table.iloc[index][id_column]) if id_column in table.columns else f"row_{index + 1}"): table.iloc[index][target_column]
        for index in range(len(table))
    }
    y = [float(target_map[row.mol_id]) for row in rows]
    return rows, np.asarray(y, dtype=np.float32)


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_true, y_pred)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train or apply a binding affinity model")
    parser.add_argument("--train", help="Training CSV/TSV with SMILES and affinity target")
    parser.add_argument("--predict", help="Prediction CSV/TSV/text input")
    parser.add_argument("--smiles", nargs="*", help="Inline SMILES for prediction")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--target-column", default="affinity")
    parser.add_argument("--model-input", help="Existing model bundle to load")
    parser.add_argument("--model-output", default="affinity_model.joblib")
    parser.add_argument("--predictions-output", default="affinity_predictions.csv")
    parser.add_argument("--metrics-output", default="affinity_metrics.json")
    parser.add_argument("--feature-backend", default="rdkit-morgan", choices=["rdkit-morgan", "rdkit-maccs", "deepchem-circular"])
    parser.add_argument("--fingerprint-size", type=int, default=2048)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--algorithm", default="rf", choices=["rf", "et", "gbr", "ridge"])
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--include-descriptors", action="store_true", default=False)
    parser.add_argument("--affinity-direction", choices=["higher-better", "lower-better"], default="higher-better")
    args = parser.parse_args()

    bundle = None
    metrics: dict[str, float] = {}
    if args.train:
        rows, y = read_training_table(args.train, args.smiles_column, args.id_column, args.target_column)
        X, valid_rows, invalid_rows, feature_names, _ = build_feature_matrix(
            rows,
            feature_backend=args.feature_backend,
            fingerprint_size=args.fingerprint_size,
            radius=args.radius,
            include_descriptors=args.include_descriptors,
        )
        if invalid_rows:
            print(f"warning: skipped {len(invalid_rows)} invalid SMILES during training")
        valid_targets = np.asarray(align_targets_to_valid_rows(rows, y, valid_rows), dtype=np.float32)
        if len(valid_targets) < 4:
            raise SystemExit("Need at least 4 valid labeled molecules to train a binding affinity model.")
        from sklearn.model_selection import train_test_split

        estimator = estimator_for("regression", args.algorithm)
        X_train, X_test, y_train, y_test = train_test_split(X, valid_targets, test_size=args.test_size, random_state=42)
        estimator.fit(X_train, y_train)
        metrics = regression_metrics(y_test, estimator.predict(X_test))
        bundle = {
            "task": "regression",
            "model_kind": "binding_affinity",
            "estimator": estimator,
            "feature_backend": args.feature_backend,
            "fingerprint_size": args.fingerprint_size,
            "radius": args.radius,
            "include_descriptors": args.include_descriptors,
            "feature_names": feature_names,
            "affinity_direction": args.affinity_direction,
        }
        save_model_bundle(args.model_output, bundle)
        Path(args.metrics_output).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"saved model: {args.model_output}")
        print(f"saved metrics: {args.metrics_output}")
    elif args.model_input:
        bundle = load_model_bundle(args.model_input)
    else:
        raise SystemExit("Provide --train or --model-input")

    if args.predict or args.smiles:
        predict_rows = load_smiles_rows(
            input_path=args.predict,
            smiles=args.smiles,
            smiles_column=args.smiles_column,
            id_column=args.id_column,
        )
        X_pred, valid_rows, invalid_rows, _, _ = build_feature_matrix(
            predict_rows,
            feature_backend=bundle["feature_backend"],
            fingerprint_size=bundle["fingerprint_size"],
            radius=bundle["radius"],
            include_descriptors=bundle["include_descriptors"],
        )
        predictions = bundle["estimator"].predict(X_pred)
        output_rows = [
            {"id": row.mol_id, "smiles": row.smiles, "predicted_affinity": float(pred)}
            for row, pred in zip(valid_rows, predictions)
        ]
        for invalid in invalid_rows:
            output_rows.append({"id": invalid["id"], "smiles": invalid["smiles"], "predicted_affinity": ""})
        output_path = Path(args.predictions_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "smiles", "predicted_affinity"])
            writer.writeheader()
            writer.writerows(output_rows)
        print(f"saved predictions: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
