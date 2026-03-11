#!/usr/bin/env python3
"""Normalize PDBbind-like structure affinity datasets into DrugClaw tables."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd


PDBBIND_AFFINITY_PATTERNS = [
    re.compile(r"-log(?:Kd|Ki|IC50|EC50)?(?:/Ki|/Kd)?\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"(Kd|Ki|IC50|EC50)\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(fM|pM|nM|uM|μM|mM|M)", re.IGNORECASE),
]
UNIT_TO_MOLAR = {
    "fm": 1e-15,
    "pm": 1e-12,
    "nm": 1e-9,
    "um": 1e-6,
    "μm": 1e-6,
    "mm": 1e-3,
    "m": 1.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize PDBbind-style index files into DrugClaw structure datasets")
    parser.add_argument("--root", required=True, help="Dataset root containing PDBbind entry directories")
    parser.add_argument("--index", help="PDBbind index file or CSV/TSV table")
    parser.add_argument("--metadata", help="Optional CSV/TSV table with extra columns to merge by id")
    parser.add_argument("--source", default="auto", choices=["auto", "pdbbind", "generic"])
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--target-column", default="affinity")
    parser.add_argument("--target-name-column", default="target_name")
    parser.add_argument("--group-column", default="target_group")
    parser.add_argument("--protein-id-column", default="protein_id")
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--complex-path-column", default="complex_path")
    parser.add_argument("--receptor-path-column", default="receptor_path")
    parser.add_argument("--ligand-path-column", default="ligand_path")
    parser.add_argument("--convert-raw-to-pactivity", action="store_true", default=False)
    parser.add_argument("--skip-missing", action="store_true", default=False)
    parser.add_argument("--output", default="pdbbind_normalized.csv")
    parser.add_argument("--summary", default="pdbbind_normalized.json")
    return parser.parse_args()



def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()



def maybe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed):
        return None
    return parsed



def relative_or_absolute(path: Path, *, base_dir: Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = base_dir / value
    return value.resolve()



def detect_source(index_path: str | None, requested: str) -> str:
    if requested != "auto":
        return requested
    if not index_path:
        return "pdbbind"
    suffix = Path(index_path).suffix.lower()
    return "generic" if suffix in {".csv", ".tsv", ".json"} else "pdbbind"



def pactivity_from_raw(value: float, unit: str) -> float | None:
    factor = UNIT_TO_MOLAR.get(unit.lower())
    if factor is None or value <= 0:
        return None
    molar = value * factor
    return -math.log10(molar)



def parse_affinity_blob(text: str, *, convert_raw_to_pactivity: bool) -> dict[str, Any]:
    clean = clean_text(text)
    if not clean:
        return {"affinity": None, "affinity_kind": "", "affinity_unit": "", "raw_affinity": ""}
    match = PDBBIND_AFFINITY_PATTERNS[0].search(clean)
    if match:
        return {
            "affinity": round(float(match.group(1)), 6),
            "affinity_kind": "pactivity",
            "affinity_unit": "p",
            "raw_affinity": clean,
        }
    match = PDBBIND_AFFINITY_PATTERNS[1].search(clean)
    if match:
        kind = match.group(1)
        raw_value = float(match.group(2))
        unit = match.group(3)
        if convert_raw_to_pactivity:
            converted = pactivity_from_raw(raw_value, unit)
            if converted is not None:
                return {
                    "affinity": round(converted, 6),
                    "affinity_kind": f"p{kind}",
                    "affinity_unit": "p",
                    "raw_affinity": clean,
                }
        return {
            "affinity": raw_value,
            "affinity_kind": kind,
            "affinity_unit": unit,
            "raw_affinity": clean,
        }
    numeric = maybe_float(clean)
    if numeric is not None:
        return {
            "affinity": numeric,
            "affinity_kind": "target",
            "affinity_unit": "",
            "raw_affinity": clean,
        }
    return {"affinity": None, "affinity_kind": "", "affinity_unit": "", "raw_affinity": clean}



def parse_pdbbind_index(path: Path, *, convert_raw_to_pactivity: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            left, _, comment = stripped.partition("//")
            tokens = left.split()
            if len(tokens) < 4:
                continue
            pdb_id = tokens[0].strip()
            resolution = maybe_float(tokens[1])
            release_year = int(tokens[2]) if tokens[2].isdigit() else None
            affinity_blob = " ".join(tokens[3:])
            affinity_fields = parse_affinity_blob(affinity_blob, convert_raw_to_pactivity=convert_raw_to_pactivity)
            rows.append(
                {
                    "id": pdb_id,
                    "resolution": resolution,
                    "release_year": release_year,
                    "target_name": clean_text(comment),
                    **affinity_fields,
                }
            )
    if not rows:
        raise SystemExit(f"No usable entries parsed from {path}")
    return pd.DataFrame(rows)



def read_generic_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("rows") or payload.get("records") or []
        return pd.DataFrame(payload)
    return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")



def resolve_entry_dir(root: Path, pdb_id: str) -> Path:
    candidates = [root / pdb_id, root / pdb_id.lower(), root / pdb_id.upper()]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (root / pdb_id).resolve()



def find_first_existing(candidates: list[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None



def detect_paths(entry_dir: Path, entry_id: str) -> dict[str, Optional[Path]]:
    stem_candidates = [entry_id, entry_id.lower(), entry_id.upper()]
    complex_candidates: list[Path] = []
    receptor_candidates: list[Path] = []
    ligand_candidates: list[Path] = []
    for stem in stem_candidates:
        complex_candidates.extend(
            [
                entry_dir / f"{stem}_complex.pdb",
                entry_dir / f"{stem}_complex.pdbqt",
                entry_dir / f"{stem}.pdb",
                entry_dir / f"{stem}.pdbqt",
            ]
        )
        receptor_candidates.extend(
            [
                entry_dir / f"{stem}_protein.pdb",
                entry_dir / f"{stem}_receptor.pdb",
                entry_dir / f"{stem}_protein.pdbqt",
                entry_dir / f"{stem}_receptor.pdbqt",
                entry_dir / "protein.pdb",
                entry_dir / "receptor.pdb",
            ]
        )
        ligand_candidates.extend(
            [
                entry_dir / f"{stem}_ligand.sdf",
                entry_dir / f"{stem}_ligand.mol2",
                entry_dir / f"{stem}_ligand.pdb",
                entry_dir / f"{stem}_ligand.pdbqt",
                entry_dir / "ligand.sdf",
                entry_dir / "ligand.mol2",
                entry_dir / "ligand.pdb",
            ]
        )
    return {
        "complex_path": find_first_existing(complex_candidates),
        "receptor_path": find_first_existing(receptor_candidates),
        "ligand_path": find_first_existing(ligand_candidates),
    }



def merge_metadata(base: pd.DataFrame, metadata: pd.DataFrame, *, id_column: str) -> pd.DataFrame:
    if id_column not in metadata.columns:
        raise SystemExit(f"Metadata table is missing id column: {id_column}")
    return base.merge(metadata, on=id_column, how="left", suffixes=("", "_meta"))



def resolve_optional_path(value: Any, *, base_dir: Path) -> Optional[Path]:
    text = clean_text(value)
    if not text:
        return None
    return relative_or_absolute(Path(text), base_dir=base_dir)



def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Dataset root not found: {root}")
    source = detect_source(args.index, args.source)
    if source == "pdbbind":
        if not args.index:
            raise SystemExit("PDBbind mode requires --index")
        frame = parse_pdbbind_index(Path(args.index).expanduser().resolve(), convert_raw_to_pactivity=args.convert_raw_to_pactivity)
    else:
        if not args.index:
            raise SystemExit("Generic mode requires --index")
        frame = read_generic_table(Path(args.index).expanduser().resolve())

    metadata_base = Path(args.metadata).expanduser().resolve().parent if args.metadata else root
    if args.metadata:
        metadata = read_generic_table(Path(args.metadata).expanduser().resolve())
        frame = merge_metadata(frame, metadata, id_column=args.id_column)

    if args.id_column != "id" and "id" in frame.columns and args.id_column not in frame.columns:
        frame = frame.rename(columns={"id": args.id_column})
    if args.target_column != "affinity" and "affinity" in frame.columns and args.target_column not in frame.columns:
        frame = frame.rename(columns={"affinity": args.target_column})
    if args.target_name_column != "target_name" and "target_name" in frame.columns and args.target_name_column not in frame.columns:
        frame = frame.rename(columns={"target_name": args.target_name_column})

    if args.id_column not in frame.columns:
        raise SystemExit(f"Input is missing id column: {args.id_column}")

    normalized_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        entry_id = clean_text(row[args.id_column])
        if not entry_id:
            invalid_rows.append({"id": "", "reason": "missing_id"})
            continue
        entry_dir = resolve_entry_dir(root, entry_id)
        detected_paths = detect_paths(entry_dir, entry_id)
        complex_path = resolve_optional_path(row.get(args.complex_path_column), base_dir=metadata_base) or detected_paths["complex_path"]
        receptor_path = resolve_optional_path(row.get(args.receptor_path_column), base_dir=metadata_base) or detected_paths["receptor_path"]
        ligand_path = resolve_optional_path(row.get(args.ligand_path_column), base_dir=metadata_base) or detected_paths["ligand_path"]
        if not complex_path and not (receptor_path and ligand_path):
            invalid_rows.append({"id": entry_id, "reason": "missing_structure_paths", "entry_dir": str(entry_dir)})
            if not args.skip_missing:
                continue
        affinity_value = maybe_float(row.get(args.target_column))
        if affinity_value is None and clean_text(row.get(args.target_column)):
            parsed = parse_affinity_blob(clean_text(row.get(args.target_column)), convert_raw_to_pactivity=args.convert_raw_to_pactivity)
            affinity_value = maybe_float(parsed["affinity"])
        normalized_rows.append(
            {
                "id": entry_id,
                "complex_path": str(complex_path) if complex_path else "",
                "receptor_path": str(receptor_path) if receptor_path else "",
                "ligand_path": str(ligand_path) if ligand_path else "",
                "affinity": affinity_value,
                "affinity_kind": clean_text(row.get("affinity_kind")) or clean_text(row.get("measurement")) or clean_text(row.get("standard_type")),
                "affinity_unit": clean_text(row.get("affinity_unit")) or clean_text(row.get("standard_units")),
                "raw_affinity": clean_text(row.get("raw_affinity")) or clean_text(row.get(args.target_column)),
                "target_name": clean_text(row.get(args.target_name_column)),
                "target_group": clean_text(row.get(args.group_column)),
                "protein_id": clean_text(row.get(args.protein_id_column)),
                "smiles": clean_text(row.get(args.smiles_column)),
                "resolution": maybe_float(row.get("resolution")),
                "release_year": maybe_float(row.get("release_year")),
                "entry_dir": str(entry_dir) if entry_dir.exists() else "",
                "source": "pdbbind" if source == "pdbbind" else "generic",
            }
        )

    if not normalized_rows:
        raise SystemExit("No valid rows were normalized.")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(normalized_rows).to_csv(output, index=False)

    summary = {
        "source": source,
        "root": str(root),
        "rows": len(normalized_rows),
        "with_complex_path": int(sum(1 for row in normalized_rows if row["complex_path"])),
        "with_receptor_ligand_pair": int(sum(1 for row in normalized_rows if row["receptor_path"] and row["ligand_path"])),
        "with_affinity": int(sum(1 for row in normalized_rows if row["affinity"] is not None)),
        "with_smiles": int(sum(1 for row in normalized_rows if row["smiles"])),
        "invalid_rows": invalid_rows,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved dataset: {output}")
    print(f"saved summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
