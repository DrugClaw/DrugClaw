#!/usr/bin/env python3
"""Profile a compound library with datamol-backed standardization."""

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
    parser.add_argument("--no-standardize", action="store_true")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    import datamol as dm
    from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
    from rdkit.Chem.Scaffolds import MurckoScaffold

    df = read_table(args.input)
    if args.smiles_column not in df.columns:
        raise SystemExit(f"missing smiles column: {args.smiles_column}")

    ids = df[args.id_column].astype(str) if args.id_column and args.id_column in df.columns else df.index.astype(str)

    rows: list[dict[str, Any]] = []
    scaffold_counts: dict[str, int] = {}
    invalid = 0

    for idx, (record_id, smiles) in enumerate(zip(ids, df[args.smiles_column].fillna("")), start=1):
        smiles = str(smiles).strip()
        row: dict[str, Any] = {"row_index": idx, "record_id": record_id, "input_smiles": smiles}
        try:
            mol = dm.to_mol(smiles)
            if mol is None:
                raise ValueError("invalid smiles")
            if not args.no_standardize:
                mol = dm.standardize_mol(mol)
            canonical = dm.to_smiles(mol)
            inchikey = dm.to_inchikey(mol)
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol) or ""
            scaffold_counts[scaffold] = scaffold_counts.get(scaffold, 0) + 1
            row.update(
                {
                    "valid": True,
                    "canonical_smiles": canonical,
                    "inchikey": inchikey,
                    "murcko_scaffold": scaffold,
                    "molecular_weight": Descriptors.MolWt(mol),
                    "clogp": Crippen.MolLogP(mol),
                    "tpsa": rdMolDescriptors.CalcTPSA(mol),
                    "hbd": Lipinski.NumHDonors(mol),
                    "hba": Lipinski.NumHAcceptors(mol),
                    "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
                    "rings": Lipinski.RingCount(mol),
                    "fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            invalid += 1
            row.update({"valid": False, "error": str(exc)})
        rows.append(row)

    profiled = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    profiled.to_csv(args.output, index=False)

    valid_df = profiled[profiled["valid"] == True]  # noqa: E712
    summary = {
        "input_path": str(args.input),
        "rows": int(len(profiled)),
        "valid_molecules": int(len(valid_df)),
        "invalid_molecules": int(invalid),
        "unique_inchikeys": int(valid_df["inchikey"].nunique()) if not valid_df.empty else 0,
        "unique_scaffolds": int(valid_df["murcko_scaffold"].replace("", pd.NA).dropna().nunique()) if not valid_df.empty else 0,
        "top_scaffolds": sorted(
            ({"scaffold": key, "count": value} for key, value in scaffold_counts.items() if key),
            key=lambda item: (-item["count"], item["scaffold"]),
        )[:10],
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
