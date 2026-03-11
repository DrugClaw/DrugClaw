#!/usr/bin/env python3
"""Train or apply a structure-aware protein-ligand affinity model."""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from chem_ml_utils import (
    estimator_for,
    load_model_bundle,
    predict_with_uncertainty,
    rdkit_descriptor_dict,
    save_model_bundle,
)

RESIDUE_CATEGORY_MAP = {
    "aromatic": {"PHE", "TYR", "TRP", "HIS"},
    "acidic": {"ASP", "GLU"},
    "basic": {"LYS", "ARG", "HIS"},
    "polar": {"SER", "THR", "ASN", "GLN", "CYS", "TYR", "HIS"},
    "hydrophobic": {"ALA", "VAL", "LEU", "ILE", "PRO", "MET", "PHE", "TRP", "TYR"},
}
ATOM_CATEGORIES = ["C", "N", "O", "S", "P", "halogen", "metal", "other"]
DISTANCE_BINS = [(0.0, 3.5, "lt3_5"), (3.5, 5.0, "3_5_5_0"), (5.0, 6.0, "5_0_6_0")]
COMMON_METALS = {"ZN", "MG", "MN", "CA", "FE", "CU", "CO", "NI", "NA", "K"}


@dataclass
class AtomRecord:
    atom_name: str
    resname: str
    chain: str
    resseq: str
    element: str
    x: float
    y: float
    z: float
    is_hetatm: bool


@dataclass
class StructureRow:
    sample_id: str
    receptor_path: Optional[Path]
    ligand_path: Optional[Path]
    complex_path: Optional[Path]
    smiles: str | None
    extras: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train or apply a structure-aware affinity model from complexes")
    parser.add_argument("--train", help="Training CSV/TSV with structure paths and affinity target")
    parser.add_argument("--predict", help="Prediction CSV/TSV with structure paths")
    parser.add_argument("--sample-id", default="sample_1", help="Identifier for single-sample prediction")
    parser.add_argument("--complex", help="Single complex PDB/PDBQT path for prediction")
    parser.add_argument("--receptor", help="Single receptor PDB/PDBQT path for prediction")
    parser.add_argument("--ligand", help="Single ligand PDB/PDBQT path for prediction")
    parser.add_argument("--smiles", help="Optional SMILES for ligand descriptors")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--target-column", default="affinity")
    parser.add_argument("--receptor-path-column", default="receptor_path")
    parser.add_argument("--ligand-path-column", default="ligand_path")
    parser.add_argument("--complex-path-column", default="complex_path")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--ligand-chain-column", default="ligand_chain")
    parser.add_argument("--ligand-resname-column", default="ligand_resname")
    parser.add_argument("--ligand-resseq-column", default="ligand_resseq")
    parser.add_argument("--model-input", help="Existing model bundle to load")
    parser.add_argument("--model-output", default="protein_ligand_affinity.joblib")
    parser.add_argument("--predictions-output", default="protein_ligand_affinity_predictions.csv")
    parser.add_argument("--metrics-output", default="protein_ligand_affinity_metrics.json")
    parser.add_argument("--features-output", default="protein_ligand_affinity_features.csv")
    parser.add_argument("--algorithm", default="rf", choices=["rf", "et", "gbr", "ridge"])
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--contact-cutoff", type=float, default=6.0)
    parser.add_argument("--pocket-cutoff", type=float, default=8.0)
    parser.add_argument("--disable-ligand-descriptors", action="store_true", default=False)
    parser.add_argument("--affinity-direction", choices=["higher-better", "lower-better"], default="higher-better")
    return parser.parse_args()


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    metrics = {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
    }
    if len(y_true) >= 2:
        r2 = float(r2_score(y_true, y_pred))
        if math.isfinite(r2):
            metrics["r2"] = r2
    try:
        from scipy.stats import spearmanr

        statistic = float(spearmanr(y_true, y_pred).statistic)
        if math.isfinite(statistic):
            metrics["spearman"] = statistic
    except Exception:
        pass
    return metrics


def element_from_line(line: str) -> str:
    element = line[76:78].strip().upper()
    if element:
        return element
    atom_name = line[12:16].strip().upper()
    letters = "".join(ch for ch in atom_name if ch.isalpha())
    if not letters:
        return "X"
    if len(letters) >= 2 and letters[:2] in COMMON_METALS:
        return letters[:2]
    return letters[0]


def parse_atom_line(line: str) -> Optional[AtomRecord]:
    if not line.startswith(("ATOM", "HETATM")):
        return None
    try:
        return AtomRecord(
            atom_name=line[12:16].strip(),
            resname=line[17:20].strip().upper(),
            chain=line[21].strip() or "_",
            resseq=line[22:26].strip() or "0",
            element=element_from_line(line),
            x=float(line[30:38].strip()),
            y=float(line[38:46].strip()),
            z=float(line[46:54].strip()),
            is_hetatm=line.startswith("HETATM"),
        )
    except Exception:
        return None


def load_atoms(path: Path) -> list[AtomRecord]:
    suffix = path.suffix.lower()
    if suffix in {".pdb", ".pdbqt", ".ent"}:
        atoms: list[AtomRecord] = []
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                atom = parse_atom_line(line)
                if atom is not None and atom.resname != "HOH":
                    atoms.append(atom)
        if not atoms:
            raise RuntimeError(f"No atoms parsed from {path}")
        return atoms
    if suffix in {".sdf", ".mol", ".mol2"}:
        try:
            from rdkit import Chem
        except Exception as exc:
            raise RuntimeError(f"RDKit is required to parse {path}: {exc}")
        if suffix == ".sdf":
            supplier = Chem.SDMolSupplier(str(path), removeHs=False)
            mol = next((item for item in supplier if item is not None), None)
        elif suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(path), removeHs=False)
        else:
            mol = Chem.MolFromMolFile(str(path), removeHs=False)
        if mol is None or not mol.GetNumConformers():
            raise RuntimeError(f"RDKit could not load coordinates from {path}")
        conformer = mol.GetConformer()
        atoms = []
        for atom in mol.GetAtoms():
            position = conformer.GetAtomPosition(atom.GetIdx())
            atoms.append(
                AtomRecord(
                    atom_name=atom.GetSymbol(),
                    resname="LIG",
                    chain="L",
                    resseq="1",
                    element=atom.GetSymbol().upper(),
                    x=float(position.x),
                    y=float(position.y),
                    z=float(position.z),
                    is_hetatm=True,
                )
            )
        return atoms
    raise RuntimeError(f"Unsupported structure format for {path}. Use PDB, PDBQT, SDF, MOL, or MOL2.")


def resolve_path(value: Any, *, base_dir: Path) -> Optional[Path]:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() == "nan":
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def read_rows(
    *,
    input_path: str | None,
    sample_id: str,
    complex_path: str | None,
    receptor_path: str | None,
    ligand_path: str | None,
    smiles: str | None,
    id_column: str,
    receptor_path_column: str,
    ligand_path_column: str,
    complex_path_column: str,
    smiles_column: str,
) -> list[StructureRow]:
    rows: list[StructureRow] = []
    if input_path:
        import pandas as pd

        table = pd.read_csv(input_path, sep="\t" if input_path.endswith(".tsv") else ",")
        base_dir = Path(input_path).resolve().parent
        for index, row in table.iterrows():
            row_id = str(row[id_column]) if id_column in table.columns else f"row_{index + 1}"
            rows.append(
                StructureRow(
                    sample_id=row_id,
                    receptor_path=resolve_path(row.get(receptor_path_column), base_dir=base_dir),
                    ligand_path=resolve_path(row.get(ligand_path_column), base_dir=base_dir),
                    complex_path=resolve_path(row.get(complex_path_column), base_dir=base_dir),
                    smiles=str(row[smiles_column]) if smiles_column in table.columns and str(row[smiles_column]).strip() not in {"", "nan"} else None,
                    extras=row.to_dict(),
                )
            )
        return rows
    base_dir = Path.cwd()
    rows.append(
        StructureRow(
            sample_id=sample_id,
            receptor_path=resolve_path(receptor_path, base_dir=base_dir),
            ligand_path=resolve_path(ligand_path, base_dir=base_dir),
            complex_path=resolve_path(complex_path, base_dir=base_dir),
            smiles=smiles,
            extras={},
        )
    )
    return rows


def atom_category(element: str) -> str:
    normalized = element.upper()
    if normalized in {"C"}:
        return "C"
    if normalized in {"N"}:
        return "N"
    if normalized in {"O"}:
        return "O"
    if normalized in {"S"}:
        return "S"
    if normalized in {"P"}:
        return "P"
    if normalized in {"F", "CL", "BR", "I"}:
        return "halogen"
    if normalized in COMMON_METALS:
        return "metal"
    return "other"


def residue_category(resname: str) -> str:
    for category, residues in RESIDUE_CATEGORY_MAP.items():
        if resname in residues:
            return category
    return "other"


def choose_ligand_signature(atoms: list[AtomRecord], extras: dict[str, Any]) -> tuple[str, str, str]:
    requested_chain = str(extras.get("ligand_chain", extras.get("ligand_chain_column", ""))).strip()
    requested_resname = str(extras.get("ligand_resname", "")).strip().upper()
    requested_resseq = str(extras.get("ligand_resseq", "")).strip()
    het_atoms = [atom for atom in atoms if atom.is_hetatm and atom.resname != "HOH"]
    if not het_atoms:
        raise RuntimeError("Complex file does not contain non-water HETATM records for ligand extraction.")
    if requested_chain or requested_resname or requested_resseq:
        matches = [
            atom
            for atom in het_atoms
            if (not requested_chain or atom.chain == requested_chain)
            and (not requested_resname or atom.resname == requested_resname)
            and (not requested_resseq or atom.resseq == requested_resseq)
        ]
        if matches:
            first = matches[0]
            return first.chain, first.resname, first.resseq
    chain_l = [atom for atom in het_atoms if atom.chain == "L"]
    if chain_l:
        first = chain_l[0]
        return first.chain, first.resname, first.resseq
    counts: dict[tuple[str, str, str], int] = {}
    for atom in het_atoms:
        key = (atom.chain, atom.resname, atom.resseq)
        counts[key] = counts.get(key, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


def split_complex_atoms(atoms: list[AtomRecord], extras: dict[str, Any]) -> tuple[list[AtomRecord], list[AtomRecord]]:
    chain, resname, resseq = choose_ligand_signature(atoms, extras)
    ligand_atoms = [atom for atom in atoms if atom.is_hetatm and atom.chain == chain and atom.resname == resname and atom.resseq == resseq]
    receptor_atoms = [atom for atom in atoms if atom not in ligand_atoms and atom.resname != "HOH"]
    receptor_atoms = [atom for atom in receptor_atoms if not atom.is_hetatm or atom.resname in COMMON_METALS]
    if not receptor_atoms:
        receptor_atoms = [atom for atom in atoms if atom not in ligand_atoms]
    return receptor_atoms, ligand_atoms


def load_structure_pair(row: StructureRow) -> tuple[list[AtomRecord], list[AtomRecord]]:
    if row.complex_path:
        atoms = load_atoms(row.complex_path)
        return split_complex_atoms(atoms, row.extras)
    if row.receptor_path and row.ligand_path:
        receptor_atoms = [atom for atom in load_atoms(row.receptor_path) if atom.resname != "HOH"]
        ligand_atoms = [atom for atom in load_atoms(row.ligand_path) if atom.resname != "HOH"]
        return receptor_atoms, ligand_atoms
    raise RuntimeError(f"Row {row.sample_id} must provide complex_path or receptor_path + ligand_path")


def rdkit_ligand_descriptors(smiles: str | None, ligand_path: Path | None) -> dict[str, float]:
    try:
        from rdkit import Chem
    except Exception:
        return {}
    mol = None
    if smiles:
        mol = Chem.MolFromSmiles(smiles)
    if mol is None and ligand_path and ligand_path.exists():
        try:
            suffix = ligand_path.suffix.lower()
            if suffix in {".pdb", ".pdbqt", ".ent"}:
                mol = Chem.MolFromPDBFile(str(ligand_path), removeHs=False)
            elif suffix == ".sdf":
                supplier = Chem.SDMolSupplier(str(ligand_path), removeHs=False)
                mol = next((item for item in supplier if item is not None), None)
            elif suffix == ".mol2":
                mol = Chem.MolFromMol2File(str(ligand_path), removeHs=False)
            elif suffix == ".mol":
                mol = Chem.MolFromMolFile(str(ligand_path), removeHs=False)
        except Exception:
            mol = None
    if mol is None:
        return {}
    descriptors = rdkit_descriptor_dict(mol)
    descriptors["ligand_aromatic_atoms"] = float(sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic()))
    descriptors["ligand_formal_charge_sum"] = float(sum(atom.GetFormalCharge() for atom in mol.GetAtoms()))
    return descriptors


def initialize_feature_map() -> dict[str, float]:
    features = {
        "ligand_atom_count": 0.0,
        "receptor_atom_count": 0.0,
        "pocket_atom_count": 0.0,
        "pocket_residue_count": 0.0,
        "min_contact_distance": 99.0,
        "mean_contact_distance": 99.0,
        "median_contact_distance": 99.0,
        "ligand_centroid_to_pocket_centroid": 0.0,
        "hydrophobic_contacts": 0.0,
        "polar_contacts": 0.0,
        "hbond_proxy_contacts": 0.0,
        "close_contacts": 0.0,
    }
    for _, _, label in DISTANCE_BINS:
        features[f"contacts_{label}"] = 0.0
    for ligand_category in ATOM_CATEGORIES:
        features[f"ligand_atom_{ligand_category}"] = 0.0
        features[f"pocket_atom_{ligand_category}"] = 0.0
        for receptor_category in ATOM_CATEGORIES:
            for _, _, label in DISTANCE_BINS:
                features[f"pair_{label}_{ligand_category}_{receptor_category}"] = 0.0
    for category in [*RESIDUE_CATEGORY_MAP.keys(), "other"]:
        features[f"pocket_residue_{category}"] = 0.0
    return features


def compute_structure_features(
    receptor_atoms: list[AtomRecord],
    ligand_atoms: list[AtomRecord],
    *,
    smiles: str | None,
    ligand_path: Path | None,
    contact_cutoff: float,
    pocket_cutoff: float,
    include_ligand_descriptors: bool,
) -> dict[str, float]:
    features = initialize_feature_map()
    receptor_coords = np.asarray([[atom.x, atom.y, atom.z] for atom in receptor_atoms], dtype=np.float32)
    ligand_coords = np.asarray([[atom.x, atom.y, atom.z] for atom in ligand_atoms], dtype=np.float32)
    features["ligand_atom_count"] = float(len(ligand_atoms))
    features["receptor_atom_count"] = float(len(receptor_atoms))
    if receptor_coords.size == 0 or ligand_coords.size == 0:
        return features

    receptor_categories = [atom_category(atom.element) for atom in receptor_atoms]
    ligand_categories = [atom_category(atom.element) for atom in ligand_atoms]
    for category in ligand_categories:
        features[f"ligand_atom_{category}"] += 1.0

    deltas = ligand_coords[:, None, :] - receptor_coords[None, :, :]
    distances = np.linalg.norm(deltas, axis=2)
    contact_mask = distances <= contact_cutoff
    pocket_mask = distances <= pocket_cutoff
    pocket_atom_indices = np.where(pocket_mask.any(axis=0))[0].tolist()
    features["pocket_atom_count"] = float(len(pocket_atom_indices))
    for index in pocket_atom_indices:
        features[f"pocket_atom_{receptor_categories[index]}"] += 1.0
    pocket_residues = {(receptor_atoms[index].chain, receptor_atoms[index].resseq, receptor_atoms[index].resname) for index in pocket_atom_indices}
    features["pocket_residue_count"] = float(len(pocket_residues))
    for _, _, resname in pocket_residues:
        features[f"pocket_residue_{residue_category(resname)}"] += 1.0

    contact_distances = distances[contact_mask]
    if contact_distances.size:
        features["min_contact_distance"] = float(contact_distances.min())
        features["mean_contact_distance"] = float(contact_distances.mean())
        features["median_contact_distance"] = float(np.median(contact_distances))
        features["close_contacts"] = float(np.count_nonzero(contact_distances <= 4.0))
    ligand_centroid = ligand_coords.mean(axis=0)
    if pocket_atom_indices:
        pocket_centroid = receptor_coords[pocket_atom_indices].mean(axis=0)
        features["ligand_centroid_to_pocket_centroid"] = float(np.linalg.norm(ligand_centroid - pocket_centroid))

    for lig_index, ligand_category in enumerate(ligand_categories):
        contact_indices = np.where(contact_mask[lig_index])[0]
        for rec_index in contact_indices:
            rec_category = receptor_categories[rec_index]
            dist = float(distances[lig_index, rec_index])
            for low, high, label in DISTANCE_BINS:
                if low <= dist < high:
                    features[f"contacts_{label}"] += 1.0
                    features[f"pair_{label}_{ligand_category}_{rec_category}"] += 1.0
                    break
            receptor_atom = receptor_atoms[rec_index]
            if ligand_category == "C" and rec_category in {"C", "S"} and receptor_atom.resname in RESIDUE_CATEGORY_MAP["hydrophobic"] and dist <= 4.5:
                features["hydrophobic_contacts"] += 1.0
            if ligand_category in {"N", "O", "S"} and rec_category in {"N", "O", "S"} and dist <= 3.7:
                features["polar_contacts"] += 1.0
            if ligand_category in {"N", "O"} and rec_category in {"N", "O"} and dist <= 3.5:
                features["hbond_proxy_contacts"] += 1.0

    if include_ligand_descriptors:
        for key, value in rdkit_ligand_descriptors(smiles, ligand_path).items():
            features[key] = float(value)
    return features


def feature_matrix(
    rows: list[StructureRow],
    *,
    contact_cutoff: float,
    pocket_cutoff: float,
    include_ligand_descriptors: bool,
) -> tuple[np.ndarray, list[StructureRow], list[dict[str, str]], list[str], list[dict[str, Any]]]:
    valid_rows: list[StructureRow] = []
    invalid_rows: list[dict[str, str]] = []
    feature_rows: list[dict[str, Any]] = []
    feature_names: list[str] = []
    for row in rows:
        try:
            receptor_atoms, ligand_atoms = load_structure_pair(row)
            features = compute_structure_features(
                receptor_atoms,
                ligand_atoms,
                smiles=row.smiles,
                ligand_path=row.ligand_path,
                contact_cutoff=contact_cutoff,
                pocket_cutoff=pocket_cutoff,
                include_ligand_descriptors=include_ligand_descriptors,
            )
        except Exception as exc:
            invalid_rows.append({"id": row.sample_id, "reason": str(exc)})
            continue
        if not feature_names:
            feature_names = sorted(features.keys())
        valid_rows.append(row)
        feature_rows.append({"id": row.sample_id, **features})
    if not valid_rows:
        raise SystemExit("No valid structures remained after parsing.")
    matrix = np.asarray([[row[name] for name in feature_names] for row in feature_rows], dtype=np.float32)
    return matrix, valid_rows, invalid_rows, feature_names, feature_rows


def read_training_targets(path: str, id_column: str, target_column: str) -> dict[str, float]:
    import pandas as pd

    table = pd.read_csv(path, sep="\t" if path.endswith(".tsv") else ",")
    if target_column not in table.columns:
        raise SystemExit(f"Missing target column: {target_column}")
    target_map: dict[str, float] = {}
    for index, row in table.iterrows():
        row_id = str(row[id_column]) if id_column in table.columns else f"row_{index + 1}"
        target_map[row_id] = float(row[target_column])
    return target_map


def write_feature_rows(path: str, feature_rows: list[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(feature_rows[0].keys()))
        writer.writeheader()
        writer.writerows(feature_rows)


def main() -> int:
    args = parse_args()
    bundle = None
    metrics: dict[str, Any] = {}
    if args.train:
        rows = read_rows(
            input_path=args.train,
            sample_id=args.sample_id,
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
        target_map = read_training_targets(args.train, args.id_column, args.target_column)
        X, valid_rows, invalid_rows, feature_names, feature_rows = feature_matrix(
            rows,
            contact_cutoff=args.contact_cutoff,
            pocket_cutoff=args.pocket_cutoff,
            include_ligand_descriptors=not args.disable_ligand_descriptors,
        )
        y = np.asarray([target_map[row.sample_id] for row in valid_rows], dtype=np.float32)
        if len(y) < 4:
            raise SystemExit("Need at least 4 valid structure-labeled samples to train a protein-ligand affinity model.")
        write_feature_rows(args.features_output, feature_rows)
        from sklearn.model_selection import train_test_split

        estimator = estimator_for("regression", args.algorithm)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=args.test_size, random_state=42)
        estimator.fit(X_train, y_train)
        predictions, uncertainty = predict_with_uncertainty(estimator, X_test, task="regression")
        metrics = regression_metrics(y_test, predictions.astype(np.float32))
        if uncertainty is not None:
            metrics["holdout_uncertainty_mean"] = float(np.mean(uncertainty))
        if hasattr(estimator, "feature_importances_"):
            top = sorted(zip(feature_names, [float(value) for value in estimator.feature_importances_]), key=lambda item: item[1], reverse=True)[:20]
            metrics["top_feature_importance"] = [{"feature": key, "importance": value} for key, value in top]
        metrics["invalid_rows"] = invalid_rows
        metrics["valid_rows"] = len(valid_rows)
        bundle = {
            "task": "regression",
            "model_kind": "protein_ligand_affinity",
            "estimator": estimator,
            "feature_names": feature_names,
            "contact_cutoff": args.contact_cutoff,
            "pocket_cutoff": args.pocket_cutoff,
            "include_ligand_descriptors": not args.disable_ligand_descriptors,
            "affinity_direction": args.affinity_direction,
        }
        save_model_bundle(args.model_output, bundle)
        Path(args.metrics_output).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"saved model: {args.model_output}")
        print(f"saved metrics: {args.metrics_output}")
        print(f"saved features: {args.features_output}")
    elif args.model_input:
        bundle = load_model_bundle(args.model_input)
    else:
        raise SystemExit("Provide --train or --model-input")

    if args.predict or args.complex or (args.receptor and args.ligand):
        rows = read_rows(
            input_path=args.predict,
            sample_id=args.sample_id,
            complex_path=args.complex,
            receptor_path=args.receptor,
            ligand_path=args.ligand,
            smiles=args.smiles,
            id_column=args.id_column,
            receptor_path_column=args.receptor_path_column,
            ligand_path_column=args.ligand_path_column,
            complex_path_column=args.complex_path_column,
            smiles_column=args.smiles_column,
        )
        X_pred, valid_rows, invalid_rows, feature_names, feature_rows = feature_matrix(
            rows,
            contact_cutoff=float(bundle.get("contact_cutoff", args.contact_cutoff)),
            pocket_cutoff=float(bundle.get("pocket_cutoff", args.pocket_cutoff)),
            include_ligand_descriptors=bool(bundle.get("include_ligand_descriptors", not args.disable_ligand_descriptors)),
        )
        if feature_names != bundle["feature_names"]:
            aligned_feature_rows = []
            for row in feature_rows:
                aligned_feature_rows.append({name: row.get(name, 0.0) for name in bundle["feature_names"]})
            X_pred = np.asarray([[row[name] for name in bundle["feature_names"]] for row in aligned_feature_rows], dtype=np.float32)
        predictions, uncertainty = predict_with_uncertainty(bundle["estimator"], X_pred, task="regression")
        output_rows = []
        for index, row in enumerate(valid_rows):
            output = {
                "id": row.sample_id,
                "predicted_affinity": float(predictions[index]),
                "receptor_path": str(row.receptor_path) if row.receptor_path else "",
                "ligand_path": str(row.ligand_path) if row.ligand_path else "",
                "complex_path": str(row.complex_path) if row.complex_path else "",
                "smiles": row.smiles or "",
            }
            if uncertainty is not None:
                output["prediction_uncertainty"] = float(uncertainty[index])
            output_rows.append(output)
        for invalid in invalid_rows:
            output_rows.append({"id": invalid["id"], "predicted_affinity": "", "error": invalid["reason"]})
        output_path = Path(args.predictions_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in output_rows for key in row.keys()}))
            writer.writeheader()
            writer.writerows(output_rows)
        print(f"saved predictions: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
