"""Quick revenue and matching stats."""
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

ds = Path(__file__).parent / "dataset"
app = pd.read_csv(ds / "invoices_app.csv", encoding="utf-8-sig")
app_det = pd.read_csv(ds / "invoice_details_app.csv", encoding="utf-8-sig")
erp = pd.read_csv(ds / "invoices_erp.csv", encoding="utf-8-sig")
erp_det = pd.read_csv(ds / "invoice_details_erp.csv", encoding="utf-8-sig")
leg = pd.read_csv(ds / "invoices_legacy.csv", encoding="utf-8-sig")
leg_det = pd.read_csv(ds / "invoice_details_legacy.csv", encoding="utf-8-sig")

line_sums = app_det.groupby("invoice_id")["line_total"].sum()
app = app.copy()
app["line_sum"] = app["invoice_id"].map(line_sums)
for status in app["order_status"].unique():
    sub = app[app["order_status"] == status]
    print(f"APP {status}: count={len(sub)}, grand={sub['grand_total'].sum():,.0f}, lines={sub['line_sum'].sum():,.0f}")

print("\nAPP pending_hold paid_total null:", app[app["order_status"] == "pending_hold"]["paid_total"].isna().sum())

line_sums_e = erp_det.groupby("invoice_h_id")["line_total_after_disc"].sum()
erp = erp.copy()
erp["line_sum"] = erp["invoice_no"].map(line_sums_e)
for state in ["CLSD", None]:
    sub = erp[erp["record_state"].isna() if state is None else erp["record_state"] == state]
    label = "NaN" if state is None else state
    print(f"ERP {label}: count={len(sub)}, header={sub['total_after_discount'].sum():,.0f}, lines={sub['line_sum'].sum():,.0f}")

leg_sums = leg_det.groupby("doc_no")["line_value"].sum()
leg = leg.copy()
leg["line_sum"] = leg["doc_no"].map(leg_sums)
for dt in ["INV", "CR"]:
    sub = leg[leg["doc_type"] == dt]
    print(f"LEGACY {dt}: count={len(sub)}, lines={sub['line_sum'].sum():,.0f}")

aliases = pd.read_csv(ds / "supplier_account_names.csv", encoding="utf-8-sig")
branch_aliases = aliases[aliases["branch_id"] == 754]["account_name"].tolist()
print(f"\nFuzzy MISR SMOUHA @ 754: {process.extractOne('MISR SMOUHA', branch_aliases, scorer=fuzz.WRatio)}")
