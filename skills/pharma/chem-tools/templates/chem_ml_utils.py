#!/usr/bin/env python3
"""Shared helpers for DrugClaw chemistry ML templates."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import joblib
import numpy as np


@dataclass
class MolRow:
    mol_id: str
    smiles: str
    extras: dict[str, Any]


def load_smiles_rows(
    *,
    input_path: str | None,
    smiles: list[str] | None,
    smiles_column: str,
    id_column: str,
) -> list[MolRow]:
    rows: list[MolRow] = []
    if smiles:
        for index, value in enumerate(smiles, 1):
            rows.append(MolRow(mol_id=f"mol_{index}", smiles=value, extras={}))
    if input_path:
        path = Path(input_path)
        suffix = path.suffix.lower()
        if suffix in {".csv", ".tsv"}:
            import pandas as pd

            frame = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
            for index, row in frame.iterrows():
                mol_id = str(row[id_column]) if id_column in frame.columns else f"row_{index + 1}"
                extras = row.to_dict()
                rows.append(MolRow(mol_id=mol_id, smiles=str(row[smiles_column]), extras=extras))
        else:
            with path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle, 1):
                    clean = line.strip()
                    if clean:
                        rows.append(MolRow(mol_id=f"line_{index}", smiles=clean, extras={}))
    if not rows:
        raise SystemExit("No SMILES provided. Use --smiles or --input.")
    return rows


def infer_positive_label(classes: list[Any]) -> Any:
    preferred = ["active", "1", 1, True, "true", "yes", "binder", "hit"]
    normalized = {str(value).lower(): value for value in classes}
    for key in preferred:
        if str(key).lower() in normalized:
            return normalized[str(key).lower()]
    return classes[-1]


def resolve_class_label(classes: Iterable[Any], requested: Any | None) -> Any:
    class_list = list(classes)
    if not class_list:
        raise SystemExit("Model does not expose any classes.")
    if requested is None:
        return infer_positive_label(class_list)
    requested_text = str(requested).lower()
    for value in class_list:
        if value == requested or str(value).lower() == requested_text:
            return value
    raise SystemExit(f"Requested positive label {requested!r} not found in model classes: {class_list}")


def align_targets_to_valid_rows(
    rows: Iterable[MolRow],
    targets: Iterable[Any],
    valid_rows: Iterable[MolRow],
) -> list[Any]:
    target_map = {row.mol_id: target for row, target in zip(rows, targets)}
    return [target_map[row.mol_id] for row in valid_rows]


def infer_task_from_targets(values: Iterable[Any]) -> str:
    items = [value for value in values if value is not None and str(value).strip() != ""]
    if not items:
        raise SystemExit("Cannot infer task from empty targets.")
    numeric_values: list[float] = []
    for value in items:
        try:
            numeric_values.append(float(value))
        except Exception:
            return "classification"
    unique = {round(value, 8) for value in numeric_values}
    if unique <= {0.0, 1.0}:
        return "classification"
    return "regression" if len(unique) > 4 else "classification"


def scaffold_for_smiles(smiles: str) -> str:
    from rdkit import Chem
    from rdkit.Chem.Scaffolds import MurckoScaffold

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "invalid"
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
    return scaffold or smiles


def scaffold_split_indices(rows: list[MolRow], *, test_size: float) -> tuple[list[int], list[int], list[str]]:
    groups: dict[str, list[int]] = {}
    scaffolds: list[str] = []
    for index, row in enumerate(rows):
        scaffold = scaffold_for_smiles(row.smiles)
        scaffolds.append(scaffold)
        groups.setdefault(scaffold, []).append(index)
    ordered_groups = sorted(groups.values(), key=len, reverse=True)
    target_test = max(1, int(round(len(rows) * test_size)))
    test_indices: list[int] = []
    for group in ordered_groups:
        if len(test_indices) >= target_test and test_indices:
            break
        test_indices.extend(group)
    test_set = set(test_indices)
    train_indices = [index for index in range(len(rows)) if index not in test_set]
    if not train_indices:
        fallback = max(1, len(rows) - max(1, target_test))
        train_indices = list(range(fallback))
        test_set = set(range(fallback, len(rows)))
    return train_indices, sorted(test_set), scaffolds


def rdkit_descriptor_dict(mol) -> dict[str, float]:
    from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

    formal_charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    return {
        "mol_wt": float(Descriptors.MolWt(mol)),
        "logp": float(Crippen.MolLogP(mol)),
        "hbd": float(Lipinski.NumHDonors(mol)),
        "hba": float(Lipinski.NumHAcceptors(mol)),
        "rot_bonds": float(Lipinski.NumRotatableBonds(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "rings": float(rdMolDescriptors.CalcNumRings(mol)),
        "heavy_atoms": float(mol.GetNumHeavyAtoms()),
        "fraction_csp3": float(rdMolDescriptors.CalcFractionCSP3(mol)),
        "formal_charge": float(formal_charge),
    }


def _bitvect_to_array(bitvect, n_bits: int) -> np.ndarray:
    from rdkit import DataStructs

    arr = np.zeros((n_bits,), dtype=np.float32)
    DataStructs.ConvertToNumpyArray(bitvect, arr)
    return arr


def build_feature_matrix(
    rows: Iterable[MolRow],
    *,
    feature_backend: str,
    fingerprint_size: int,
    radius: int,
    include_descriptors: bool,
) -> tuple[np.ndarray, list[MolRow], list[dict[str, str]], list[str], list[dict[str, Any]]]:
    from rdkit import Chem
    from rdkit.Chem import AllChem, MACCSkeys

    row_list = list(rows)
    valid_rows: list[MolRow] = []
    invalid_rows: list[dict[str, str]] = []
    descriptor_rows: list[dict[str, Any]] = []
    mols = []
    for row in row_list:
        mol = Chem.MolFromSmiles(row.smiles)
        if mol is None:
            invalid_rows.append({"id": row.mol_id, "smiles": row.smiles})
            continue
        valid_rows.append(row)
        descriptor_rows.append({"id": row.mol_id, "smiles": row.smiles, **rdkit_descriptor_dict(mol)})
        mols.append(mol)
    if not valid_rows:
        raise SystemExit("No valid SMILES remained after parsing.")

    feature_names: list[str] = []
    fp_matrix: np.ndarray
    if feature_backend == "rdkit-morgan":
        fp_rows = []
        for mol in mols:
            bitvect = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=fingerprint_size)
            fp_rows.append(_bitvect_to_array(bitvect, fingerprint_size))
        fp_matrix = np.asarray(fp_rows, dtype=np.float32)
        feature_names = [f"fp_{i}" for i in range(fingerprint_size)]
    elif feature_backend == "rdkit-maccs":
        fp_rows = []
        for mol in mols:
            bitvect = MACCSkeys.GenMACCSKeys(mol)
            fp_rows.append(_bitvect_to_array(bitvect, bitvect.GetNumBits()))
        fp_matrix = np.asarray(fp_rows, dtype=np.float32)
        feature_names = [f"maccs_{i}" for i in range(fp_matrix.shape[1])]
    elif feature_backend == "deepchem-circular":
        try:
            import deepchem as dc
        except Exception as exc:
            raise SystemExit(f"DeepChem backend unavailable: {exc}")
        featurizer = dc.feat.CircularFingerprint(size=fingerprint_size, radius=radius)
        fp_matrix = np.asarray(featurizer.featurize([row.smiles for row in valid_rows]), dtype=np.float32)
        feature_names = [f"dc_fp_{i}" for i in range(fp_matrix.shape[1])]
    else:
        raise SystemExit(f"Unsupported feature backend: {feature_backend}")

    if include_descriptors:
        descriptor_keys = [key for key in descriptor_rows[0].keys() if key not in {"id", "smiles"}]
        descriptor_matrix = np.asarray([[row[key] for key in descriptor_keys] for row in descriptor_rows], dtype=np.float32)
        fp_matrix = np.concatenate([fp_matrix, descriptor_matrix], axis=1)
        feature_names.extend(descriptor_keys)

    return fp_matrix, valid_rows, invalid_rows, feature_names, descriptor_rows


def estimator_for(task: str, algorithm: str):
    if task == "regression":
        from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
        from sklearn.linear_model import Ridge

        mapping = {
            "rf": RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1),
            "et": ExtraTreesRegressor(n_estimators=300, random_state=42, n_jobs=-1),
            "gbr": GradientBoostingRegressor(random_state=42),
            "ridge": Ridge(alpha=1.0),
        }
    else:
        from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression

        mapping = {
            "rf": RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1),
            "et": ExtraTreesClassifier(n_estimators=300, random_state=42, n_jobs=-1),
            "logreg": LogisticRegression(max_iter=5000),
        }
    if algorithm not in mapping:
        raise SystemExit(f"Unsupported algorithm for {task}: {algorithm}")
    return mapping[algorithm]


def save_model_bundle(path: str | Path, bundle: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out)


def load_model_bundle(path: str | Path) -> dict[str, Any]:
    return joblib.load(Path(path))


def normalize_series(values: list[float], *, higher_is_better: bool) -> list[float]:
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if abs(max_value - min_value) < 1e-12:
        return [1.0 for _ in values]
    scaled = [(value - min_value) / (max_value - min_value) for value in values]
    return scaled if higher_is_better else [1.0 - value for value in scaled]


def predict_with_uncertainty(
    estimator,
    X: np.ndarray,
    *,
    task: str,
    positive_label: Any | None = None,
) -> tuple[np.ndarray, np.ndarray | None]:
    predictions = np.asarray(estimator.predict(X))
    if not hasattr(estimator, "estimators_"):
        return predictions, None
    if task == "regression":
        try:
            member_predictions = np.asarray([member.predict(X) for member in estimator.estimators_], dtype=np.float32)
        except Exception:
            return predictions, None
        return predictions, member_predictions.std(axis=0)
    if not hasattr(estimator, "classes_"):
        return predictions, None
    label = resolve_class_label(estimator.classes_, positive_label)
    probability_rows: list[np.ndarray] = []
    for member in getattr(estimator, "estimators_", []):
        if not hasattr(member, "predict_proba"):
            continue
        base_probs = member.predict_proba(X)
        base_classes = list(getattr(member, "classes_", []))
        if label in base_classes:
            probability_rows.append(np.asarray(base_probs[:, base_classes.index(label)], dtype=np.float32))
        else:
            probability_rows.append(np.zeros((X.shape[0],), dtype=np.float32))
    if not probability_rows:
        return predictions, None
    stacked = np.asarray(probability_rows, dtype=np.float32)
    return predictions, stacked.std(axis=0)
