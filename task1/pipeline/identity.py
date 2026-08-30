"""Pharmacy entity resolution."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd
from rapidfuzz import fuzz, process

from .config import ALIAS_PHARMACY_SCORE_THRESHOLD, ERP_ALIAS_SCORE_THRESHOLD
from .normalize import extract_area_from_text, meaningful_tokens, normalize_lookup_key, normalize_name


@dataclass
class IdentityStats:
    aliases_total: int = 0
    aliases_matched: int = 0
    aliases_unmatched: int = 0
    aliases_ambiguous: int = 0
    erp_invoices_total: int = 0
    erp_invoices_matched: int = 0
    erp_invoices_unmatched: int = 0
    erp_invoices_ambiguous: int = 0
    erp_revenue_matched: float = 0.0
    erp_revenue_unmatched: float = 0.0
    app_direct_links: int = 0
    legacy_direct_links: int = 0


def _location_tokens_from_registry(registry: pd.DataFrame, official_areas: list[str]) -> set[str]:
    tokens = set()
    for area in official_areas:
        tokens.update(area.lower().split())
    tokens -= {"city"}
    return tokens


def _match_alias_to_pharmacy(alias_norm: str, registry: pd.DataFrame, location_tokens: set[str], branch_area: str | None):
    alias_tokens = meaningful_tokens(alias_norm)
    if len(alias_tokens) < 1:
        return None, 0.0, "empty_name"

    # An exact normalized registry name is stronger than a fuzzy candidate
    # ranking. Keep it ambiguous if the registry itself contains duplicates.
    exact_rows = registry[registry["name_norm"] == alias_norm]
    if len(exact_rows) == 1:
        return int(exact_rows.iloc[0]["id"]), 100.0, "exact_registry_name"

    choices = registry["name_norm"].tolist()
    matches = process.extract(
        alias_norm,
        choices,
        scorer=fuzz.token_sort_ratio,
        limit=8,
        score_cutoff=ALIAS_PHARMACY_SCORE_THRESHOLD,
    )
    if not matches:
        return None, 0.0, "below_threshold"

    alias_locs = alias_tokens & location_tokens
    scored = []
    for name_norm, score, idx in matches:
        row = registry.iloc[idx]
        pharm_tokens = meaningful_tokens(name_norm)
        # Require overlapping brand tokens (ignore shared location-only matches)
        brand_alias = alias_tokens - location_tokens
        brand_pharm = pharm_tokens - location_tokens
        if brand_alias and brand_pharm and not (brand_alias & brand_pharm):
            continue
        if len(brand_alias) >= 2 and len(brand_alias & brand_pharm) < 1:
            continue
        pharm_locs = pharm_tokens & location_tokens
        if alias_locs and pharm_locs and not (alias_locs & pharm_locs):
            # Location conflict in the names themselves
            continue
        if alias_locs and not pharm_locs:
            area = row["area"] if pd.notna(row["area"]) else None
            area_tokens = set(str(area).lower().split()) if area else set()
            if not (alias_locs & area_tokens):
                continue
        scored.append((int(row["id"]), float(score), idx, name_norm))

    if not scored:
        return None, float(matches[0][1]), "location_conflict"

    scored.sort(key=lambda x: x[1], reverse=True)
    best_id, best_score, _, _ = scored[0]
    second = scored[1][1] if len(scored) > 1 else 0.0
    distinct_ids = {s[0] for s in scored if s[1] >= best_score - 5}

    if len(distinct_ids) > 1:
        if branch_area:
            area_hits = registry[registry["id"].isin(distinct_ids) & (registry["area"] == branch_area)]
            if len(area_hits) == 1:
                return int(area_hits.iloc[0]["id"]), best_score, "area_disambiguated"
        return None, best_score, "ambiguous_registry_name"

    if second and best_score - second < 4 and scored[0][0] != scored[1][0]:
        return None, best_score, "ambiguous_score_gap"

    return best_id, best_score, "direct_match"


def resolve_identities(
    registry: pd.DataFrame,
    branches: pd.DataFrame,
    aliases: pd.DataFrame,
    erp_invoices: pd.DataFrame,
    app_invoices: pd.DataFrame,
    legacy_invoices: pd.DataFrame,
    official_areas: list[str] | None = None,
):
    stats = IdentityStats()
    registry = registry.copy()
    registry["name_norm"] = registry["name"].map(normalize_name)
    official_areas = official_areas or ["Smouha", "Nasr City", "Faisal", "Mohandessin"]
    location_tokens = _location_tokens_from_registry(registry, official_areas)

    branch_area = {
        int(k): (v if pd.notna(v) else None) for k, v in branches.set_index("branch_id")["area"].to_dict().items()
    }

    alias_columns = {
        "alias_id": [],
        "account_name": [],
        "branch_id": [],
        "supplier_code": [],
        "pharmacy_id": [],
        "match_score": [],
        "match_method": [],
        "match_status": [],
        "match_evidence": [],
    }
    stats.aliases_total = len(aliases)
    for row in aliases.itertuples(index=False):
        pharmacy_id, score, method = _match_alias_to_pharmacy(
            normalize_name(row.account_name),
            registry,
            location_tokens,
            branch_area.get(int(row.branch_id)),
        )
        if pharmacy_id is not None:
            stats.aliases_matched += 1
        else:
            stats.aliases_unmatched += 1
            if method.startswith("ambiguous"):
                stats.aliases_ambiguous += 1
        alias_columns["alias_id"].append(row.alias_id)
        alias_columns["account_name"].append(row.account_name)
        alias_columns["branch_id"].append(int(row.branch_id))
        alias_columns["supplier_code"].append(int(row.supplier_code))
        alias_columns["pharmacy_id"].append(pharmacy_id)
        alias_columns["match_score"].append(score)
        alias_columns["match_method"].append(method)
        alias_columns["match_status"].append("MATCHED" if pharmacy_id is not None else ("AMBIGUOUS" if method.startswith("ambiguous") else "UNMATCHED"))
        alias_columns["match_evidence"].append(method)
    alias_map = pd.DataFrame(alias_columns, columns=list(alias_columns))

    by_name_branch: dict[tuple[str, int], list] = defaultdict(list)
    by_name: dict[str, list] = defaultdict(list)
    matched_recs = []
    for rec in alias_map.itertuples(index=False):
        if rec.pharmacy_id is None or pd.isna(rec.pharmacy_id):
            continue
        key_name = normalize_lookup_key(rec.account_name)
        by_name_branch[(key_name, int(rec.branch_id))].append(rec)
        by_name[key_name].append(rec)
        matched_recs.append(rec)

    branch_alias_names: dict[int, list[tuple[str, object]]] = defaultdict(list)
    for rec in matched_recs:
        branch_alias_names[int(rec.branch_id)].append((normalize_lookup_key(rec.account_name), rec))

    unique_alias_rec_by_name = {normalize_lookup_key(r.account_name): r for r in matched_recs}
    unique_alias_names = list(unique_alias_rec_by_name.keys())

    unique_erp = erp_invoices[["account_name", "branch_code"]].drop_duplicates()
    unique_erp = unique_erp.assign(name_key=unique_erp["account_name"].map(normalize_lookup_key))

    name_match: dict[tuple[str, int], dict] = {}
    for row in unique_erp.itertuples(index=False):
        name_key = row.name_key
        branch_id = int(row.branch_code)
        chosen = None
        match_method = "unmatched"
        match_score = 0.0

        if (name_key, branch_id) in by_name_branch:
            chosen = by_name_branch[(name_key, branch_id)][0]
            match_method = "exact_name_branch"
            match_score = 100.0
        elif name_key in by_name:
            recs = by_name[name_key]
            pharmacy_ids = {int(r.pharmacy_id) for r in recs}
            if len(pharmacy_ids) == 1:
                chosen = recs[0]
                match_method = "exact_name_unique_pharmacy"
                match_score = 100.0
            else:
                at_branch = [r for r in recs if int(r.branch_id) == branch_id]
                if at_branch and len({int(r.pharmacy_id) for r in at_branch}) == 1:
                    chosen = at_branch[0]
                    match_method = "exact_name_branch_disambiguated"
                    match_score = 100.0
                else:
                    match_method = "ambiguous_exact_name"

        if chosen is None and match_method != "ambiguous_exact_name":
            candidates = branch_alias_names.get(branch_id, [])
            if candidates:
                names = [c[0] for c in candidates]
                fuzzy = process.extract(
                    name_key,
                    names,
                    scorer=fuzz.token_sort_ratio,
                    limit=2,
                    score_cutoff=ERP_ALIAS_SCORE_THRESHOLD,
                )
                if fuzzy:
                    best = fuzzy[0]
                    second = fuzzy[1][1] if len(fuzzy) > 1 else 0
                    if best[1] - second >= 6 or len(fuzzy) == 1:
                        chosen = candidates[best[2]][1]
                        match_method = "fuzzy_name_at_branch"
                        match_score = float(best[1])

        if chosen is None and match_method != "ambiguous_exact_name" and unique_alias_names:
            fuzzy = process.extractOne(
                name_key,
                unique_alias_names,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=max(ERP_ALIAS_SCORE_THRESHOLD, 93),
            )
            if fuzzy:
                matched_name, fscore, _ = fuzzy
                chosen = unique_alias_rec_by_name[matched_name]
                match_method = "fuzzy_name_global"
                match_score = float(fscore)

        name_match[(name_key, branch_id)] = {
            "pharmacy_id": int(chosen.pharmacy_id) if chosen is not None else None,
            "alias_id": chosen.alias_id if chosen is not None else None,
            "supplier_code": int(chosen.supplier_code) if chosen is not None else None,
            "match_score": match_score,
            "match_method": match_method,
        }

    erp_links = []
    stats.erp_invoices_total = len(erp_invoices)
    for inv in erp_invoices.itertuples(index=False):
        name_key = normalize_lookup_key(inv.account_name)
        branch_id = int(inv.branch_code)
        rec = name_match.get((name_key, branch_id), {})
        pharmacy_id = rec.get("pharmacy_id")
        revenue = float(inv.total_after_discount) if pd.notna(inv.total_after_discount) else 0.0
        if pharmacy_id is not None:
            stats.erp_invoices_matched += 1
            stats.erp_revenue_matched += revenue
        else:
            stats.erp_invoices_unmatched += 1
            stats.erp_revenue_unmatched += revenue
            if str(rec.get("match_method", "")).startswith("ambiguous"):
                stats.erp_invoices_ambiguous += 1
        erp_links.append(
            {
                "invoice_no": inv.invoice_no,
                "account_name": inv.account_name,
                "branch_code": branch_id,
                "pharmacy_id": pharmacy_id,
                "alias_id": rec.get("alias_id"),
                "supplier_code": rec.get("supplier_code"),
                "match_score": rec.get("match_score", 0.0),
                "match_method": rec.get("match_method", "unmatched"),
                "match_status": "MATCHED" if pharmacy_id is not None else ("AMBIGUOUS" if str(rec.get("match_method", "")).startswith("ambiguous") else "UNMATCHED"),
                "entry_date": inv.entry_date,
                "total_after_discount": revenue,
                "record_state": getattr(inv, "record_state", None),
            }
        )
    erp_links_df = pd.DataFrame(erp_links)

    stats.app_direct_links = int(app_invoices["customer_id"].nunique())
    legacy = legacy_invoices.copy()
    legacy["pharmacy_id"] = pd.to_numeric(
        legacy["account_ref"].str.extract(r"P:(\d+)", expand=False), errors="coerce"
    ).astype("Int64")
    stats.legacy_direct_links = int(legacy["pharmacy_id"].nunique())

    pharmacy_aliases = alias_map.dropna(subset=["pharmacy_id"]).copy()
    pharmacy_aliases["pharmacy_id"] = pharmacy_aliases["pharmacy_id"].astype(int)

    canonical = registry[["id", "name", "governorate", "area"]].rename(
        columns={"id": "pharmacy_id", "name": "registry_name"}
    )
    canonical["canonical_name"] = canonical["registry_name"]

    supplier_identities = pharmacy_aliases.merge(
        branches[["branch_id", "parent_company", "branch_tag"]],
        on="branch_id",
        how="left",
    )

    unresolved_aliases = alias_map[alias_map["pharmacy_id"].isna()].copy()
    unresolved_aliases = unresolved_aliases.merge(
        branches[["branch_id", "parent_company", "branch_tag"]],
        on="branch_id",
        how="left",
    )
    ambiguous_aliases = unresolved_aliases[unresolved_aliases["match_status"] == "AMBIGUOUS"].copy()
    unmatched_aliases = unresolved_aliases[unresolved_aliases["match_status"] == "UNMATCHED"].copy()
    stats.aliases_unmatched = len(unmatched_aliases)
    unmatched_erp = erp_links_df[erp_links_df["pharmacy_id"].isna()].copy()

    return canonical, supplier_identities, unmatched_aliases, ambiguous_aliases, unmatched_erp, erp_links_df, stats
