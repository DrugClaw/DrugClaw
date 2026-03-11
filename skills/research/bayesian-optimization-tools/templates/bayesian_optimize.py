#!/usr/bin/env python3
"""Suggest the next experiment or parameter settings with Gaussian-process Bayesian optimization."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import warnings
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suggest experiment settings with a Gaussian-process surrogate and acquisition search"
    )
    parser.add_argument("--input", help="CSV or TSV history table with numeric parameter columns and one objective column")
    parser.add_argument(
        "--history-json",
        help='Inline JSON array of records, for example \'[{"temp": 20, "ph": 7.1, "yield": 0.42}]\'',
    )
    parser.add_argument("--objective-column", required=True, help="Name of the objective column to optimize")
    parser.add_argument("--param-column", action="append", default=[], help="Parameter column to use. Repeat for multiple columns")
    parser.add_argument("--id-column", help="Optional row id column to ignore during modeling")
    parser.add_argument("--direction", choices=["maximize", "minimize"], default="maximize")
    parser.add_argument(
        "--bound",
        action="append",
        default=[],
        help="Parameter bounds in the form name:min:max. Repeat for each parameter",
    )
    parser.add_argument(
        "--bounds-json",
        help='JSON object of bounds, for example \'{"temp": [15, 80], "ph": [5.0, 9.0]}\'',
    )
    parser.add_argument("--acquisition", choices=["ucb", "ei"], default="ucb")
    parser.add_argument("--exploration-weight", type=float, default=1.0, help="UCB beta or EI xi term")
    parser.add_argument("--candidate-count", type=int, default=2048, help="Random candidates sampled inside the bounds")
    parser.add_argument("--suggestions", type=int, default=1, help="How many ranked suggestions to export")
    parser.add_argument("--seed", type=int, default=777)
    parser.add_argument("--output", default="bayesopt_suggestions.csv")
    parser.add_argument("--summary", default="bayesopt_summary.json")
    return parser.parse_args()


def require_ml() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import numpy as np
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
    except Exception as exc:
        raise SystemExit(f"bayesian_optimize.py requires numpy and scikit-learn ({exc})")
    return np, GaussianProcessRegressor, ConstantKernel, Matern, WhiteKernel


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_history(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.history_json:
        data = json.loads(args.history_json)
        if not isinstance(data, list):
            raise SystemExit("--history-json must decode to a JSON array")
        rows: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                raise SystemExit("--history-json must contain JSON objects")
            rows.append(item)
        return rows
    if not args.input:
        raise SystemExit("Provide --input or --history-json")
    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"History file not found: {path}")
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def infer_param_columns(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    if args.param_column:
        return args.param_column
    if not rows:
        raise SystemExit("History table is empty")
    excluded = {args.objective_column}
    if args.id_column:
        excluded.add(args.id_column)
    inferred: list[str] = []
    for key in rows[0].keys():
        if key in excluded:
            continue
        inferred.append(key)
    if not inferred:
        raise SystemExit("Could not infer parameter columns. Use --param-column explicitly")
    return inferred


def parse_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except Exception as exc:
        raise SystemExit(f"Field '{field}' must be numeric ({value!r}: {exc})")
    if not math.isfinite(number):
        raise SystemExit(f"Field '{field}' must be finite ({value!r})")
    return number


def parse_bounds(args: argparse.Namespace, param_columns: list[str], rows: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    bounds: dict[str, tuple[float, float]] = {}
    if args.bounds_json:
        data = json.loads(args.bounds_json)
        if not isinstance(data, dict):
            raise SystemExit("--bounds-json must decode to an object")
        for key, value in data.items():
            if not isinstance(value, list) or len(value) != 2:
                raise SystemExit(f"Bounds for '{key}' must be a two-item array")
            low = parse_float(value[0], f"{key} lower bound")
            high = parse_float(value[1], f"{key} upper bound")
            if low >= high:
                raise SystemExit(f"Bounds for '{key}' must satisfy low < high")
            bounds[key] = (low, high)
    for item in args.bound:
        parts = item.split(":", 2)
        if len(parts) != 3:
            raise SystemExit(f"Invalid --bound value: {item!r}")
        name = parts[0].strip()
        low = parse_float(parts[1], f"{name} lower bound")
        high = parse_float(parts[2], f"{name} upper bound")
        if low >= high:
            raise SystemExit(f"Bounds for '{name}' must satisfy low < high")
        bounds[name] = (low, high)
    missing = [name for name in param_columns if name not in bounds]
    if not missing:
        return bounds
    if not rows:
        raise SystemExit(f"Missing bounds for parameters: {', '.join(missing)}")
    for name in missing:
        values = [parse_float(row.get(name), name) for row in rows]
        observed_low = min(values)
        observed_high = max(values)
        if observed_low == observed_high:
            pad = 1.0 if observed_low == 0 else abs(observed_low) * 0.1
            bounds[name] = (observed_low - pad, observed_high + pad)
            continue
        span = observed_high - observed_low
        pad = span * 0.1
        bounds[name] = (observed_low - pad, observed_high + pad)
    return bounds


def matrix_from_history(rows: list[dict[str, Any]], param_columns: list[str], objective_column: str, np: Any) -> tuple[Any, Any]:
    x_rows: list[list[float]] = []
    y_rows: list[float] = []
    for row in rows:
        x_rows.append([parse_float(row.get(name), name) for name in param_columns])
        y_rows.append(parse_float(row.get(objective_column), objective_column))
    if not x_rows:
        raise SystemExit("No valid history rows found")
    return np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float)


def fit_gp(x: Any, y: Any, seed: int, GaussianProcessRegressor: Any, ConstantKernel: Any, Matern: Any, WhiteKernel: Any) -> Any:
    kernel = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=[1.0] * x.shape[1], nu=2.5) + WhiteKernel(noise_level=1e-5)
    model = GaussianProcessRegressor(kernel=kernel, alpha=1e-6, normalize_y=True, random_state=seed, n_restarts_optimizer=3)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(x, y)
    return model


def normal_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def acquisition_score(kind: str, mean: float, std: float, best: float, exploration: float) -> float:
    if kind == "ucb":
        return mean + exploration * std
    if std <= 0:
        return 0.0
    improvement = mean - best - exploration
    z = improvement / std
    return improvement * normal_cdf(z) + std * normal_pdf(z)


def random_candidates(bounds: dict[str, tuple[float, float]], count: int, seed: int, np: Any) -> Any:
    rng = random.Random(seed)
    names = list(bounds.keys())
    samples = []
    for _ in range(max(count, 1)):
        row = []
        for name in names:
            low, high = bounds[name]
            row.append(rng.uniform(low, high))
        samples.append(row)
    return np.asarray(samples, dtype=float)


def round_key(values: list[float]) -> tuple[float, ...]:
    return tuple(round(value, 10) for value in values)


def suggest_points(args: argparse.Namespace) -> dict[str, Any]:
    np, GaussianProcessRegressor, ConstantKernel, Matern, WhiteKernel = require_ml()
    rows = read_history(args)
    param_columns = infer_param_columns(rows, args)
    bounds = parse_bounds(args, param_columns, rows)
    x, y_original = matrix_from_history(rows, param_columns, args.objective_column, np)
    if args.direction == "maximize":
        y_model = y_original.copy()
    else:
        y_model = -1.0 * y_original
    model = fit_gp(x, y_model, args.seed, GaussianProcessRegressor, ConstantKernel, Matern, WhiteKernel)
    candidates = random_candidates(bounds, args.candidate_count, args.seed, np)
    means, stds = model.predict(candidates, return_std=True)
    observed_best = float(np.max(y_model))
    observed_keys = {round_key(list(row)) for row in x.tolist()}
    scored: list[dict[str, Any]] = []
    for idx, values in enumerate(candidates.tolist()):
        if round_key(values) in observed_keys:
            continue
        mean_model = float(means[idx])
        std = float(stds[idx])
        mean_original = mean_model if args.direction == "maximize" else -1.0 * mean_model
        score = acquisition_score(args.acquisition, mean_model, std, observed_best, args.exploration_weight)
        row = {name: values[pos] for pos, name in enumerate(param_columns)}
        row.update(
            {
                "rank": 0,
                "predicted_objective_mean": mean_original,
                "predicted_objective_std": std,
                "acquisition": args.acquisition,
                "acquisition_score": score,
                "direction": args.direction,
            }
        )
        scored.append(row)
    scored.sort(key=lambda item: item["acquisition_score"], reverse=True)
    for idx, row in enumerate(scored[: args.suggestions], start=1):
        row["rank"] = idx
    best_row_index = int(np.argmax(y_model))
    best_observed = {name: float(x[best_row_index, idx]) for idx, name in enumerate(param_columns)}
    best_observed[args.objective_column] = float(y_original[best_row_index])
    return {
        "rows": scored[: args.suggestions],
        "summary": {
            "objective_column": args.objective_column,
            "direction": args.direction,
            "param_columns": param_columns,
            "history_rows": int(x.shape[0]),
            "candidate_count": int(args.candidate_count),
            "suggestions": int(min(args.suggestions, len(scored))),
            "acquisition": args.acquisition,
            "exploration_weight": args.exploration_weight,
            "bounds": {name: [bounds[name][0], bounds[name][1]] for name in param_columns},
            "best_observed": best_observed,
            "output": args.output,
        },
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["rank"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    result = suggest_points(args)
    write_rows(Path(args.output), result["rows"])
    write_json(Path(args.summary), result["summary"])
    print(json.dumps({"output": args.output, "summary": args.summary, "result_count": len(result["rows"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
