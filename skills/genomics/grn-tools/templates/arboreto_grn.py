#!/usr/bin/env python3
"""Infer gene regulatory networks with Arboreto."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer a gene regulatory network from an expression matrix")
    parser.add_argument("--input", required=True, help="CSV or TSV expression matrix with observations as rows and genes as columns")
    parser.add_argument("--sep", choices=[",", "tab"], help="Override input delimiter")
    parser.add_argument("--index-column", help="Optional sample id column to drop before modeling")
    parser.add_argument("--transpose", action="store_true", help="Transpose the input so genes become columns")
    parser.add_argument("--tf-file", help="Optional text file with one transcription factor per line")
    parser.add_argument("--algorithm", choices=["grnboost2", "genie3"], default="grnboost2")
    parser.add_argument("--seed", type=int, default=777)
    parser.add_argument("--workers", type=int, default=0, help="Local Dask workers. Use 0 to let Arboreto manage resources")
    parser.add_argument("--min-importance", type=float, default=0.0)
    parser.add_argument("--top-edges", type=int, default=0, help="Keep only the top N edges after ranking")
    parser.add_argument("--output", default="grn_network.tsv")
    parser.add_argument("--summary", default="grn_summary.json")
    return parser.parse_args()


def load_dependencies(use_cluster: bool) -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        import pandas as pd
        from arboreto.algo import genie3, grnboost2
        from arboreto.utils import load_tf_names
    except Exception as exc:
        raise SystemExit(f"arboreto_grn.py requires pandas and arboreto ({exc})")
    Client = None
    LocalCluster = None
    if use_cluster:
        try:
            from distributed import Client, LocalCluster
        except Exception as exc:
            raise SystemExit(f"workers > 0 requires distributed ({exc})")
    return pd, grnboost2, genie3, load_tf_names, Client, LocalCluster


def delimiter_from_args(path: Path, sep_arg: str | None) -> str:
    if sep_arg == "tab":
        return "\t"
    if sep_arg == ",":
        return ","
    if path.suffix.lower() in {".tsv", ".tab"}:
        return "\t"
    return ","


def read_tf_names(tf_file: str | None, load_tf_names: Any) -> tuple[Any, int]:
    if not tf_file:
        return "all", 0
    path = Path(tf_file)
    if not path.exists():
        raise SystemExit(f"TF file not found: {path}")
    tf_names = load_tf_names(str(path))
    return tf_names, len(tf_names)


def prepare_matrix(args: argparse.Namespace, pd: Any) -> tuple[Any, dict[str, Any]]:
    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"Expression matrix not found: {path}")
    delimiter = delimiter_from_args(path, args.sep)
    frame = pd.read_csv(path, sep=delimiter)
    if args.index_column:
        if args.index_column not in frame.columns:
            raise SystemExit(f"Index column not found: {args.index_column}")
        frame = frame.drop(columns=[args.index_column])
    if args.transpose:
        frame = frame.transpose().reset_index(drop=True)
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    dropped = int(numeric.isna().any(axis=0).sum())
    numeric = numeric.dropna(axis=1, how="any")
    if numeric.empty:
        raise SystemExit("No fully numeric gene columns remain after cleaning")
    if numeric.shape[0] < 2 or numeric.shape[1] < 2:
        raise SystemExit("Need at least two observations and two genes for GRN inference")
    return numeric, {
        "input": str(path),
        "rows": int(numeric.shape[0]),
        "genes": int(numeric.shape[1]),
        "dropped_non_numeric_columns": dropped,
        "transposed": bool(args.transpose),
    }


def filter_network(network: Any, args: argparse.Namespace) -> Any:
    filtered = network.copy()
    if args.min_importance > 0:
        filtered = filtered[filtered["importance"] >= args.min_importance]
    filtered = filtered.sort_values("importance", ascending=False)
    if args.top_edges > 0:
        filtered = filtered.head(args.top_edges)
    return filtered


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    use_cluster = args.workers > 0
    pd, grnboost2, genie3, load_tf_names, Client, LocalCluster = load_dependencies(use_cluster)
    matrix, matrix_summary = prepare_matrix(args, pd)
    tf_names, tf_count = read_tf_names(args.tf_file, load_tf_names)
    client = None
    cluster = None
    try:
        if use_cluster:
            cluster = LocalCluster(n_workers=args.workers, threads_per_worker=1, processes=True)
            client = Client(cluster)
        algo = grnboost2 if args.algorithm == "grnboost2" else genie3
        kwargs = {"expression_data": matrix, "tf_names": tf_names, "seed": args.seed}
        if client is not None:
            kwargs["client_or_address"] = client
        network = algo(**kwargs)
        filtered = filter_network(network, args)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        filtered.to_csv(output_path, sep="\t", index=False)
        summary = {
            "algorithm": args.algorithm,
            "seed": args.seed,
            "tf_count": tf_count,
            "output": str(output_path),
            "summary": args.summary,
            "raw_edge_count": int(len(network)),
            "filtered_edge_count": int(len(filtered)),
            "min_importance": args.min_importance,
            "top_edges": args.top_edges,
            "workers": args.workers,
            **matrix_summary,
        }
        if not filtered.empty:
            top = filtered.head(5).to_dict(orient="records")
            for row in top:
                for key, value in list(row.items()):
                    if hasattr(value, "item"):
                        row[key] = value.item()
            summary["top_edges_preview"] = top
        return summary
    finally:
        if client is not None:
            client.close()
        if cluster is not None:
            cluster.close()


def main() -> None:
    args = parse_args()
    summary = run(args)
    write_summary(Path(args.summary), summary)
    print(json.dumps({"output": args.output, "summary": args.summary, "result_count": summary["filtered_edge_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
