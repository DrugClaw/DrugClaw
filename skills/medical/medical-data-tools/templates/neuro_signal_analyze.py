#!/usr/bin/env python3
"""Analyze physiological signals with NeuroKit2 and export summary features."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import neurokit2 as nk
except Exception:  # pragma: no cover - optional at runtime
    nk = None

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional at runtime
    pd = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze physiological signals from CSV/TSV tables")
    parser.add_argument("--input", required=True, help="Input CSV or TSV file")
    parser.add_argument("--signal-column", required=True, help="Numeric signal column")
    parser.add_argument("--sampling-rate", type=float, required=True, help="Sampling rate in Hz")
    parser.add_argument("--signal-type", required=True, choices=["ecg", "ppg", "eda", "rsp", "emg"], help="Signal modality")
    parser.add_argument("--id", help="Optional record id for reporting")
    parser.add_argument("--sep", choices=[",", "tab", "auto"], default="auto")
    parser.add_argument("--output", default="medical/signal_features.csv")
    parser.add_argument("--summary", default="medical/signal_summary.json")
    parser.add_argument("--signals-output", help="Optional processed time-series output CSV")
    return parser.parse_args()


def require_modules() -> None:
    if nk is None:
        raise SystemExit("neurokit2 is required for neuro_signal_analyze.py")
    if pd is None:
        raise SystemExit("pandas is required for neuro_signal_analyze.py")


def load_table(path: Path, sep: str):
    if sep == "tab":
        return pd.read_csv(path, sep="\t")
    if sep == ",":
        return pd.read_csv(path)
    return pd.read_csv(path, sep=None, engine="python")


def normalize_analysis(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        if getattr(result, "empty", False):
            return {}
        if hasattr(result, "iloc"):
            first_row = result.iloc[0]
            if hasattr(first_row, "to_dict"):
                return {str(k): v for k, v in first_row.to_dict().items()}
        as_dict = result.to_dict()
        return {str(k): v for k, v in as_dict.items()}
    if isinstance(result, dict):
        return result
    return {"result": str(result)}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    require_modules()
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    frame = load_table(input_path, args.sep)
    if args.signal_column not in frame.columns:
        raise SystemExit(f"Missing signal column: {args.signal_column}")
    signal = frame[args.signal_column].dropna().astype(float).tolist()
    if len(signal) < 10:
        raise SystemExit("Signal is too short for NeuroKit2 processing")

    process_fn = getattr(nk, f"{args.signal_type}_process")
    analyze_fn = getattr(nk, f"{args.signal_type}_analyze")
    processed, info = process_fn(signal, sampling_rate=args.sampling_rate)
    analysis = normalize_analysis(analyze_fn(processed, sampling_rate=args.sampling_rate))
    analysis.update(
        {
            "record_id": args.id or input_path.stem,
            "signal_type": args.signal_type,
            "sampling_rate_hz": args.sampling_rate,
            "n_samples": len(signal),
            "duration_seconds": len(signal) / args.sampling_rate,
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([analysis]).to_csv(output_path, index=False)
    if args.signals_output:
        signals_path = Path(args.signals_output)
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        processed.to_csv(signals_path, index=False)
    else:
        signals_path = None

    summary = {
        "tool": "neuro_signal_analyze",
        "input": str(input_path),
        "record_id": analysis["record_id"],
        "signal_type": args.signal_type,
        "sampling_rate_hz": args.sampling_rate,
        "n_samples": len(signal),
        "duration_seconds": len(signal) / args.sampling_rate,
        "output": str(output_path),
        "signals_output": str(signals_path) if signals_path is not None else "",
        "info_keys": sorted(info.keys()),
        "warning": "These outputs are research features and signal-quality summaries, not diagnostic conclusions.",
    }
    write_json(summary_path, summary)
    print(json.dumps({"output": str(output_path), "summary": str(summary_path), "result_count": 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
