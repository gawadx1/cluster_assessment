"""Temporary data exploration script."""
import json
from pathlib import Path

import pandas as pd

ds = Path(__file__).parent / "dataset"

files = {
    "registry": pd.read_csv(ds / "pharmacy_registry.csv", encoding="utf-8-sig"),
    "areas": pd.read_csv(ds / "areas_reference.csv", encoding="utf-8-sig"),
    "branches": pd.read_csv(ds / "supplier_branches.csv", encoding="utf-8-sig"),
    "aliases": pd.read_csv(ds / "supplier_account_names.csv", encoding="utf-8-sig"),
    "app_inv": pd.read_csv(ds / "invoices_app.csv", encoding="utf-8-sig"),
    "app_det": pd.read_csv(ds / "invoice_details_app.csv", encoding="utf-8-sig"),
    "erp_inv": pd.read_csv(ds / "invoices_erp.csv", encoding="utf-8-sig"),
    "erp_det": pd.read_csv(ds / "invoice_details_erp.csv", encoding="utf-8-sig"),
    "leg_inv": pd.read_csv(ds / "invoices_legacy.csv", encoding="utf-8-sig"),
    "leg_det": pd.read_csv(ds / "invoice_details_legacy.csv", encoding="utf-8-sig"),
}

manifest = json.load(open(ds / "_manifest.json", encoding="utf-8"))
print("=== ROW COUNTS vs MANIFEST ===")
key_map = {
    "pharmacy_registry.csv": "registry",
    "areas_reference.csv": "areas",
    "supplier_branches.csv": "branches",
    "supplier_account_names.csv": "aliases",
    "invoices_app.csv": "app_inv",
    "invoice_details_app.csv": "app_det",
    "invoices_erp.csv": "erp_inv",
    "invoice_details_erp.csv": "erp_det",
    "invoices_legacy.csv": "leg_inv",
    "invoice_details_legacy.csv": "leg_det",
}
for k, v in manifest["files"].items():
    if k in key_map:
        actual = len(files[key_map[k]])
        print(f"{k}: manifest={v['rows']}, actual={actual}, match={actual == v['rows']}")

r = files["registry"]
print("\n=== REGISTRY AREA MISSING ===")
print(f"Total pharmacies: {len(r)}")
missing_area = r["area"].isna() | (r["area"].astype(str).str.strip() == "")
print(f"Missing area: {missing_area.sum()}")
print(r["area"].value_counts(dropna=False))

app = files["app_inv"]
reg_ids = set(r["id"])
print("\n=== APP ===")
print(app["order_status"].value_counts())
app_cust = set(app["customer_id"].dropna().astype(int))
print(f"Customers in registry: {len(app_cust & reg_ids)}/{len(app_cust)}")

leg = files["leg_inv"]
print("\n=== LEGACY ===")
print(leg["doc_type"].value_counts())
leg["pharmacy_id"] = leg["account_ref"].str.extract(r"P:(\d+)").astype(float)
print(f"Rows with valid P:id: {leg['pharmacy_id'].notna().sum()}")

erp = files["erp_inv"]
aliases = files["aliases"]
alias_lookup = {n.lower().strip(): n for n in aliases["account_name"]}
erp_names = erp["account_name"].dropna().unique()
matched = sum(1 for n in erp_names if str(n).lower().strip() in alias_lookup)
print(f"\n=== ERP ===")
print(f"ERP names exact in aliases: {matched}/{len(erp_names)}")
print(erp["record_state"].value_counts(dropna=False))

# Line total reconciliation APP
app_det = files["app_det"]
merged = app_det.groupby("invoice_id")["line_total"].sum().reset_index()
app_m = app.merge(merged, on="invoice_id", how="left")
app_m["diff"] = app_m["grand_total"] - app_m["line_total"]
print("\n=== APP grand_total vs line sum ===")
print(app_m["diff"].abs().describe())
print(f"Within 0.01: {(app_m['diff'].abs() <= 0.01).sum()}/{len(app_m)}")

# ERP reconciliation
erp_det = files["erp_det"]
erp_sum = erp_det.groupby("invoice_h_id")["line_total_after_disc"].sum().reset_index()
erp_m = erp.merge(erp_sum, left_on="invoice_no", right_on="invoice_h_id", how="left")
erp_m["diff"] = erp_m["total_after_discount"] - erp_m["line_total_after_disc"]
print("\n=== ERP total_after_discount vs line sum ===")
print(erp_m["diff"].abs().describe())
print(f"Within 0.01: {(erp_m['diff'].abs() <= 0.01).sum()}/{len(erp_m)}")

# Legacy reconciliation
leg_det = files["leg_det"]
leg_sum = leg_det.groupby("doc_no")["line_value"].sum().reset_index()
leg_m = leg.merge(leg_sum, on="doc_no", how="left")
print("\n=== LEGACY line counts ===")
print(f"Header line_count sum vs detail rows: {leg['line_count'].sum()} vs {len(leg_det)}")

# Credit docs
credits = leg[leg["doc_type"] == "CR"]
print(f"\nCredit docs: {len(credits)}")
print(credits.head())

# supplier_code meaning
print("\n=== Aliases per supplier_code ===")
print(aliases.groupby("supplier_code")["alias_id"].count())

# Check if same account_name appears with different branch_ids
dup_names = aliases.groupby("account_name")["branch_id"].nunique()
multi = dup_names[dup_names > 1]
print(f"\nAccount names with multiple branches: {len(multi)}")

# Sample delivery addresses for area recovery
print("\n=== Sample ship_to_address ===")
print(erp_det["ship_to_address"].dropna().head(10).tolist())
