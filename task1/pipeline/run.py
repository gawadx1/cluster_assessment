"""Pipeline orchestrator."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .analytics import build_analytics
from .areas import recover_areas
from .config import OUTPUT_DIR
from .identity import resolve_identities
from .revenue import build_revenue_ledger
from .validate import read_csv, validate_inputs, validate_outputs


def run_pipeline() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    validation = validate_inputs()
    with (OUTPUT_DIR / "validation_report.json").open("w", encoding="utf-8") as handle:
        json.dump(validation, handle, indent=2)

    if not validation["ok"]:
        # Row counts are required; hash mismatch is reported but does not abort.
        row_ok = all(v["actual_rows"] == v["expected_rows"] for v in validation["files"].values())
        if not row_ok:
            raise RuntimeError("Input CSV row counts do not match _manifest.json")

    registry = read_csv("pharmacy_registry.csv")
    branches = read_csv("supplier_branches.csv")
    aliases = read_csv("supplier_account_names.csv")
    areas_ref = read_csv("areas_reference.csv")
    app_inv = read_csv("invoices_app.csv")
    erp_inv = read_csv("invoices_erp.csv")
    leg_inv = read_csv("invoices_legacy.csv")

    official_areas = areas_ref["area"].tolist()

    canonical, supplier_identities, unmatched_aliases, ambiguous_aliases, unmatched_erp, erp_links, identity_stats = resolve_identities(
        registry, branches, aliases, erp_inv, app_inv, leg_inv, official_areas
    )

    erp_with_pharmacy = erp_inv.merge(
        erp_links[["invoice_no", "pharmacy_id", "alias_id", "supplier_code", "match_method"]],
        on="invoice_no",
        how="left",
    )
    erp_det = read_csv("invoice_details_erp.csv")
    erp_det_with_ph = erp_det.merge(
        erp_links[["invoice_no", "pharmacy_id"]],
        left_on="invoice_h_id",
        right_on="invoice_no",
        how="left",
    )

    areas_df, areas_unknown = recover_areas(registry, erp_with_pharmacy, erp_det_with_ph, official_areas)

    pharmacies = canonical.merge(areas_df, on="pharmacy_id", how="left")

    app_det = read_csv("invoice_details_app.csv")
    leg_det = read_csv("invoice_details_legacy.csv")
    ledger, revenue_stats = build_revenue_ledger(
        app_inv, app_det, erp_inv, erp_det, erp_links, leg_inv, leg_det, branches
    )
    ledger = ledger.merge(pharmacies[["pharmacy_id", "canonical_name", "resolved_area"]], on="pharmacy_id", how="left")

    output_validation = validate_outputs(
        ledger, pharmacies, supplier_identities, unmatched_aliases, ambiguous_aliases, unmatched_erp, areas_ref
    )

    validation["output_validation"] = output_validation
    with (OUTPUT_DIR / "validation_report.json").open("w", encoding="utf-8") as handle:
        json.dump(validation, handle, indent=2)

    pharmacies.to_csv(OUTPUT_DIR / "pharmacies_clean.csv", index=False)
    supplier_identities.to_csv(OUTPUT_DIR / "supplier_identities.csv", index=False)
    ledger.to_csv(OUTPUT_DIR / "revenue_ledger.csv", index=False)
    unmatched_aliases.to_csv(OUTPUT_DIR / "unmatched_aliases.csv", index=False)
    ambiguous_aliases.to_csv(OUTPUT_DIR / "ambiguous_aliases.csv", index=False)
    unmatched_erp.to_csv(OUTPUT_DIR / "unmatched_erp_invoices.csv", index=False)
    areas_unknown[areas_unknown["area_confidence"] != "ambiguous"].to_csv(OUTPUT_DIR / "unknown_areas.csv", index=False)
    areas_unknown[areas_unknown["area_confidence"] == "ambiguous"].to_csv(OUTPUT_DIR / "ambiguous_areas.csv", index=False)

    with (OUTPUT_DIR / "identity_stats.json").open("w", encoding="utf-8") as handle:
        json.dump(asdict(identity_stats), handle, indent=2)
    with (OUTPUT_DIR / "revenue_stats.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {"impacts": [asdict(i) for i in revenue_stats.impacts], "total_revenue_egp": revenue_stats.total_revenue_egp},
            handle,
            indent=2,
        )

    analytics = build_analytics(
        ledger,
        pharmacies,
        supplier_identities,
        unmatched_aliases,
        ambiguous_aliases,
        unmatched_erp,
        identity_stats,
        revenue_stats,
        areas_unknown,
        validation,
    )
    analytics_path = OUTPUT_DIR / "analytics.json"
    with analytics_path.open("w", encoding="utf-8") as handle:
        json.dump(analytics, handle, default=str)

    return analytics_path
