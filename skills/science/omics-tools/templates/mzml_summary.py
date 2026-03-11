#!/usr/bin/env python3
"""Summarize an mzML experiment with pyOpenMS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    import pyopenms as ms

    exp = ms.MSExperiment()
    ms.MzMLFile().load(str(args.input), exp)

    level_counts: dict[int, int] = {}
    rt_values: list[float] = []
    peak_rows: list[dict[str, Any]] = []
    for idx, spec in enumerate(exp):
        level = int(spec.getMSLevel())
        level_counts[level] = level_counts.get(level, 0) + 1
        rt_values.append(float(spec.getRT()))
        mz, intensity = spec.get_peaks()
        peak_rows.append(
            {
                "spectrum_index": idx,
                "ms_level": level,
                "rt": float(spec.getRT()),
                "peak_count": int(len(mz)),
                "tic": float(sum(intensity)) if len(intensity) else 0.0,
            }
        )

    out_df = pd.DataFrame(peak_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    summary = {
        "input_path": str(args.input),
        "spectra": int(exp.getNrSpectra()),
        "chromatograms": int(exp.getNrChromatograms()),
        "ms_levels": {str(key): value for key, value in sorted(level_counts.items())},
        "rt_min": min(rt_values) if rt_values else None,
        "rt_max": max(rt_values) if rt_values else None,
        "output_path": str(args.output),
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
