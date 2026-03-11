#!/usr/bin/env python3
"""Inspect DICOM files, export metadata tables, and optionally write basic de-identified copies."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    import pydicom
    from pydicom.misc import is_dicom
    from pydicom.uid import generate_uid
except Exception:  # pragma: no cover - optional at runtime
    pydicom = None
    is_dicom = None
    generate_uid = None


DEIDENTIFY_TEXT_TAGS = [
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientBirthTime",
    "PatientSex",
    "PatientAddress",
    "OtherPatientIDs",
    "OtherPatientNames",
    "EthnicGroup",
    "InstitutionName",
    "InstitutionAddress",
    "ReferringPhysicianName",
    "PerformingPhysicianName",
    "OperatorsName",
    "AccessionNumber",
    "StudyID",
]
DEIDENTIFY_UID_TAGS = ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect DICOM metadata and optionally write de-identified copies")
    parser.add_argument("input", help="DICOM file or directory")
    parser.add_argument("--output", default="medical/dicom_metadata.csv")
    parser.add_argument("--summary", default="medical/dicom_summary.json")
    parser.add_argument("--recursive", action="store_true", help="Recurse into subdirectories")
    parser.add_argument("--max-files", type=int, default=0, help="Optional hard limit on scanned files")
    parser.add_argument("--deidentify-dir", help="Optional directory for basic de-identified copies")
    parser.add_argument("--retain-uids", action="store_true", help="Keep study/series/SOP instance UIDs")
    return parser.parse_args()


def require_pydicom() -> None:
    if pydicom is None or is_dicom is None:
        raise SystemExit("pydicom is required for dicom_inspect.py")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "; ".join(clean_text(item) for item in value if clean_text(item))
    return clean_text(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_rows(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["message"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: flatten_value(value) for key, value in row.items()})


def collect_candidate_files(root: Path, recursive: bool, max_files: int) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise SystemExit(f"Input path does not exist: {root}")
    iterator: Iterable[Path]
    iterator = root.rglob("*") if recursive else root.glob("*")
    files = [path for path in iterator if path.is_file()]
    files.sort()
    if max_files > 0:
        files = files[:max_files]
    return files


def is_dicom_file(path: Path) -> bool:
    if is_dicom is None:
        return False
    try:
        return bool(is_dicom(str(path)))
    except Exception:
        return False


def read_dataset(path: Path):
    return pydicom.dcmread(str(path), stop_before_pixels=True, force=True)


def dataset_row(path: Path, ds: Any) -> dict[str, Any]:
    pixel_spacing = getattr(ds, "PixelSpacing", []) or []
    orientation = getattr(ds, "ImageOrientationPatient", []) or []
    return {
        "file_path": str(path),
        "patient_id": clean_text(getattr(ds, "PatientID", "")),
        "patient_name": clean_text(getattr(ds, "PatientName", "")),
        "study_instance_uid": clean_text(getattr(ds, "StudyInstanceUID", "")),
        "series_instance_uid": clean_text(getattr(ds, "SeriesInstanceUID", "")),
        "sop_instance_uid": clean_text(getattr(ds, "SOPInstanceUID", "")),
        "modality": clean_text(getattr(ds, "Modality", "")),
        "study_description": clean_text(getattr(ds, "StudyDescription", "")),
        "series_description": clean_text(getattr(ds, "SeriesDescription", "")),
        "body_part_examined": clean_text(getattr(ds, "BodyPartExamined", "")),
        "manufacturer": clean_text(getattr(ds, "Manufacturer", "")),
        "institution_name": clean_text(getattr(ds, "InstitutionName", "")),
        "accession_number": clean_text(getattr(ds, "AccessionNumber", "")),
        "study_date": clean_text(getattr(ds, "StudyDate", "")),
        "series_date": clean_text(getattr(ds, "SeriesDate", "")),
        "content_date": clean_text(getattr(ds, "ContentDate", "")),
        "rows": clean_text(getattr(ds, "Rows", "")),
        "columns": clean_text(getattr(ds, "Columns", "")),
        "number_of_frames": clean_text(getattr(ds, "NumberOfFrames", "")),
        "slice_thickness": clean_text(getattr(ds, "SliceThickness", "")),
        "pixel_spacing": "; ".join(clean_text(value) for value in pixel_spacing if clean_text(value)),
        "image_orientation_patient": "; ".join(clean_text(value) for value in orientation if clean_text(value)),
    }


def deidentify_dataset(ds: Any, retain_uids: bool) -> Any:
    clone = copy.deepcopy(ds)
    for tag in DEIDENTIFY_TEXT_TAGS:
        if tag in clone:
            clone.data_element(tag).value = ""
    if not retain_uids:
        if generate_uid is None:
            raise SystemExit("pydicom.uid.generate_uid is required when --retain-uids is not set")
        for tag in DEIDENTIFY_UID_TAGS:
            if tag in clone:
                clone.data_element(tag).value = generate_uid()
    return clone


def write_deidentified_copy(input_path: Path, output_dir: Path, ds: Any, retain_uids: bool) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    clone = deidentify_dataset(ds, retain_uids)
    target = output_dir / input_path.name
    clone.save_as(str(target))
    return str(target)


def main() -> None:
    args = parse_args()
    require_pydicom()
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    deidentify_dir = Path(args.deidentify_dir) if args.deidentify_dir else None

    rows: list[dict[str, Any]] = []
    scanned_files = 0
    dicom_files = 0
    modality_counts: Counter[str] = Counter()
    studies: set[str] = set()
    series: set[str] = set()
    deidentified_paths: list[str] = []
    errors: list[dict[str, str]] = []

    for path in collect_candidate_files(input_path, args.recursive, args.max_files):
        scanned_files += 1
        if not is_dicom_file(path):
            continue
        try:
            ds = read_dataset(path)
            row = dataset_row(path, ds)
            rows.append(row)
            dicom_files += 1
            if row["modality"]:
                modality_counts[row["modality"]] += 1
            if row["study_instance_uid"]:
                studies.add(row["study_instance_uid"])
            if row["series_instance_uid"]:
                series.add(row["series_instance_uid"])
            if deidentify_dir is not None:
                deidentified_paths.append(write_deidentified_copy(path, deidentify_dir, ds, args.retain_uids))
        except Exception as exc:
            errors.append({"file_path": str(path), "error": str(exc)})

    write_rows(rows, output_path)
    summary = {
        "tool": "dicom_inspect",
        "input": str(input_path),
        "scanned_files": scanned_files,
        "dicom_files": dicom_files,
        "study_count": len(studies),
        "series_count": len(series),
        "modality_counts": dict(modality_counts),
        "deidentify_dir": str(deidentify_dir) if deidentify_dir is not None else "",
        "deidentified_file_count": len(deidentified_paths),
        "error_count": len(errors),
        "errors": errors[:50],
        "warning": "Basic de-identification removes common direct identifiers only and is not a validated anonymization workflow.",
        "output": str(output_path),
    }
    write_json(summary_path, summary)
    print(json.dumps({"output": str(output_path), "summary": str(summary_path), "result_count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
