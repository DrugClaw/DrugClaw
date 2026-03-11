#!/usr/bin/env python3
"""Run a lightweight, local ADMET heuristic screen for small molecules."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from chem_ml_utils import load_smiles_rows


def lipinski_ok(mw: float, logp: float, hbd: float, hba: float) -> bool:
    return mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10


def veber_ok(rot_bonds: float, tpsa: float) -> bool:
    return rot_bonds <= 10 and tpsa <= 140


def egan_ok(logp: float, tpsa: float) -> bool:
    return logp <= 5.88 and tpsa <= 131.6


def bbb_likely(logp: float, tpsa: float, hbd: float) -> bool:
    return 1.0 <= logp <= 4.5 and tpsa < 90 and hbd <= 2


def admet_penalty(desc: dict[str, float], tox_alert_count: int) -> tuple[float, list[str]]:
    penalties = 0.0
    notes: list[str] = []
    if desc["mol_wt"] > 500:
        penalties += 0.15
        notes.append("high_mw")
    if desc["logp"] > 5.0 or desc["logp"] < -0.5:
        penalties += 0.15
        notes.append("logp_out_of_range")
    if desc["tpsa"] > 140:
        penalties += 0.15
        notes.append("high_tpsa")
    if desc["rot_bonds"] > 10:
        penalties += 0.10
        notes.append("high_flexibility")
    if desc["hbd"] > 5 or desc["hba"] > 10:
        penalties += 0.10
        notes.append("lipinski_hbond_violation")
    if abs(desc["formal_charge"]) > 1:
        penalties += 0.10
        notes.append("formal_charge_risk")
    if tox_alert_count > 0:
        penalties += min(0.25, tox_alert_count * 0.08)
        notes.append("structural_alerts")
    return max(0.0, 1.0 - penalties), notes


def filter_alerts(mol) -> tuple[int, str]:
    try:
        from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
        catalog = FilterCatalog(params)
        matches = catalog.GetMatches(mol)
        labels = sorted({match.GetDescription() for match in matches})
        return len(labels), "; ".join(labels)
    except Exception:
        return 0, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen molecules with lightweight ADMET heuristics")
    parser.add_argument("--input", help="CSV/TSV/text input containing SMILES")
    parser.add_argument("--smiles", nargs="*", help="Inline SMILES strings")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--output", default="admet_screen.csv")
    parser.add_argument("--summary", default="admet_summary.json")
    args = parser.parse_args()

    try:
        from rdkit import Chem
        from chem_ml_utils import rdkit_descriptor_dict
    except Exception as exc:
        raise SystemExit(f"RDKit runtime is unavailable: {exc}")

    rows = load_smiles_rows(
        input_path=args.input,
        smiles=args.smiles,
        smiles_column=args.smiles_column,
        id_column=args.id_column,
    )
    results: list[dict[str, object]] = []
    invalid: list[dict[str, str]] = []
    for row in rows:
        mol = Chem.MolFromSmiles(row.smiles)
        if mol is None:
            invalid.append({"id": row.mol_id, "smiles": row.smiles})
            continue
        desc = rdkit_descriptor_dict(mol)
        alert_count, alert_labels = filter_alerts(mol)
        score, flags = admet_penalty(desc, alert_count)
        results.append(
            {
                "id": row.mol_id,
                "smiles": row.smiles,
                **desc,
                "lipinski_ok": lipinski_ok(desc["mol_wt"], desc["logp"], desc["hbd"], desc["hba"]),
                "veber_ok": veber_ok(desc["rot_bonds"], desc["tpsa"]),
                "egan_ok": egan_ok(desc["logp"], desc["tpsa"]),
                "bbb_likely": bbb_likely(desc["logp"], desc["tpsa"], desc["hbd"]),
                "tox_alert_count": alert_count,
                "tox_alerts": alert_labels,
                "admet_score": round(score, 4),
                "admet_flags": "; ".join(flags),
                "admet_bucket": "pass" if score >= 0.75 else "warn" if score >= 0.50 else "fail",
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
        "pass": sum(1 for row in results if row["admet_bucket"] == "pass"),
        "warn": sum(1 for row in results if row["admet_bucket"] == "warn"),
        "fail": sum(1 for row in results if row["admet_bucket"] == "fail"),
        "invalid_rows": invalid,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"saved ADMET table: {output_path}")
    print(f"saved summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
