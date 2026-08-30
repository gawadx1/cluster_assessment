"""Matching and revenue exploration."""
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

ds = Path(__file__).parent / "dataset"


def normalize_name(s):
    if pd.isna(s):
        return ""
    s = str(s).lower()
    s = re.sub(r"^(py/|ph/|ph |el-|el |p/|pharmacy\s*)", "", s)
    s = re.sub(
        r"\b(pharmacy|pharma|pharm|wh-\d+|branch\s*\d+|br\.?\s*\d+|6th zone|main road|station st\.?|mall|011|\(\d+\))\b",
        " ",
        s,
    )
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def token_jaccard(a, b):
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_pharmacy(alias_norm, registry, min_score=0.55):
    best_id, best_score = None, 0.0
    for _, row in registry.iterrows():
        seq = SequenceMatcher(None, alias_norm, row["name_norm"]).ratio()
        jac = token_jaccard(alias_norm, row["name_norm"])
        score = 0.6 * seq + 0.4 * jac
        if score > best_score:
            best_score = score
            best_id = row["id"]
    if best_score >= min_score:
        return best_id, best_score
    return None, best_score


registry = pd.read_csv(ds / "pharmacy_registry.csv", encoding="utf-8-sig")
aliases = pd.read_csv(ds / "supplier_account_names.csv", encoding="utf-8-sig")
erp = pd.read_csv(ds / "invoices_erp.csv", encoding="utf-8-sig")
app = pd.read_csv(ds / "invoices_app.csv", encoding="utf-8-sig")
leg = pd.read_csv(ds / "invoices_legacy.csv", encoding="utf-8-sig")
leg_det = pd.read_csv(ds / "invoice_details_legacy.csv", encoding="utf-8-sig")
erp_det = pd.read_csv(ds / "invoice_details_erp.csv", encoding="utf-8-sig")
areas = pd.read_csv(ds / "areas_reference.csv", encoding="utf-8-sig")

registry["name_norm"] = registry["name"].map(normalize_name)
aliases["name_norm"] = aliases["account_name"].map(normalize_name)

# ERP exact composite match rate
alias_keys = set(
    zip(
        aliases["account_name"].str.lower().str.strip(),
        aliases["branch_id"].astype(int),
    )
)
erp_keys = list(
    zip(
        erp["account_name"].str.lower().str.strip(),
        erp["branch_code"].astype(int),
    )
)
exact = sum(1 for k in erp_keys if k in alias_keys)
print(f"ERP exact (name, branch) match: {exact}/{len(erp)}")

# Match all aliases to pharmacies
results = []
for _, row in aliases.iterrows():
    pid, score = match_pharmacy(row["name_norm"], registry)
    results.append((row["alias_id"], pid, score))
match_df = pd.DataFrame(results, columns=["alias_id", "pharmacy_id", "score"])
print(f"Aliases matched to pharmacy (>={0.55}): {match_df['pharmacy_id'].notna().sum()}/{len(match_df)}")
print(f"Score distribution:\n{match_df['score'].describe()}")

print("\nAPP by status:")
print(app.groupby("order_status")["grand_total"].agg(["count", "sum"]))

print("\nERP by record_state:")
print(erp.groupby("record_state", dropna=False)["total_after_discount"].agg(["count", "sum"]))

inv_sum = leg_det.merge(leg[["doc_no", "doc_type"]], on="doc_no")
print("\nLEGACY line_value by doc_type:")
print(inv_sum.groupby("doc_type")["line_value"].agg(["count", "sum"]))

for area in areas["area"]:
    cnt = erp_det["ship_to_address"].str.contains(area, case=False, na=False).sum()
    print(f"ERP addresses mentioning {area}: {cnt}")
