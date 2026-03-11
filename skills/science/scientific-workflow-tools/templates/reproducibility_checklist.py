#!/usr/bin/env python3
"""Generate a reproducibility checklist for common research profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CHECKLISTS = {
    "general": [
        "Research question and primary outcome are explicitly stated.",
        "Raw data location and access conditions are documented.",
        "Analysis code location and execution instructions are documented.",
        "Software versions and environment specification are recorded.",
        "All statistical tests and thresholds are listed.",
        "Known limitations and negative results are described.",
    ],
    "omics": [
        "Reference genome or database version is documented.",
        "Sample metadata and inclusion or exclusion criteria are saved.",
        "Count-matrix or processed-data provenance is documented.",
        "QC thresholds, normalization, and batch handling are stated.",
        "Differential analysis design formula and contrast are recorded.",
        "Repository accession or sharing plan is documented.",
    ],
    "ml": [
        "Training, validation, and test split logic is fixed and documented.",
        "Feature generation pipeline and versioned inputs are saved.",
        "Random seeds and hardware-sensitive settings are recorded.",
        "Evaluation metrics and calibration logic are defined.",
        "External test or benchmark set is separated from tuning data.",
        "Model checkpoints and inference environment are reproducible.",
    ],
    "clinical-research": [
        "Eligibility criteria and cohort definition are explicit.",
        "Outcome definitions and time windows are documented.",
        "Missing-data handling strategy is defined.",
        "Confounder adjustment or matching plan is recorded.",
        "Reporting guideline target is selected.",
        "Data governance and de-identification constraints are documented.",
    ],
}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(CHECKLISTS), default="general")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    items = CHECKLISTS[args.profile]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    markdown = [f"# Reproducibility Checklist: {args.profile}", ""]
    markdown.extend(f"- [ ] {item}" for item in items)
    args.output.write_text("\n".join(markdown) + "\n", encoding="utf-8")

    summary = {
        "profile": args.profile,
        "item_count": len(items),
        "output_path": str(args.output),
        "items": items,
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
