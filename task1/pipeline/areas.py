"""Pharmacy area recovery from registry and invoice evidence."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from .normalize import extract_area_from_text


def recover_areas(
    registry: pd.DataFrame,
    erp_invoices: pd.DataFrame,
    erp_details: pd.DataFrame,
    official_areas: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    registry = registry.copy()
    registry["registry_area"] = registry["area"]
    registry["resolved_area"] = registry["area"]
    registry["area_source"] = registry["area"].apply(lambda x: "registry" if pd.notna(x) and str(x).strip() else None)
    registry["area_confidence"] = registry["area"].apply(lambda x: "high" if pd.notna(x) and str(x).strip() else None)

    # Collect area votes from invoice evidence. Registry names are deliberately
    # not used: a name suffix such as "- Helwan" is not reliable proof of the
    # operating area, especially when the registry area is missing.
    votes: dict[int, Counter] = {int(pid): Counter() for pid in registry["id"]}

    def add_vote(pharmacy_id, area, weight, source):
        if pharmacy_id is None or area is None:
            return
        votes.setdefault(int(pharmacy_id), Counter())
        votes[int(pharmacy_id)][(area, source)] += weight

    evidence_counts: dict[int, Counter] = {int(pid): Counter() for pid in registry["id"]}

    # ERP header area/governorate + account_address
    for row in erp_invoices.itertuples(index=False):
        pid = getattr(row, "pharmacy_id", None)
        if pid is None or (isinstance(pid, float) and pid != pid):
            continue
        if pd.notna(row.area) and str(row.area).strip():
            add_vote(int(pid), str(row.area).strip(), 3, "erp_header_area")
            evidence_counts[int(pid)]["invoice_header"] += 1
        for field in ("account_address",):
            val = getattr(row, field, None)
            found = extract_area_from_text(val, official_areas)
            if found:
                add_vote(int(pid), found, 2, "erp_account_address")
                evidence_counts[int(pid)]["account_address"] += 1

    # Delivery addresses from details — need invoice_no -> pharmacy mapping
    # Caller should merge pharmacy_id onto erp_invoices before calling recover_areas on details
    if "pharmacy_id" in erp_details.columns:
        detail_votes = erp_details.dropna(subset=["pharmacy_id"])
        for row in detail_votes.itertuples(index=False):
            found = extract_area_from_text(row.ship_to_address, official_areas)
            if found:
                add_vote(int(row.pharmacy_id), found, 1, "erp_ship_to_address")
                evidence_counts[int(row.pharmacy_id)]["delivery_address"] += 1

    recovery_rows = []
    for _, row in registry.iterrows():
        pharmacy_id = int(row["id"])
        if pd.notna(row["resolved_area"]) and str(row["resolved_area"]).strip():
            counter = votes.get(pharmacy_id, Counter())
            invoice_areas = Counter()
            invoice_breakdown = {}
            for (area, source), weight in counter.items():
                invoice_areas[area] += weight
                invoice_breakdown.setdefault(area, {})[source] = invoice_breakdown.setdefault(area, {}).get(source, 0) + weight
            conflict = bool(invoice_areas and any(a != row["registry_area"] for a in invoice_areas))
            recovery_rows.append(
                {
                    "pharmacy_id": pharmacy_id,
                    "registry_area": row["registry_area"],
                    "resolved_area": row["resolved_area"],
                    "area_source": "registry_conflict" if conflict else "registry",
                    "area_confidence": "conflict" if conflict else "high",
                    "vote_breakdown": invoice_breakdown,
                    "area_conflict": conflict,
                    "evidence_count": int(sum(evidence_counts.get(pharmacy_id, Counter()).values())),
                    "conflicting_area_count": int(sum(1 for a in invoice_areas if a != row["registry_area"])),
                }
            )
            continue

        counter = votes.get(pharmacy_id, Counter())
        if not counter:
            recovery_rows.append(
                {
                    "pharmacy_id": pharmacy_id,
                    "registry_area": row["registry_area"],
                    "resolved_area": None,
                    "area_source": None,
                    "area_confidence": None,
                    "vote_breakdown": {},
                    "area_conflict": False,
                    "evidence_count": 0,
                    "conflicting_area_count": 0,
                }
            )
            continue

        # Aggregate by area across sources
        area_totals: Counter = Counter()
        breakdown = {}
        for (area, source), weight in counter.items():
            area_totals[area] += weight
            breakdown.setdefault(area, {})[source] = breakdown.get(area, {}).get(source, 0) + weight

        best_area, best_weight = area_totals.most_common(1)[0]
        second_weight = area_totals.most_common(2)[1][1] if len(area_totals) > 1 else 0
        if best_weight < 2:
            recovery_rows.append(
                {
                    "pharmacy_id": pharmacy_id,
                    "registry_area": row["registry_area"],
                    "resolved_area": None,
                    "area_source": None,
                    "area_confidence": "insufficient",
                    "vote_breakdown": breakdown.get(best_area, {}),
                    "area_conflict": False,
                    "evidence_count": int(sum(evidence_counts.get(pharmacy_id, Counter()).values())),
                    "conflicting_area_count": int(max(0, len(area_totals) - 1)),
                }
            )
            continue
        confidence = "high" if best_weight >= 3 and best_weight > second_weight * 1.5 else "medium"

        if second_weight and best_weight <= second_weight * 1.5:
            recovery_rows.append(
                {
                    "pharmacy_id": pharmacy_id,
                    "registry_area": row["registry_area"],
                    "resolved_area": None,
                    "area_source": "invoice_evidence_conflict",
                    "area_confidence": "ambiguous",
                    "vote_breakdown": breakdown,
                    "area_conflict": True,
                    "evidence_count": int(sum(evidence_counts.get(pharmacy_id, Counter()).values())),
                    "conflicting_area_count": int(len(area_totals) - 1),
                }
            )
            continue

        recovery_rows.append(
            {
                "pharmacy_id": pharmacy_id,
                "registry_area": row["registry_area"],
                "resolved_area": best_area,
                "area_source": "invoice_evidence",
                "area_confidence": confidence,
                "vote_breakdown": breakdown.get(best_area, {}),
                "area_conflict": bool(second_weight),
                "evidence_count": int(sum(evidence_counts.get(pharmacy_id, Counter()).values())),
                "conflicting_area_count": int(sum(1 for a in area_totals if a != best_area)),
            }
        )

    areas_df = pd.DataFrame(recovery_rows)
    unknown = areas_df[areas_df["resolved_area"].isna()]
    return areas_df, unknown
