"""Historical CSV data cleaner and exclusion logger.

MANDATORY RULES:
1. Original reference CSVs are NEVER modified (read-only).
2. Cleaned copies are saved to data/cleaned/.
3. Every excluded row is recorded with the exact rule that triggered it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
REF_DIR = ROOT_DIR / "reference"
OUT_DIR = ROOT_DIR / "data" / "cleaned"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILES = [
    "pzem_training_data_20261012_115213.csv",
    "home_app_training_bulb_only_20261012_123319.csv",
    "pzem_training_data_20261015_160424.csv",
]


def sha256_of_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def evaluate_row(row: dict[str, str]) -> tuple[bool, str | None]:
    """Applies strict electrical validation rules to a single CSV row."""
    try:
        v = float(row.get("voltage_V", 0.0))
        i = float(row.get("current_A", 0.0))
        p = float(row.get("active_power_W", 0.0))
        pf = float(row.get("power_factor_pzem", 0.0))
        f = float(row.get("frequency_Hz", 0.0))
    except (ValueError, TypeError) as e:
        return False, f"Non-numeric value in electrical columns: {e}"

    for val, name in [(v, "V"), (i, "I"), (p, "P"), (pf, "PF"), (f, "F")]:
        if not math.isfinite(val):
            return False, f"Non-finite {name}: {val}"

    if v < 0 or i < 0 or p < 0:
        return False, f"Negative measurement: V={v}, I={i}, P={p}"

    # Voltage checks
    if v > 0 and (v < 50.0 or v > 300.0):
        return False, f"Implausible voltage ({v} V outside 50-300V)"

    # Current checks
    if i > 50.0:
        return False, f"Implausible current ({i} A exceeds 50A limit)"

    # Power factor checks
    if pf < 0.0 or pf > 1.0:
        return False, f"Implausible power factor ({pf} outside [0.0, 1.0])"

    # Frequency checks
    if f > 0 and (f < 40.0 or f > 65.0):
        return False, f"Implausible frequency ({f} Hz outside 40-65Hz)"

    return True, None


def clean_file(filename: str) -> dict[str, object]:
    src_path = REF_DIR / filename
    dest_path = OUT_DIR / f"cleaned_{filename}"
    log_path = OUT_DIR / f"exclusions_{filename.replace('.csv', '.json')}"

    orig_hash = sha256_of_file(src_path)

    total_rows = 0
    retained_rows = []
    exclusions = []

    with open(src_path, mode="r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames or []

        for row_idx, row in enumerate(reader, start=1):
            total_rows += 1
            is_valid, reason = evaluate_row(row)
            if is_valid:
                retained_rows.append(row)
            else:
                exclusions.append({
                    "row_index": row_idx,
                    "logged_at": row.get("logged_at"),
                    "voltage_V": row.get("voltage_V"),
                    "current_A": row.get("current_A"),
                    "power_factor_pzem": row.get("power_factor_pzem"),
                    "reason": reason,
                })

    # Write cleaned CSV
    with open(dest_path, mode="w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(retained_rows)

    # Write exclusion log
    with open(log_path, mode="w", encoding="utf-8") as logfile:
        json.dump(
            {
                "original_filename": filename,
                "original_sha256": orig_hash,
                "total_rows": total_rows,
                "retained_count": len(retained_rows),
                "excluded_count": len(exclusions),
                "retained_percentage": round(len(retained_rows) / max(1, total_rows) * 100, 2),
                "exclusions": exclusions,
            },
            logfile,
            indent=2,
        )

    # Verify original has not been changed
    post_hash = sha256_of_file(src_path)
    assert orig_hash == post_hash, f"CRITICAL: {filename} was modified during cleaning!"

    return {
        "file": filename,
        "sha256": orig_hash,
        "total": total_rows,
        "retained": len(retained_rows),
        "excluded": len(exclusions),
        "retained_pct": round(len(retained_rows) / max(1, total_rows) * 100, 2),
    }


def main():
    print("=" * 60)
    print("HISTORICAL CSV CLEANING AND EXCLUSION REPORT")
    print("=" * 60)
    results = []
    for f in CSV_FILES:
        res = clean_file(f)
        results.append(res)
        print(f"File: {res['file']}")
        print(f"  SHA-256:  {res['sha256']}")
        print(f"  Total:    {res['total']} rows")
        print(f"  Retained: {res['retained']} rows ({res['retained_pct']}%)")
        print(f"  Excluded: {res['excluded']} rows")
        print("-" * 60)


if __name__ == "__main__":
    main()

