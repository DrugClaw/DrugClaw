#!/usr/bin/env python3
"""Compute common RDKit descriptors and simple drug-likeness flags."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_rows(args: argparse.Namespace) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if args.smiles:
        for index, smiles in enumerate(args.smiles, 1):
            rows.append((f"mol_{index}", smiles))
    if args.input:
        path = Path(args.input)
        suffix = path.suffix.lower()
        if suffix in {".csv", ".tsv"}:
            import pandas as pd

            frame = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
            for index, row in frame.iterrows():
                mol_id = str(row[args.id_column]) if args.id_column in frame.columns else f"row_{index + 1}"
                rows.append((mol_id, str(row[args.smiles_column])))
        else:
            with path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle, 1):
                    clean = line.strip()
                    if clean:
                        rows.append((f"line_{index}", clean))
    if not rows:
        raise SystemExit("No SMILES provided. Use --smiles or --input.")
    return rows


def lipinski_ok(mw: float, logp: float, hbd: int, hba: int) -> bool:
    return mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10


def veber_ok(rot_bonds: int, tpsa: float) -> bool:
    return rot_bonds <= 10 and tpsa <= 140


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute RDKit descriptors and drug-likeness flags")
    parser.add_argument("--input", help="CSV/TSV/text input containing SMILES")
    parser.add_argument("--smiles", nargs="*", help="Inline SMILES strings")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--output", default="rdkit_descriptors.csv")
    parser.add_argument("--summary", default="rdkit_summary.json")
    args = parser.parse_args()

    try:
        import pandas as pd
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
    except Exception as exc:
        raise SystemExit(f"RDKit runtime is unavailable: {exc}")

    rows = load_rows(args)
    results: list[dict[str, object]] = []
    invalid: list[dict[str, str]] = []
    for mol_id, smiles in rows:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            invalid.append({"id": mol_id, "smiles": smiles})
            continue
        mw = float(Descriptors.MolWt(mol))
        logp = float(Crippen.MolLogP(mol))
        hbd = int(Lipinski.NumHDonors(mol))
        hba = int(Lipinski.NumHAcceptors(mol))
        rot_bonds = int(Lipinski.NumRotatableBonds(mol))
        tpsa = float(rdMolDescriptors.CalcTPSA(mol))
        rings = int(rdMolDescriptors.CalcNumRings(mol))
        heavy_atoms = int(mol.GetNumHeavyAtoms())
        results.append(
            {
                "id": mol_id,
                "smiles": smiles,
                "mol_wt": mw,
                "logp": logp,
                "hbd": hbd,
                "hba": hba,
                "rot_bonds": rot_bonds,
                "tpsa": tpsa,
                "rings": rings,
                "heavy_atoms": heavy_atoms,
                "lipinski_ok": lipinski_ok(mw, logp, hbd, hba),
                "veber_ok": veber_ok(rot_bonds, tpsa),
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if results:
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
    else:
        output_path.write_text("", encoding="utf-8")

    summary = {
        "total": len(rows),
        "valid": len(results),
        "invalid": len(invalid),
        "lipinski_pass": sum(1 for row in results if row["lipinski_ok"]),
        "veber_pass": sum(1 for row in results if row["veber_ok"]),
        "invalid_rows": invalid,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"saved descriptors: {output_path}")
    print(f"saved summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
