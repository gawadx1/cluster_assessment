"""Revenue reconciliation across APP, ERP, and Legacy systems."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import APP_EXCLUDED_STATUSES, APP_INCLUDED_STATUSES, DATE_END, DATE_START


@dataclass
class RevenueRuleImpact:
    rule_id: str
    description: str
    rows_affected: int
    monetary_impact_egp: float


@dataclass
class RevenueStats:
    impacts: list[RevenueRuleImpact] = field(default_factory=list)
    ledger_rows: int = 0
    total_revenue_egp: float = 0.0


def _parse_app_date(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace("T", " ", regex=False).str.replace("Z", "", regex=False)
    return pd.to_datetime(cleaned, errors="coerce", utc=True).dt.tz_convert(None)


def _parse_erp_date(df: pd.DataFrame) -> pd.Series:
    d1 = pd.to_datetime(df["entry_date"], format="%d%m%Y", errors="coerce")
    d2 = pd.to_datetime(df["entry_date"], format="%d-%b-%Y", errors="coerce")
    return d1.fillna(d2)


def _parse_legacy_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")


def _in_window(dates: pd.Series) -> pd.Series:
    start = pd.Timestamp(DATE_START)
    end = pd.Timestamp(DATE_END)
    return (dates >= start) & (dates <= end)


def build_revenue_ledger(
    app_invoices: pd.DataFrame,
    app_details: pd.DataFrame,
    erp_invoices: pd.DataFrame,
    erp_details: pd.DataFrame,
    erp_links: pd.DataFrame,
    legacy_invoices: pd.DataFrame,
    legacy_details: pd.DataFrame,
    branches: pd.DataFrame,
) -> tuple[pd.DataFrame, RevenueStats]:
    stats = RevenueStats()
    ledger_parts = []

    # --- APP ---
    app = app_invoices.copy()
    app["order_date"] = _parse_app_date(app["placed_at_utc"])
    app_line = app_details.groupby("invoice_id", as_index=False)["line_total"].sum()
    app = app.merge(app_line, on="invoice_id", how="left")
    app["revenue_egp"] = app["line_total"].fillna(app["grand_total"])

    excluded = app[app["order_status"].isin(APP_EXCLUDED_STATUSES)]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="APP-01",
            description=f"Exclude order_status in {sorted(APP_EXCLUDED_STATUSES)}",
            rows_affected=len(excluded),
            monetary_impact_egp=float(excluded["revenue_egp"].sum()),
        )
    )
    app = app[app["order_status"].isin(APP_INCLUDED_STATUSES)]

    out_of_window = app[~_in_window(app["order_date"])]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="APP-02",
            description=f"Exclude orders outside {DATE_START}..{DATE_END}",
            rows_affected=len(out_of_window),
            monetary_impact_egp=float(out_of_window["revenue_egp"].sum()),
        )
    )
    app = app[_in_window(app["order_date"])]

    null_rev = app[app["revenue_egp"].isna() | (app["revenue_egp"] <= 0)]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="APP-03",
            description="Exclude zero/null revenue APP orders",
            rows_affected=len(null_rev),
            monetary_impact_egp=float(null_rev["revenue_egp"].fillna(0).sum()),
        )
    )
    app = app[app["revenue_egp"].notna() & (app["revenue_egp"] > 0)]

    app_ledger = app[["invoice_id", "order_date", "customer_id", "revenue_egp", "order_status"]].copy()
    app_ledger = app_ledger.rename(columns={"invoice_id": "source_doc_id", "customer_id": "pharmacy_id"})
    app_ledger["source_system"] = "APP"
    app_ledger["supplier_key"] = "APP"
    app_ledger["supplier_name"] = "Mobile App"
    ledger_parts.append(app_ledger)

    # --- ERP ---
    erp = erp_invoices.merge(
        erp_links[["invoice_no", "pharmacy_id", "supplier_code", "alias_id"]],
        on="invoice_no",
        how="left",
    )
    erp["order_date"] = _parse_erp_date(erp)
    erp_line = erp_details.groupby("invoice_h_id", as_index=False)["line_total_after_disc"].sum()
    erp = erp.merge(erp_line, left_on="invoice_no", right_on="invoice_h_id", how="left")
    erp["revenue_egp"] = erp["line_total_after_disc"].fillna(erp["total_after_discount"])

    unmatched = erp[erp["pharmacy_id"].isna()]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="ERP-01",
            description="Exclude ERP invoices without matched pharmacy identity",
            rows_affected=len(unmatched),
            monetary_impact_egp=float(unmatched["revenue_egp"].fillna(0).sum()),
        )
    )
    erp = erp[erp["pharmacy_id"].notna()]

    out_of_window_e = erp[~_in_window(erp["order_date"])]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="ERP-02",
            description=f"Exclude ERP orders outside {DATE_START}..{DATE_END}",
            rows_affected=len(out_of_window_e),
            monetary_impact_egp=float(out_of_window_e["revenue_egp"].sum()),
        )
    )
    erp = erp[_in_window(erp["order_date"])]

    null_rev_e = erp[erp["revenue_egp"].isna() | (erp["revenue_egp"] <= 0)]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="ERP-03",
            description="Exclude zero/null revenue ERP orders",
            rows_affected=len(null_rev_e),
            monetary_impact_egp=float(null_rev_e["revenue_egp"].fillna(0).sum()),
        )
    )
    erp = erp[erp["revenue_egp"].notna() & (erp["revenue_egp"] > 0)]

    branch_supplier = branches.set_index("branch_id")["parent_company"].to_dict()
    erp["supplier_name"] = erp["branch_code"].map(branch_supplier)
    erp["supplier_key"] = erp["supplier_code"].astype(str)

    erp_ledger = erp[
        ["invoice_no", "order_date", "pharmacy_id", "revenue_egp", "supplier_key", "supplier_name", "branch_code"]
    ].copy()
    erp_ledger = erp_ledger.rename(columns={"invoice_no": "source_doc_id", "branch_code": "branch_id"})
    erp_ledger["pharmacy_id"] = erp_ledger["pharmacy_id"].astype(int)
    erp_ledger["source_system"] = "ERP"
    ledger_parts.append(erp_ledger)

    # --- LEGACY ---
    leg = legacy_invoices.copy()
    leg["pharmacy_id"] = pd.to_numeric(
        leg["account_ref"].str.extract(r"P:(\d+)", expand=False), errors="coerce"
    ).astype("Int64")
    leg["order_date"] = _parse_legacy_date(leg["doc_date"])
    leg_line = legacy_details.groupby("doc_no", as_index=False)["line_value"].sum()
    leg = leg.merge(leg_line, on="doc_no", how="left")
    leg["revenue_egp"] = leg["line_value"]

    # Credits (CR) already have negative line_value — included in sum
    credits = leg[leg["doc_type"] == "CR"]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="LEG-01",
            description="Credit documents (CR) reduce revenue via negative line_value",
            rows_affected=len(credits),
            monetary_impact_egp=float(credits["revenue_egp"].sum()),
        )
    )

    no_pharmacy = leg[leg["pharmacy_id"].isna()]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="LEG-02",
            description="Exclude legacy docs without parseable P:pharmacy_id",
            rows_affected=len(no_pharmacy),
            monetary_impact_egp=float(no_pharmacy["revenue_egp"].fillna(0).sum()),
        )
    )
    leg = leg[leg["pharmacy_id"].notna()]

    out_of_window_l = leg[~_in_window(leg["order_date"])]
    stats.impacts.append(
        RevenueRuleImpact(
            rule_id="LEG-03",
            description=f"Exclude legacy docs outside {DATE_START}..{DATE_END}",
            rows_affected=len(out_of_window_l),
            monetary_impact_egp=float(out_of_window_l["revenue_egp"].sum()),
        )
    )
    leg = leg[_in_window(leg["order_date"])]

    leg = leg[leg["revenue_egp"].notna() & (leg["revenue_egp"] != 0)]

    leg_ledger = leg[["doc_no", "order_date", "pharmacy_id", "revenue_egp", "doc_type"]].copy()
    leg_ledger = leg_ledger.rename(columns={"doc_no": "source_doc_id"})
    leg_ledger["pharmacy_id"] = leg_ledger["pharmacy_id"].astype(int)
    leg_ledger["source_system"] = "LEGACY"
    leg_ledger["supplier_key"] = "LEGACY"
    leg_ledger["supplier_name"] = "Legacy System"
    ledger_parts.append(leg_ledger)

    ledger = pd.concat(ledger_parts, ignore_index=True)
    ledger["order_date"] = pd.to_datetime(ledger["order_date"])
    stats.ledger_rows = len(ledger)
    stats.total_revenue_egp = float(ledger["revenue_egp"].sum())
    return ledger, stats
