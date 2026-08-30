"""Task 1 pipeline configuration."""
from pathlib import Path

TASK1_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = TASK1_ROOT / "dataset"
OUTPUT_DIR = TASK1_ROOT / "output"

DATE_START = "2024-09-01"
DATE_END = "2026-08-26"

# Identity resolution thresholds (deterministic)
ALIAS_PHARMACY_SCORE_THRESHOLD = 78.0
ERP_ALIAS_SCORE_THRESHOLD = 88.0

# Revenue inclusion rules (documented in README)
APP_INCLUDED_STATUSES = {"paid", "shipped"}
APP_EXCLUDED_STATUSES = {"canceled", "pending_hold"}

# ERP: include all invoices with detail lines unless total is null/zero
# record_state CLSD/NaN both treated as valid completed invoices (see README)

# Legacy: INV adds, CR subtracts (line_value sign)

OFFICIAL_AREAS = ["Smouha", "Nasr City", "Faisal", "Mohandessin"]

CSV_FILES = [
    "pharmacy_registry.csv",
    "areas_reference.csv",
    "supplier_branches.csv",
    "supplier_account_names.csv",
    "invoices_app.csv",
    "invoice_details_app.csv",
    "invoices_erp.csv",
    "invoice_details_erp.csv",
    "invoices_legacy.csv",
    "invoice_details_legacy.csv",
]
