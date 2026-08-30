"""Generate analytics JSON consumed by the website."""
from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd


def _records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for col in out.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        out[col] = out[col].dt.strftime("%Y-%m-%d")
    out = out.where(pd.notna(out), None)
    return out.to_dict(orient="records")


def build_analytics(
    ledger: pd.DataFrame,
    pharmacies: pd.DataFrame,
    supplier_identities: pd.DataFrame,
    unmatched_aliases: pd.DataFrame,
    ambiguous_aliases: pd.DataFrame,
    unmatched_erp: pd.DataFrame,
    identity_stats,
    revenue_stats,
    areas_unknown: pd.DataFrame,
    validation_report: dict,
) -> dict:
    ph = pharmacies.copy()
    if "canonical_name" in ledger.columns and "resolved_area" in ledger.columns:
        merged = ledger.copy()
    else:
        merged = ledger.merge(ph[["pharmacy_id", "canonical_name", "resolved_area"]], on="pharmacy_id", how="left")

    pharmacies_per_area = (
        ph.dropna(subset=["resolved_area"])
        .groupby("resolved_area", as_index=False)
        .agg(pharmacy_count=("pharmacy_id", "nunique"))
        .sort_values("pharmacy_count", ascending=False)
    )

    revenue_per_area = (
        merged.dropna(subset=["resolved_area"])
        .groupby("resolved_area", as_index=False)
        .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
        .sort_values("revenue_egp", ascending=False)
    )

    top_pharmacies = (
        merged.groupby(["pharmacy_id", "canonical_name", "resolved_area"], as_index=False)
        .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
        .sort_values("revenue_egp", ascending=False)
    )

    top_by_area = {}
    for area in ph["resolved_area"].dropna().unique():
        sub = top_pharmacies[top_pharmacies["resolved_area"] == area].head(20)
        top_by_area[area] = _records(sub)

    top_suppliers = (
        merged.groupby(["supplier_key", "supplier_name"], as_index=False)
        .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
        .sort_values("revenue_egp", ascending=False)
    )

    # Pharmacy drill-down payloads
    pharmacy_list = []
    alias_groups = supplier_identities.groupby("pharmacy_id")
    merged["month"] = merged["order_date"].dt.to_period("M").astype(str)
    revenue_ts = merged.groupby(["pharmacy_id", "month"], as_index=False)["revenue_egp"].sum()

    for _, row in ph.iterrows():
        pid = int(row["pharmacy_id"])
        aliases = alias_groups.get_group(pid) if pid in alias_groups.groups else pd.DataFrame()
        alias_records = (
            aliases[
                    ["account_name", "branch_id", "supplier_code", "parent_company", "branch_tag", "match_score", "match_method", "match_status", "match_evidence"]
            ].to_dict(orient="records")
            if len(aliases)
            else []
        )
        ts = revenue_ts[revenue_ts["pharmacy_id"] == pid].sort_values("month")
        pharm_rev = merged[merged["pharmacy_id"] == pid]
        pharmacy_list.append(
            {
                "pharmacy_id": pid,
                "canonical_name": row["canonical_name"],
                "registry_name": row.get("registry_name", row["canonical_name"]),
                "resolved_area": row["resolved_area"],
                "registry_area": row.get("registry_area"),
                "area_source": row.get("area_source"),
                "area_confidence": row.get("area_confidence"),
                "area_conflict": bool(row.get("area_conflict", False)),
                "area_evidence": row.get("vote_breakdown", {}),
                "area_evidence_count": int(row.get("evidence_count", 0) or 0),
                "conflicting_evidence_count": int(row.get("conflicting_area_count", 0) or 0),
                "master_pharmacy_id": pid,
                "total_revenue_egp": float(pharm_rev["revenue_egp"].sum()) if len(pharm_rev) else 0.0,
                "order_count": int(len(pharm_rev)),
                "aliases": alias_records,
            "revenue_by_month": _records(ts),
            }
        )

    return {
        "meta": {
            "date_start": str(merged["order_date"].min().date()) if len(merged) else None,
            "date_end": str(merged["order_date"].max().date()) if len(merged) else None,
            "total_revenue_egp": float(merged["revenue_egp"].sum()),
            "total_orders": int(len(merged)),
            "pharmacy_count": int(ph["pharmacy_id"].nunique()),
            "master_pharmacy_count": int(ph["pharmacy_id"].nunique()),
            "supplier_count": int(supplier_identities["parent_company"].nunique()),
            "areas": sorted(ph["resolved_area"].dropna().unique().tolist()),
        },
        "summary": {
            "identity_stats": asdict(identity_stats),
            "revenue_impacts": [asdict(i) for i in revenue_stats.impacts],
            "validation_ok": validation_report.get("ok", False),
            "unmatched_alias_count": int(len(unmatched_aliases)),
            "unmatched_erp_invoice_count": int(len(unmatched_erp)),
            "unmatched_erp_revenue_egp": float(unmatched_erp.get("total_after_discount", pd.Series(dtype=float)).sum())
            if "total_after_discount" in unmatched_erp.columns
            else float(identity_stats.erp_revenue_unmatched),
            "unknown_area_pharmacy_count": int((areas_unknown["area_confidence"] != "ambiguous").sum()),
            "ambiguous_alias_count": int(len(ambiguous_aliases)),
            "matched_erp_invoice_count": int(identity_stats.erp_invoices_matched),
            "ambiguous_erp_invoice_count": int(identity_stats.erp_invoices_ambiguous),
            "recovered_area_pharmacy_count": int(((ph["area_source"] == "invoice_evidence")).sum()),
            "area_conflict_pharmacy_count": int(ph["area_conflict"].fillna(False).sum()),
            "ambiguous_area_pharmacy_count": int((ph["area_confidence"] == "ambiguous").sum()),
        },
        "pharmacies_per_area": _records(pharmacies_per_area),
        "revenue_per_area": _records(revenue_per_area),
        "top_pharmacies": _records(top_pharmacies.head(50)),
        "top_pharmacies_by_area": top_by_area,
        "top_suppliers": _records(top_suppliers.head(50)),
        "pharmacies": pharmacy_list,
        "ledger": _records(
            merged[
                [
                    "source_system",
                    "source_doc_id",
                    "order_date",
                    "pharmacy_id",
                    "canonical_name",
                    "resolved_area",
                    "supplier_key",
                    "supplier_name",
                    "revenue_egp",
                ]
            ]
        ),
        "unmatched_aliases_sample": _records(unmatched_aliases.head(100)),
        "ambiguous_aliases_sample": _records(ambiguous_aliases.head(100)),
        "unmatched_erp_sample": _records(unmatched_erp.head(100)),
        "data_quality": {
            "matched_alias_pct": round(100.0 * len(supplier_identities) / max(len(supplier_identities) + len(ambiguous_aliases) + len(unmatched_aliases), 1), 2),
            "ambiguous_alias_pct": round(100.0 * len(ambiguous_aliases) / max(len(supplier_identities) + len(ambiguous_aliases) + len(unmatched_aliases), 1), 2),
            "unmatched_alias_pct": round(100.0 * len(unmatched_aliases) / max(len(supplier_identities) + len(ambiguous_aliases) + len(unmatched_aliases), 1), 2),
            "matched_erp_invoice_pct": round(100.0 * identity_stats.erp_invoices_matched / max(identity_stats.erp_invoices_total, 1), 2),
            "unmatched_erp_invoice_pct": round(100.0 * identity_stats.erp_invoices_unmatched / max(identity_stats.erp_invoices_total, 1), 2),
        },
    }


def filter_analytics(data: dict, date_start: str | None, date_end: str | None, area: str | None) -> dict:
    """Apply date/area filters deterministically (same logic as website)."""
    ledger = pd.DataFrame(data["ledger"])
    if ledger.empty:
        return data

    ledger["order_date"] = pd.to_datetime(ledger["order_date"])
    if date_start:
        ledger = ledger[ledger["order_date"] >= pd.Timestamp(date_start)]
    if date_end:
        # Date filters are calendar-date inclusive, including the whole end day.
        ledger = ledger[ledger["order_date"] < (pd.Timestamp(date_end) + pd.Timedelta(days=1))]
    if area:
        ledger = ledger[ledger["resolved_area"] == area]

    filtered = data.copy()
    ph = pd.DataFrame(data["pharmacies"])
    filtered["ledger"] = _records(ledger)

    filtered["meta"]["total_revenue_egp"] = float(ledger["revenue_egp"].sum())
    filtered["meta"]["total_orders"] = int(len(ledger))

    if area:
        ph = ph[ph["resolved_area"] == area]
    # The explorer is a canonical registry view. Date filters change financial
    # metrics, but must not hide a valid pharmacy merely because it had no
    # ledger activity in the selected period.
    filtered["meta"]["pharmacy_count"] = int(ph["pharmacy_id"].nunique())

    filtered["revenue_per_area"] = (
        ledger.groupby("resolved_area", as_index=False)
        .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
        .sort_values("revenue_egp", ascending=False)
        .to_dict(orient="records")
    )
    filtered["top_pharmacies"] = (
        ledger.groupby(["pharmacy_id", "canonical_name", "resolved_area"], as_index=False)
        .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
        .sort_values("revenue_egp", ascending=False)
        .head(50)
        .to_dict(orient="records")
    )
    filtered["top_pharmacies_by_area"] = {}
    for area_name in ledger["resolved_area"].dropna().unique():
        sub = (
            ledger[ledger["resolved_area"] == area_name]
            .groupby(["pharmacy_id", "canonical_name", "resolved_area"], as_index=False)
            .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
            .sort_values("revenue_egp", ascending=False)
            .head(20)
        )
        filtered["top_pharmacies_by_area"][area_name] = sub.to_dict(orient="records")
    filtered["top_suppliers"] = (
        ledger.groupby(["supplier_key", "supplier_name"], as_index=False)
        .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
        .sort_values("revenue_egp", ascending=False)
        .head(50)
        .to_dict(orient="records")
    )
    filtered["pharmacies_per_area"] = (
        ph.dropna(subset=["resolved_area"])
        .groupby("resolved_area", as_index=False)
        .agg(pharmacy_count=("pharmacy_id", "count"))
        .to_dict(orient="records")
    )
    return filtered
