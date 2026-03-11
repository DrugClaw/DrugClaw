#!/usr/bin/env python3
"""Fetch benchmark datasets from PyTDC and export flat tables."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


TASKS = {
    "adme": ("tdc.single_pred", "ADME"),
    "tox": ("tdc.single_pred", "Tox"),
    "hts": ("tdc.single_pred", "HTS"),
    "qm": ("tdc.single_pred", "QM"),
    "dti": ("tdc.multi_pred", "DTI"),
    "ddi": ("tdc.multi_pred", "DDI"),
    "ppi": ("tdc.multi_pred", "PPI"),
    "molgen": ("tdc.generation", "MolGen"),
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split-method", default="scaffold")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument("--valid-frac", type=float, default=0.1)
    parser.add_argument("--test-frac", type=float, default=0.2)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    module_name, class_name = TASKS[args.task]
    module = importlib.import_module(module_name)
    dataset_cls = getattr(module, class_name)
    dataset = dataset_cls(name=args.dataset)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    full_df = dataset.get_data(format="df")
    full_path = args.out_dir / "full.csv"
    full_df.to_csv(full_path, index=False)

    split_sizes: dict[str, int] = {}
    split_outputs: dict[str, str] = {}
    try:
        split = dataset.get_split(
            method=args.split_method,
            seed=args.seed,
            frac=[args.train_frac, args.valid_frac, args.test_frac],
        )
        for name, part in split.items():
            out_path = args.out_dir / f"{name}.csv"
            part.to_csv(out_path, index=False)
            split_sizes[name] = int(len(part))
            split_outputs[name] = str(out_path)
    except Exception as exc:  # pragma: no cover - split support differs by task
        split_sizes = {"error": 1}
        split_outputs = {"warning": str(exc)}

    summary = {
        "task": args.task,
        "dataset": args.dataset,
        "rows": int(len(full_df)),
        "columns": list(full_df.columns),
        "split_method": args.split_method,
        "split_sizes": split_sizes,
        "full_output": str(full_path),
        "split_outputs": split_outputs,
    }
    write_json(args.out_dir / "summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
