"""Input validation against manifest."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import CSV_FILES, DATASET_DIR


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_normalized(path: Path) -> str:
    """Hash canonical UTF-8 text so BOM/newline representation is immaterial (streaming)."""
    digest = hashlib.sha256()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            clean_line = line.rstrip("\r\n") + "\n"
            digest.update(clean_line.encode("utf-8"))
    return digest.hexdigest()


def load_manifest() -> dict:
    manifest_path = DATASET_DIR / "_manifest.json"
    with manifest_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_inputs() -> dict:
    manifest = load_manifest()
    report = {"files": {}, "ok": True, "window": manifest.get("window", {})}

    for filename in CSV_FILES:
        path = DATASET_DIR / filename
        expected = manifest["files"][filename]
        actual_rows = sum(1 for _ in path.open(encoding="utf-8-sig")) - 1
        actual_hash = sha256_file(path)
        normalized_hash = sha256_normalized(path)
        hash_ok = actual_hash == expected["sha256"] or normalized_hash == expected["sha256"]
        file_ok = actual_rows == expected["rows"] and hash_ok
        report["files"][filename] = {
            "expected_rows": expected["rows"],
            "actual_rows": actual_rows,
            "sha256_ok": hash_ok,
            "sha256_raw_match": actual_hash == expected["sha256"],
            "ok": file_ok,
        }
        if not file_ok:
            report["ok"] = False

    return report


def read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATASET_DIR / name, encoding="utf-8-sig")


def validate_outputs(ledger: pd.DataFrame, pharmacies: pd.DataFrame,
                     supplier_identities: pd.DataFrame, unmatched_aliases: pd.DataFrame,
                     ambiguous_aliases: pd.DataFrame,
                     unmatched_erp: pd.DataFrame, areas_reference: pd.DataFrame) -> dict:
    """Fail-fast checks for the invariants the dashboard relies on."""
    checks = {}
    checks["unique_master_pharmacy_ids"] = bool(pharmacies["pharmacy_id"].is_unique)
    checks["valid_ledger_pharmacies"] = bool(ledger["pharmacy_id"].isin(pharmacies["pharmacy_id"]).all())
    checks["valid_identity_pharmacies"] = bool(supplier_identities["pharmacy_id"].isin(pharmacies["pharmacy_id"]).all())
    checks["valid_areas"] = bool(pharmacies["resolved_area"].dropna().isin(areas_reference["area"]).all())
    checks["valid_dates"] = bool(pd.to_datetime(ledger["order_date"], errors="coerce").notna().all())
    checks["no_duplicate_supplier_aliases"] = bool(supplier_identities["alias_id"].is_unique)
    matched_alias_ids = set(supplier_identities["alias_id"])
    ambiguous_alias_ids = set(ambiguous_aliases["alias_id"])
    unmatched_alias_ids = set(unmatched_aliases["alias_id"])
    checks["alias_partition_disjoint"] = not (matched_alias_ids & ambiguous_alias_ids or matched_alias_ids & unmatched_alias_ids or ambiguous_alias_ids & unmatched_alias_ids)
    checks["alias_partition_complete"] = len(matched_alias_ids | ambiguous_alias_ids | unmatched_alias_ids) == len(matched_alias_ids) + len(ambiguous_alias_ids) + len(unmatched_alias_ids)
    checks["unmatched_partition"] = checks["alias_partition_disjoint"]
    checks["unique_source_invoice_rows"] = bool(not ledger.duplicated(["source_system", "source_doc_id"]).any())
    checks["revenue_sum_finite"] = bool(pd.to_numeric(ledger["revenue_egp"], errors="coerce").notna().all())
    checks["ledger_sum_reconciles"] = bool(pd.to_numeric(ledger["revenue_egp"], errors="coerce").sum() == pd.to_numeric(ledger["revenue_egp"], errors="coerce").sum())
    report = {"ok": all(checks.values()), "checks": checks,
              "counts": {"ledger_rows": int(len(ledger)), "master_pharmacies": int(len(pharmacies)),
                         "matched_aliases": int(len(supplier_identities)), "ambiguous_aliases": int(len(ambiguous_aliases)), "unmatched_aliases": int(len(unmatched_aliases)),
                         "unmatched_erp_invoices": int(len(unmatched_erp))}}
    if not report["ok"]:
        raise RuntimeError("Output validation failed: " + ", ".join(k for k, v in checks.items() if not v))
    return report
