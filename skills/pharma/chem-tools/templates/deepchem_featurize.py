#!/usr/bin/env python3
"""Featurize molecules with DeepChem for DrugClaw workflows."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

def load_smiles(args: argparse.Namespace) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if args.smiles:
        for index, smiles in enumerate(args.smiles, 1):
            rows.append((f"mol_{index}", smiles))
    if args.input:
        input_path = Path(args.input)
        suffix = input_path.suffix.lower()
        if suffix in {".csv", ".tsv"}:
            import pandas as pd

            sep = "\t" if suffix == ".tsv" else ","
            frame = pd.read_csv(input_path, sep=sep)
            smiles_col = args.smiles_column
            id_col = args.id_column
            for index, row in frame.iterrows():
                mol_id = str(row[id_col]) if id_col and id_col in frame.columns else f"row_{index + 1}"
                rows.append((mol_id, str(row[smiles_col])))
        else:
            with input_path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle, 1):
                    clean = line.strip()
                    if clean:
                        rows.append((f"line_{index}", clean))
    if not rows:
        raise SystemExit("No SMILES provided. Use --smiles or --input.")
    return rows


def make_featurizer(dc, name: str, size: int, radius: int):
    if name == "circular":
        return dc.feat.CircularFingerprint(size=size, radius=radius)
    if name == "maccs":
        return dc.feat.MACCSKeysFingerprint()
    if name == "mol2vec":
        return dc.feat.Mol2VecFingerprint()
    raise SystemExit(f"Unsupported featurizer: {name}")


def summarize_features(ids: Iterable[str], smiles: Iterable[str], features) -> list[dict[str, object]]:
    import numpy as np

    summary: list[dict[str, object]] = []
    for mol_id, mol_smiles, feat in zip(ids, smiles, features):
        arr = np.asarray(feat)
        summary.append(
            {
                "id": mol_id,
                "smiles": mol_smiles,
                "feature_dim": int(arr.shape[-1]) if arr.ndim else 1,
                "nonzero": int(np.count_nonzero(arr)),
                "mean": float(arr.mean()) if arr.size else 0.0,
                "std": float(arr.std()) if arr.size else 0.0,
            }
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Featurize molecules with DeepChem")
    parser.add_argument("--input", help="CSV/TSV/text input containing SMILES")
    parser.add_argument("--smiles", nargs="*", help="Inline SMILES strings")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--featurizer", default="circular", choices=["circular", "maccs", "mol2vec"])
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--output-prefix", default="deepchem_features")
    args = parser.parse_args()

    try:
        import deepchem as dc
        import numpy as np
    except Exception as exc:
        raise SystemExit(f"DeepChem runtime is unavailable: {exc}")

    rows = load_smiles(args)
    ids = [row[0] for row in rows]
    smiles = [row[1] for row in rows]

    featurizer = make_featurizer(dc, args.featurizer, args.size, args.radius)
    features = featurizer.featurize(smiles)
    features = np.asarray(features)

    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    np.save(prefix.with_suffix(".npy"), features)

    summary = summarize_features(ids, smiles, features)
    summary_path = prefix.with_suffix(".summary.csv")
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    metadata = {
        "featurizer": args.featurizer,
        "feature_shape": list(features.shape),
        "size": args.size,
        "radius": args.radius,
        "count": len(rows),
    }
    prefix.with_suffix(".json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"saved features: {prefix.with_suffix('.npy')}")
    print(f"saved summary: {summary_path}")
    print(f"saved metadata: {prefix.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
