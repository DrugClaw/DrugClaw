#!/usr/bin/env python3
"""Run a small single-point quantum chemistry job with PySCF."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_xyz(path: Path) -> str:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) >= 3 and lines[0].isdigit():
        lines = lines[2:]
    atoms = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            atoms.append(" ".join(parts[:4]))
    if not atoms:
        raise SystemExit(f"No atoms parsed from {path}")
    return "; ".join(atoms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a PySCF single-point calculation")
    parser.add_argument("--atom", help="Inline atom specification, e.g. 'O 0 0 0; H 0 0 0.96; H 0.92 0 -0.24'")
    parser.add_argument("--xyz", help="XYZ file path")
    parser.add_argument("--basis", default="sto-3g")
    parser.add_argument("--method", choices=["rhf", "uhf", "rks", "uks"], default="rhf")
    parser.add_argument("--xc", default="b3lyp")
    parser.add_argument("--charge", type=int, default=0)
    parser.add_argument("--spin", type=int, default=0)
    parser.add_argument("--output", default="pyscf_single_point.json")
    args = parser.parse_args()

    if not args.atom and not args.xyz:
        raise SystemExit("Provide --atom or --xyz")

    try:
        from pyscf import dft, gto, scf
    except Exception as exc:
        raise SystemExit(f"PySCF runtime is unavailable: {exc}")

    atom_spec = args.atom or parse_xyz(Path(args.xyz))
    mol = gto.M(atom=atom_spec, basis=args.basis, charge=args.charge, spin=args.spin, verbose=0)

    if args.method == "rhf":
        runner = scf.RHF(mol)
    elif args.method == "uhf":
        runner = scf.UHF(mol)
    elif args.method == "rks":
        runner = dft.RKS(mol)
        runner.xc = args.xc
    else:
        runner = dft.UKS(mol)
        runner.xc = args.xc

    energy = runner.kernel()
    result = {
        "method": args.method,
        "xc": args.xc if args.method in {"rks", "uks"} else None,
        "basis": args.basis,
        "charge": args.charge,
        "spin": args.spin,
        "converged": bool(runner.converged),
        "energy_hartree": float(energy),
        "n_atoms": int(mol.natm),
        "n_basis": int(mol.nao_nr()),
        "atom": atom_spec,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
