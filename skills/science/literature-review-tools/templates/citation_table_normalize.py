#!/usr/bin/env python3
"""Normalize and deduplicate tabular citation exports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise ValueError(f"unsupported input format: {path}")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_doi(value: Any) -> str:
    text = normalize_text(value).lower().replace("https://doi.org/", "").replace("doi:", "")
    match = DOI_PATTERN.search(text)
    return match.group(0).lower() if match else text


def title_fingerprint(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", normalize_text(value).lower())
    return re.sub(r"\s+", " ", text).strip()


def citation_key(authors: str, year: Any, title: str) -> str:
    first_author = normalize_text(authors).split(",")[0].split(";")[0].split()[:1]
    prefix = first_author[0].lower() if first_author else "unknown"
    title_words = [word for word in title_fingerprint(title).split() if len(word) > 2]
    anchor = title_words[0] if title_words else "study"
    year_text = re.sub(r"\D", "", str(year or "")) or "nd"
    return f"{prefix}{year_text}{anchor}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--title-column", required=True)
    parser.add_argument("--doi-column")
    parser.add_argument("--pmid-column")
    parser.add_argument("--year-column")
    parser.add_argument("--journal-column")
    parser.add_argument("--authors-column")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--bibtex-output", type=Path)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    df = read_table(args.input)
    if args.title_column not in df.columns:
        raise SystemExit(f"missing title column: {args.title_column}")

    work = df.copy()
    work["title"] = work[args.title_column].map(normalize_text)
    work["title_fingerprint"] = work["title"].map(title_fingerprint)
    work["doi"] = work[args.doi_column].map(normalize_doi) if args.doi_column and args.doi_column in work.columns else ""
    work["pmid"] = work[args.pmid_column].map(lambda x: re.sub(r"\D", "", str(x or ""))) if args.pmid_column and args.pmid_column in work.columns else ""
    work["year"] = work[args.year_column] if args.year_column and args.year_column in work.columns else ""
    work["journal"] = work[args.journal_column].map(normalize_text) if args.journal_column and args.journal_column in work.columns else ""
    work["authors"] = work[args.authors_column].map(normalize_text) if args.authors_column and args.authors_column in work.columns else ""
    work["citation_key"] = [citation_key(a, y, t) for a, y, t in zip(work["authors"], work["year"], work["title"])]

    dedupe_key = work["doi"].where(work["doi"] != "", work["title_fingerprint"])
    before = len(work)
    normalized = work.loc[~dedupe_key.duplicated()].copy()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(args.output, index=False)

    if args.bibtex_output:
        args.bibtex_output.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for row in normalized.to_dict(orient="records"):
            entry_type = "article"
            entries.append(
                "@{type}{{{key},\n  title = {{{title}}},\n  author = {{{authors}}},\n  journal = {{{journal}}},\n  year = {{{year}}},\n  doi = {{{doi}}},\n  pmid = {{{pmid}}}\n}}\n".format(
                    type=entry_type,
                    key=row["citation_key"],
                    title=row.get("title", ""),
                    authors=row.get("authors", ""),
                    journal=row.get("journal", ""),
                    year=row.get("year", ""),
                    doi=row.get("doi", ""),
                    pmid=row.get("pmid", ""),
                )
            )
        args.bibtex_output.write_text("\n".join(entries), encoding="utf-8")

    summary = {
        "input_path": str(args.input),
        "rows_before_dedup": int(before),
        "rows_after_dedup": int(len(normalized)),
        "duplicates_removed": int(before - len(normalized)),
        "doi_rows": int((normalized["doi"] != "").sum()),
        "pmid_rows": int((normalized["pmid"] != "").sum()),
        "output_path": str(args.output),
        "bibtex_output": str(args.bibtex_output) if args.bibtex_output else None,
    }
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
