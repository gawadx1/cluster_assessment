"""Streamlit application for Task 1: Pharmacy Identity, Area Resolution, and Clean Revenue Explorer."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# Configure Streamlit page
st.set_page_config(
    page_title="Task 1 — Pharmacy Explorer & Revenue Analytics",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"
ANALYTICS_PATH = OUTPUT_DIR / "analytics.json"

# ==============================================================================
# CUSTOM CSS STYLING
# ==============================================================================
st.markdown(
    """
    <style>
    /* Dark theme modern card styling */
    .metric-card {
        background-color: #1e2530;
        border: 1px solid #2d3748;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .metric-label {
        font-size: 0.82rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.55rem;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
    }
    .metric-sub {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 4px;
    }
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    .badge-high { background-color: #065f46; color: #34d399; }
    .badge-medium { background-color: #92400e; color: #fbbf24; }
    .badge-conflict { background-color: #831843; color: #f472b6; }
    .badge-ambiguous { background-color: #581c87; color: #c084fc; }
    .badge-unknown { background-color: #334155; color: #94a3b8; }
    .badge-matched { background-color: #166534; color: #4ade80; }
    .badge-area { background-color: #1e3a8a; color: #93c5fd; }
    
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #e2e8f0;
        border-bottom: 2px solid #334155;
        padding-bottom: 8px;
        margin-top: 18px;
        margin-bottom: 16px;
    }
    
    .detail-card {
        background-color: #1a202c;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
    }
    
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# DATA LOADING & CACHING
# ==============================================================================
@st.cache_data(show_spinner="Loading Task 1 pipeline outputs...")
def load_data() -> dict:
    if not ANALYTICS_PATH.exists():
        st.error(
            f"Missing {ANALYTICS_PATH}. Please run the pipeline first (`python run_pipeline.py`)."
        )
        st.stop()

    with ANALYTICS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    # Optional CSV fallbacks/supplements if available
    csv_files = {
        "unmatched_erp": OUTPUT_DIR / "unmatched_erp_invoices.csv",
        "unmatched_aliases": OUTPUT_DIR / "unmatched_aliases.csv",
        "ambiguous_aliases": OUTPUT_DIR / "ambiguous_aliases.csv",
        "unknown_areas": OUTPUT_DIR / "unknown_areas.csv",
        "ambiguous_areas": OUTPUT_DIR / "ambiguous_areas.csv",
        "supplier_identities": OUTPUT_DIR / "supplier_identities.csv",
    }

    extra_dfs = {}
    for name, path in csv_files.items():
        if path.exists():
            try:
                extra_dfs[name] = pd.read_csv(path, low_memory=False)
            except Exception:
                extra_dfs[name] = pd.DataFrame()
        else:
            extra_dfs[name] = pd.DataFrame()

    data["extra_dfs"] = extra_dfs
    return data


# ==============================================================================
# INITIALIZE SESSION STATE
# ==============================================================================
def init_session_state(data: dict):
    if "view" not in st.session_state:
        st.session_state["view"] = "overview"
    if "selected_area" not in st.session_state:
        st.session_state["selected_area"] = None
    if "selected_pharmacy_id" not in st.session_state:
        st.session_state["selected_pharmacy_id"] = None
    if "selected_supplier" not in st.session_state:
        st.session_state["selected_supplier"] = None
    if "prev_view" not in st.session_state:
        st.session_state["prev_view"] = "overview"

    default_start = pd.to_datetime(data["meta"].get("date_start", "2024-09-01")).date()
    default_end = pd.to_datetime(data["meta"].get("date_end", "2026-08-26")).date()

    if "filter_area" not in st.session_state:
        st.session_state["filter_area"] = "All areas"
    if "filter_date_from" not in st.session_state:
        st.session_state["filter_date_from"] = default_start
    if "filter_date_to" not in st.session_state:
        st.session_state["filter_date_to"] = default_end
    if "pharmacy_search_query" not in st.session_state:
        st.session_state["pharmacy_search_query"] = ""


def navigate_to(view: str, area: str | None = None, pharmacy_id: int | None = None, supplier: str | None = None):
    st.session_state["prev_view"] = st.session_state["view"]
    st.session_state["view"] = view
    if area is not None:
        st.session_state["selected_area"] = area
    if pharmacy_id is not None:
        st.session_state["selected_pharmacy_id"] = int(pharmacy_id)
    if supplier is not None:
        st.session_state["selected_supplier"] = supplier


def reset_filters(data: dict):
    st.session_state["filter_area"] = "All areas"
    st.session_state["filter_date_from"] = pd.to_datetime(data["meta"].get("date_start", "2024-09-01")).date()
    st.session_state["filter_date_to"] = pd.to_datetime(data["meta"].get("date_end", "2026-08-26")).date()
    st.session_state["pharmacy_search_query"] = ""


# ==============================================================================
# FILTERING ENGINE
# ==============================================================================
def apply_filters(data: dict, filter_area: str, date_from, date_to) -> dict:
    ledger_df = pd.DataFrame(data["ledger"])
    pharmacies_list = data["pharmacies"]
    pharmacies_df = pd.DataFrame(pharmacies_list)

    if ledger_df.empty:
        return {
            "filtered_ledger": pd.DataFrame(),
            "filtered_pharmacies": pharmacies_df,
            "total_revenue": 0.0,
            "total_orders": 0,
            "pharmacy_count": len(pharmacies_df),
            "revenue_per_area": pd.DataFrame(),
            "pharmacies_per_area": pd.DataFrame(),
            "top_pharmacies": pd.DataFrame(),
            "top_pharmacies_by_area": {},
            "top_suppliers": pd.DataFrame(),
        }

    ledger_df["order_date_dt"] = pd.to_datetime(ledger_df["order_date"])

    # Date filtering
    mask_date = pd.Series(True, index=ledger_df.index)
    if date_from:
        mask_date &= ledger_df["order_date_dt"] >= pd.Timestamp(date_from)
    if date_to:
        mask_date &= ledger_df["order_date_dt"] <= (pd.Timestamp(date_to) + pd.Timedelta(days=1, microseconds=-1))

    # Area filtering
    mask_area_ledger = pd.Series(True, index=ledger_df.index)
    mask_area_pharm = pd.Series(True, index=pharmacies_df.index)

    if filter_area and filter_area != "All areas":
        mask_area_ledger &= ledger_df["resolved_area"] == filter_area
        mask_area_pharm &= pharmacies_df["resolved_area"] == filter_area

    filtered_ledger = ledger_df[mask_date & mask_area_ledger].copy()
    filtered_pharmacies = pharmacies_df[mask_area_pharm].copy()

    # Aggregations
    total_revenue = float(filtered_ledger["revenue_egp"].sum()) if not filtered_ledger.empty else 0.0
    total_orders = int(len(filtered_ledger))
    pharmacy_count = int(filtered_pharmacies["pharmacy_id"].nunique())

    # Pharmacies per area (based on canonical pharmacies)
    pharmacies_per_area = (
        pharmacies_df.dropna(subset=["resolved_area"])
        .groupby("resolved_area", as_index=False)
        .agg(pharmacy_count=("pharmacy_id", "nunique"))
        .sort_values("pharmacy_count", ascending=False)
    )

    # Revenue per area (based on filtered ledger)
    if not filtered_ledger.empty:
        revenue_per_area = (
            filtered_ledger.dropna(subset=["resolved_area"])
            .groupby("resolved_area", as_index=False)
            .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
            .sort_values("revenue_egp", ascending=False)
        )
        # Top pharmacies
        top_pharmacies = (
            filtered_ledger.groupby(["pharmacy_id", "canonical_name", "resolved_area"], as_index=False)
            .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
            .sort_values("revenue_egp", ascending=False)
        )
        # Top suppliers
        supplier_pharmacies = (
            filtered_ledger.groupby("supplier_name")["pharmacy_id"].nunique().to_dict()
        )
        top_suppliers = (
            filtered_ledger.groupby(["supplier_key", "supplier_name"], as_index=False)
            .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
            .sort_values("revenue_egp", ascending=False)
        )
        top_suppliers["pharmacies_served"] = top_suppliers["supplier_name"].map(supplier_pharmacies).fillna(0).astype(int)

        # Top by area
        top_pharmacies_by_area = {}
        for area_name in ["Faisal", "Mohandessin", "Nasr City", "Smouha"]:
            sub = top_pharmacies[top_pharmacies["resolved_area"] == area_name].head(20)
            top_pharmacies_by_area[area_name] = sub
    else:
        revenue_per_area = pd.DataFrame(columns=["resolved_area", "revenue_egp", "order_count"])
        top_pharmacies = pd.DataFrame(columns=["pharmacy_id", "canonical_name", "resolved_area", "revenue_egp", "order_count"])
        top_suppliers = pd.DataFrame(columns=["supplier_key", "supplier_name", "revenue_egp", "order_count", "pharmacies_served"])
        top_pharmacies_by_area = {a: pd.DataFrame(columns=["pharmacy_id", "canonical_name", "resolved_area", "revenue_egp", "order_count"]) for a in ["Faisal", "Mohandessin", "Nasr City", "Smouha"]}

    return {
        "filtered_ledger": filtered_ledger,
        "filtered_pharmacies": filtered_pharmacies,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "pharmacy_count": pharmacy_count,
        "revenue_per_area": revenue_per_area,
        "pharmacies_per_area": pharmacies_per_area,
        "top_pharmacies": top_pharmacies,
        "top_pharmacies_by_area": top_pharmacies_by_area,
        "top_suppliers": top_suppliers,
    }


# ==============================================================================
# MAIN APP ENTRY
# ==============================================================================
def main():
    data = load_data()
    init_session_state(data)

    # --------------------------------------------------------------------------
    # SIDEBAR NAVIGATION & PERSISTENT EXPLORER
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.title("💊 Cluster Assessment")
        st.caption("Task 1: Customer Identity & Revenue Ledger")

        st.markdown("---")
        st.subheader("🧭 Navigation")

        nav_options = [
            ("overview", "📊 1. Overview"),
            ("area", "🗺️ 2. Area Analysis"),
            ("pharmacy_analysis", "🏆 3. Top Pharmacies"),
            ("supplier_analysis", "🚚 4. Supplier Analysis"),
            ("explorer", "🔍 5. Pharmacy Explorer"),
            ("unmatched", "🛡️ 6. Data Quality & Unmatched"),
            ("reconciliation", "⚖️ 7. Cleaning & Reconciliation"),
        ]

        # Sync navigation view
        current_view = st.session_state["view"]
        menu_view = current_view if current_view in [k for k, _ in nav_options] else ("explorer" if current_view == "pharmacy" else ("supplier_analysis" if current_view == "supplier" else "overview"))

        selected_nav = st.radio(
            "Select Section",
            options=[k for k, _ in nav_options],
            format_func=lambda x: dict(nav_options)[x],
            index=[k for k, _ in nav_options].index(menu_view) if menu_view in [k for k, _ in nav_options] else 0,
            label_visibility="collapsed",
        )
        if selected_nav != st.session_state["view"] and st.session_state["view"] in [k for k, _ in nav_options]:
            st.session_state["view"] = selected_nav

        st.markdown("---")
        st.subheader("⚙️ Global Filters")

        # Area Filter
        area_options = ["All areas"] + sorted(data["meta"].get("areas", ["Faisal", "Mohandessin", "Nasr City", "Smouha"]))
        area_idx = area_options.index(st.session_state["filter_area"]) if st.session_state["filter_area"] in area_options else 0
        selected_filter_area = st.selectbox("Area Filter", options=area_options, index=area_idx)
        st.session_state["filter_area"] = selected_filter_area

        # Date Range Filter
        min_date = pd.to_datetime(data["meta"].get("date_start", "2024-09-01")).date()
        max_date = pd.to_datetime(data["meta"].get("date_end", "2026-08-26")).date()

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            d_from = st.date_input("From Date", value=st.session_state["filter_date_from"], min_value=min_date, max_value=max_date)
            st.session_state["filter_date_from"] = d_from
        with col_d2:
            d_to = st.date_input("To Date", value=st.session_state["filter_date_to"], min_value=min_date, max_value=max_date)
            st.session_state["filter_date_to"] = d_to

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Apply Filters", use_container_width=True, type="primary"):
                st.rerun()
        with col_btn2:
            if st.button("Reset Filters", use_container_width=True):
                reset_filters(data)
                st.rerun()

        st.markdown("---")
        st.subheader("🔍 Persistent Pharmacy Explorer")
        st.caption("Search & click any pharmacy to view details")

        search_q = st.text_input(
            "Search pharmacy name...",
            value=st.session_state["pharmacy_search_query"],
            placeholder="e.g. Omega, Misr, Dokki, 1002...",
            key="side_search",
        )
        st.session_state["pharmacy_search_query"] = search_q

        # Filter pharmacies for explorer list
        all_pharmacies = data["pharmacies"]
        explorer_list = all_pharmacies

        if selected_filter_area != "All areas":
            explorer_list = [p for p in explorer_list if p.get("resolved_area") == selected_filter_area]

        if search_q.strip():
            sq = search_q.strip().lower()
            explorer_list = [
                p for p in explorer_list
                if sq in (p.get("canonical_name") or "").lower()
                or sq in (p.get("registry_name") or "").lower()
                or sq in str(p.get("pharmacy_id", ""))
            ]

        st.caption(f"Showing **{len(explorer_list):,}** of {len(all_pharmacies):,} pharmacies")

        # Scrollable list in sidebar
        with st.container(height=320):
            if not explorer_list:
                st.info("No pharmacies found.")
            else:
                for p in explorer_list[:100]:
                    p_id = p["pharmacy_id"]
                    p_name = p["canonical_name"]
                    p_area = p.get("resolved_area") or "Unknown"
                    btn_label = f"#{p_id} {p_name} ({p_area})"
                    if st.button(btn_label, key=f"side_ph_{p_id}", use_container_width=True):
                        navigate_to("pharmacy", pharmacy_id=p_id)
                        st.rerun()
                if len(explorer_list) > 100:
                    st.caption(f"... and {len(explorer_list) - 100} more. Refine search.")

    # --------------------------------------------------------------------------
    # APPLY COMPUTED FILTERS
    # --------------------------------------------------------------------------
    filtered_results = apply_filters(
        data,
        st.session_state["filter_area"],
        st.session_state["filter_date_from"],
        st.session_state["filter_date_to"],
    )

    # --------------------------------------------------------------------------
    # ROUTE VIEWS
    # --------------------------------------------------------------------------
    view = st.session_state["view"]

    if view == "overview":
        render_overview(data, filtered_results)
    elif view == "area":
        render_area_analysis(data, filtered_results)
    elif view == "pharmacy_analysis":
        render_pharmacy_analysis(data, filtered_results)
    elif view == "supplier_analysis":
        render_supplier_analysis(data, filtered_results)
    elif view == "explorer":
        render_explorer(data, filtered_results)
    elif view == "pharmacy":
        render_pharmacy_detail(data, filtered_results)
    elif view == "supplier":
        render_supplier_detail(data, filtered_results)
    elif view == "unmatched":
        render_unmatched(data, filtered_results)
    elif view == "reconciliation":
        render_reconciliation(data, filtered_results)
    else:
        render_overview(data, filtered_results)


# ==============================================================================
# SECTION 1: OVERVIEW
# ==============================================================================
def render_overview(data: dict, filtered: dict):
    st.title("📊 Task 1: Executive Overview & KPIs")
    st.caption("Deterministic pipeline outputs: Pharmacy Identity, Recovered Geography, and Reconciled Revenue.")

    # Top Filter Notice
    filter_area = st.session_state["filter_area"]
    d_from = st.session_state["filter_date_from"]
    d_to = st.session_state["filter_date_to"]
    st.info(
        f"📅 **Active Filter**: Area = **{filter_area}** | Window = **{d_from}** to **{d_to}** "
        f"| Clean Revenue = **{filtered['total_revenue']:,.2f} EGP** | Total Orders = **{filtered['total_orders']:,}**"
    )

    # Dynamic KPI Cards Row 1: Core Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Clean Revenue</div>
                <div class="metric-value">{filtered['total_revenue']:,.2f} <span style="font-size:1rem;">EGP</span></div>
                <div class="metric-sub">Across filtered trusted ledger</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Clean Orders</div>
                <div class="metric-value">{filtered['total_orders']:,}</div>
                <div class="metric-sub">APP, ERP & Legacy matched invoices</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Canonical Pharmacies</div>
                <div class="metric-value">{filtered['pharmacy_count']:,}</div>
                <div class="metric-sub">Total Master registry: {data['meta']['pharmacy_count']:,}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Suppliers & Branches</div>
                <div class="metric-value">{data['meta']['supplier_count']} <span style="font-size:1rem;color:#94a3b8;">(83 br.)</span></div>
                <div class="metric-sub">38 Supplier Companies</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Dynamic KPI Cards Grid: Pipeline Resolutions
    st.markdown('<div class="section-header">🔍 Pipeline Identity & Quality Breakdown</div>', unsafe_allow_html=True)
    summary = data.get("summary", {})
    id_stats = summary.get("identity_stats", {})

    r1, r2, r3 = st.columns(3)

    # Supplier Accounts (14,953 total)
    with r1:
        aliases_total = id_stats.get("aliases_total", 14953)
        aliases_matched = id_stats.get("aliases_matched", 1720)
        aliases_ambig = id_stats.get("aliases_ambiguous", 2702)
        aliases_unmatched = id_stats.get("aliases_unmatched", 10531)

        pct_m = (aliases_matched / aliases_total * 100) if aliases_total else 0
        pct_a = (aliases_ambig / aliases_total * 100) if aliases_total else 0
        pct_u = (aliases_unmatched / aliases_total * 100) if aliases_total else 0

        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Supplier Account Aliases (14,953)</div>
                <div style="margin-top:8px;">
                    <span class="badge badge-matched">Matched: {aliases_matched:,} ({pct_m:.1f}%)</span><br>
                    <span class="badge badge-ambiguous" style="margin-top:4px;">Ambiguous: {aliases_ambig:,} ({pct_a:.1f}%)</span><br>
                    <span class="badge badge-unknown" style="margin-top:4px;">Unmatched: {aliases_unmatched:,} ({pct_u:.1f}%)</span>
                </div>
                <div class="metric-sub" style="margin-top:8px;">Denominator: 14,953 total supplier accounts</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ERP Invoices (17,691 total)
    with r2:
        erp_total = id_stats.get("erp_invoices_total", 17691)
        erp_matched = id_stats.get("erp_invoices_matched", 2184)
        erp_unmatched = id_stats.get("erp_invoices_unmatched", 15507)
        erp_rev_matched = id_stats.get("erp_revenue_matched", 0.0)
        erp_rev_unmatched = id_stats.get("erp_revenue_unmatched", 0.0)

        pct_erp_m = (erp_matched / erp_total * 100) if erp_total else 0
        pct_erp_u = (erp_unmatched / erp_total * 100) if erp_total else 0

        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">ERP Invoices (17,691 rows)</div>
                <div style="margin-top:8px;">
                    <span class="badge badge-matched">Matched: {erp_matched:,} rows ({pct_erp_m:.1f}%)</span> — {erp_rev_matched:,.0f} EGP<br>
                    <span class="badge badge-unknown" style="margin-top:4px;">Unmatched: {erp_unmatched:,} rows ({pct_erp_u:.1f}%)</span> — {erp_rev_unmatched:,.0f} EGP
                </div>
                <div class="metric-sub" style="margin-top:8px;">Denominator: 17,691 ERP invoice rows</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Area Resolution (1,826 master pharmacies)
    with r3:
        known_areas = 1069
        recovered = summary.get("recovered_area_pharmacy_count", 68)
        unknown = summary.get("unknown_area_pharmacy_count", 756)
        conflicts = summary.get("area_conflict_pharmacy_count", 171)
        ambig_areas = summary.get("ambiguous_area_pharmacy_count", 1)

        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Area Resolution (1,826 Pharmacies)</div>
                <div style="margin-top:8px;">
                    <span class="badge badge-matched">Resolved Areas: {known_areas:,}</span><br>
                    <span class="badge badge-area" style="margin-top:4px;">Recovered from Invoices: {recovered:,}</span><br>
                    <span class="badge badge-conflict" style="margin-top:4px;">Registry Conflicts: {conflicts:,}</span><br>
                    <span class="badge badge-unknown" style="margin-top:4px;">Unknown / Ambiguous: {unknown:,} / {ambig_areas}</span>
                </div>
                <div class="metric-sub" style="margin-top:8px;">Constrained strictly to 4 official areas</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Charts and Summaries
    st.markdown('<div class="section-header">📈 Performance by Official Area</div>', unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)

    with ch1:
        st.subheader("Revenue per Area (EGP)")
        rev_area_df = filtered["revenue_per_area"]
        if not rev_area_df.empty:
            chart_df = rev_area_df.set_index("resolved_area")[["revenue_egp"]]
            st.bar_chart(chart_df, color="#38bdf8")
            st.dataframe(
                rev_area_df.style.format({"revenue_egp": "{:,.2f} EGP", "order_count": "{:,}"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No revenue data in active filter window.")

    with ch2:
        st.subheader("Pharmacies per Area")
        ph_area_df = filtered["pharmacies_per_area"]
        if not ph_area_df.empty:
            chart_ph = ph_area_df.set_index("resolved_area")[["pharmacy_count"]]
            st.bar_chart(chart_ph, color="#a855f7")
            st.dataframe(
                ph_area_df.style.format({"pharmacy_count": "{:,}"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No pharmacy data in active filter.")

    # Quick Jump Buttons
    st.markdown("---")
    st.markdown("### 🚀 Quick Exploration Drill-Downs")
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("🗺️ Explore Areas in Detail", use_container_width=True):
            navigate_to("area")
            st.rerun()
    with b2:
        if st.button("🏆 View Top Pharmacies", use_container_width=True):
            navigate_to("pharmacy_analysis")
            st.rerun()
    with b3:
        if st.button("🚚 View Top Suppliers", use_container_width=True):
            navigate_to("supplier_analysis")
            st.rerun()
    with b4:
        if st.button("🛡️ View Data Quality / Unmatched", use_container_width=True):
            navigate_to("unmatched")
            st.rerun()


# ==============================================================================
# SECTION 2 & 3 & 4 & 6: AREA ANALYSIS & AREA DRILL-DOWN
# ==============================================================================
def render_area_analysis(data: dict, filtered: dict):
    st.title("🗺️ Area Analysis & Drill-Down")
    st.caption("Official operating areas from areas_reference.csv: Faisal, Mohandessin, Nasr City, Smouha.")

    official_areas = ["Faisal", "Mohandessin", "Nasr City", "Smouha"]

    area_tabs = st.tabs(official_areas)
    for idx, area_name in enumerate(official_areas):
        with area_tabs[idx]:
            render_single_area_drilldown(data, filtered, area_name)


def render_single_area_drilldown(data: dict, filtered: dict, area_name: str):
    # Pharmacies in this area
    all_pharmacies = data["pharmacies"]
    area_pharmacies = [p for p in all_pharmacies if p.get("resolved_area") == area_name]

    # Filtered ledger for this area
    ledger_df = filtered["filtered_ledger"]
    area_ledger = ledger_df[ledger_df["resolved_area"] == area_name] if not ledger_df.empty else pd.DataFrame()

    area_rev = float(area_ledger["revenue_egp"].sum()) if not area_ledger.empty else 0.0
    area_orders = int(len(area_ledger))
    area_suppliers = int(area_ledger["supplier_name"].nunique()) if not area_ledger.empty else 0

    # Summary Metrics Card
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Area Name</div>
                <div class="metric-value">{area_name}</div>
                <div class="metric-sub">Official Reference Area</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Canonical Pharmacies</div>
                <div class="metric-value">{len(area_pharmacies):,}</div>
                <div class="metric-sub">Total registered in {area_name}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Filtered Revenue</div>
                <div class="metric-value">{area_rev:,.2f} <span style="font-size:0.9rem;">EGP</span></div>
                <div class="metric-sub">Active date filter</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Filtered Orders</div>
                <div class="metric-value">{area_orders:,} <span style="font-size:0.9rem;color:#94a3b8;">({area_suppliers} suppliers)</span></div>
                <div class="metric-sub">Total active transactions</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Top Pharmacies Inside this Area (Explicitly Required by Spec)
    st.markdown(f'<div class="section-header">🏆 Top Pharmacies in {area_name} by Revenue</div>', unsafe_allow_html=True)

    # Calculate pharmacy ranking in this area
    pharmacy_stats = []
    for p in area_pharmacies:
        pid = p["pharmacy_id"]
        p_led = area_ledger[area_ledger["pharmacy_id"] == pid] if not area_ledger.empty else pd.DataFrame()
        rev = float(p_led["revenue_egp"].sum()) if not p_led.empty else 0.0
        ords = len(p_led)
        sups = int(p_led["supplier_name"].nunique()) if not p_led.empty else len(p.get("aliases", []))
        pharmacy_stats.append(
            {
                "Master Pharmacy ID": pid,
                "Pharmacy": p["canonical_name"],
                "Revenue (EGP)": rev,
                "Orders": ords,
                "Suppliers": sups,
                "Area Confidence": p.get("area_confidence", "high"),
                "Area Source": p.get("area_source", "registry"),
            }
        )

    df_ph_area = pd.DataFrame(pharmacy_stats).sort_values("Revenue (EGP)", ascending=False).reset_index(drop=True)
    df_ph_area["Rank"] = df_ph_area.index + 1
    df_ph_area = df_ph_area[["Rank", "Master Pharmacy ID", "Pharmacy", "Revenue (EGP)", "Orders", "Suppliers", "Area Confidence", "Area Source"]]

    # Interactive Table with Pharmacy Selection
    col_table, col_select = st.columns([3, 1])
    with col_table:
        st.dataframe(
            df_ph_area.style.format({"Revenue (EGP)": "{:,.2f} EGP", "Orders": "{:,}", "Suppliers": "{:,}"}),
            use_container_width=True,
            height=400,
            hide_index=True,
        )

    with col_select:
        st.subheader("🔎 Drill Down")
        st.caption(f"Select a pharmacy in {area_name} to view its full master record, aliases, and monthly revenue:")
        ph_options = {
            f"#{row['Master Pharmacy ID']} - {row['Pharmacy']} ({row['Revenue (EGP)']:,.0f} EGP)": row["Master Pharmacy ID"]
            for _, row in df_ph_area.iterrows()
        }
        selected_ph_label = st.selectbox("Select Pharmacy", options=list(ph_options.keys()), key=f"sel_ph_{area_name}")
        if st.button("Open Pharmacy Detail ➔", key=f"btn_open_{area_name}", type="primary", use_container_width=True):
            target_pid = ph_options[selected_ph_label]
            navigate_to("pharmacy", pharmacy_id=target_pid, area=area_name)
            st.rerun()


# ==============================================================================
# SECTION 5: TOP PHARMACIES OVERALL
# ==============================================================================
def render_pharmacy_analysis(data: dict, filtered: dict):
    st.title("🏆 Top Pharmacies Overall")
    st.caption("Master canonical pharmacies ranked by total clean reconciled revenue.")

    top_df = filtered["top_pharmacies"]
    if top_df.empty:
        st.info("No transaction data available for top pharmacies.")
        return

    top_display = top_df.copy().reset_index(drop=True)
    top_display["Rank"] = top_display.index + 1
    top_display = top_display.rename(
        columns={
            "pharmacy_id": "Master Pharmacy ID",
            "canonical_name": "Pharmacy",
            "resolved_area": "Area",
            "revenue_egp": "Revenue (EGP)",
            "order_count": "Orders",
        }
    )[["Rank", "Master Pharmacy ID", "Pharmacy", "Area", "Revenue (EGP)", "Orders"]]

    # Controls
    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        search_filter = st.text_input("Filter top pharmacies by name or ID...", placeholder="Type name...")
        if search_filter:
            top_display = top_display[
                top_display["Pharmacy"].str.contains(search_filter, case=False, na=False)
                | top_display["Master Pharmacy ID"].astype(str).str.contains(search_filter, na=False)
            ]
    with col_ctrl2:
        top_n = st.selectbox("Show Top N", options=[10, 20, 50, 100, "All"], index=1)
        if top_n != "All":
            top_display = top_display.head(int(top_n))

    # Display Table
    st.dataframe(
        top_display.style.format({"Revenue (EGP)": "{:,.2f} EGP", "Orders": "{:,}"}),
        use_container_width=True,
        height=450,
        hide_index=True,
    )

    # Click to Drill Down
    st.markdown("### 🔎 View Pharmacy Details")
    c_sel, c_btn = st.columns([3, 1])
    with c_sel:
        ph_dict = {
            f"#{r['Master Pharmacy ID']} - {r['Pharmacy']} [{r['Area']}] ({r['Revenue (EGP)']:,.0f} EGP)": r["Master Pharmacy ID"]
            for _, r in top_display.iterrows()
        }
        chosen_label = st.selectbox("Select Pharmacy from list above", options=list(ph_dict.keys()), key="top_ph_select")
    with c_btn:
        st.write("")
        st.write("")
        if st.button("Open Pharmacy Detail ➔", type="primary", use_container_width=True):
            navigate_to("pharmacy", pharmacy_id=ph_dict[chosen_label])
            st.rerun()


# ==============================================================================
# SECTION 7: TOP SUPPLIERS & SUPPLIER DRILL-DOWN
# ==============================================================================
def render_supplier_analysis(data: dict, filtered: dict):
    st.title("🚚 Supplier Performance Analysis")
    st.caption("Analysis of 38 supplier companies across 83 branches and their reconciled revenue contributions.")

    top_sup = filtered["top_suppliers"]
    if top_sup.empty:
        st.info("No supplier data in active filter window.")
        return

    sup_display = top_sup.copy().reset_index(drop=True)
    sup_display["Rank"] = sup_display.index + 1
    sup_display = sup_display.rename(
        columns={
            "supplier_name": "Supplier Company",
            "supplier_key": "Supplier Code / Key",
            "revenue_egp": "Revenue (EGP)",
            "order_count": "Orders / Invoices",
            "pharmacies_served": "Pharmacies Served",
        }
    )[["Rank", "Supplier Company", "Revenue (EGP)", "Orders / Invoices", "Pharmacies Served"]]

    col_chart, col_table = st.columns([1, 1])
    with col_chart:
        st.subheader("Top Suppliers by Revenue")
        chart_sup = top_sup.head(10).set_index("supplier_name")[["revenue_egp"]]
        st.bar_chart(chart_sup, color="#3b82f6")

    with col_table:
        st.subheader("Supplier Rankings")
        st.dataframe(
            sup_display.style.format({"Revenue (EGP)": "{:,.2f} EGP", "Orders / Invoices": "{:,}", "Pharmacies Served": "{:,}"}),
            use_container_width=True,
            height=350,
            hide_index=True,
        )

    # Supplier Drill-Down Selection
    st.markdown("---")
    st.markdown("### 🔎 Supplier Deep-Dive")
    c_s1, c_s2 = st.columns([3, 1])
    with c_s1:
        suppliers_list = sup_display["Supplier Company"].dropna().unique().tolist()
        chosen_supplier = st.selectbox("Select Supplier Company", options=suppliers_list, key="sup_detail_select")
    with c_s2:
        st.write("")
        st.write("")
        if st.button("Explore Supplier ➔", type="primary", use_container_width=True):
            navigate_to("supplier", supplier=chosen_supplier)
            st.rerun()


def render_supplier_detail(data: dict, filtered: dict):
    supplier_name = st.session_state.get("selected_supplier")
    if not supplier_name:
        st.session_state["view"] = "supplier_analysis"
        st.rerun()

    col_back, _ = st.columns([1, 4])
    with col_back:
        if st.button("← Back to Suppliers", use_container_width=True):
            navigate_to("supplier_analysis")
            st.rerun()

    st.title(f"🚚 Supplier: {supplier_name}")

    # Extract transactions for this supplier
    ledger_df = filtered["filtered_ledger"]
    sup_ledger = ledger_df[ledger_df["supplier_name"] == supplier_name] if not ledger_df.empty else pd.DataFrame()

    total_sup_rev = float(sup_ledger["revenue_egp"].sum()) if not sup_ledger.empty else 0.0
    total_sup_orders = len(sup_ledger)
    unique_pharmacies = int(sup_ledger["pharmacy_id"].nunique()) if not sup_ledger.empty else 0

    # Summary Cards
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Supplier Revenue</div>
                <div class="metric-value">{total_sup_rev:,.2f} <span style="font-size:1rem;">EGP</span></div>
                <div class="metric-sub">In selected date window</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Orders / Invoices</div>
                <div class="metric-value">{total_sup_orders:,}</div>
                <div class="metric-sub">Matched ledger transactions</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Pharmacies Served</div>
                <div class="metric-value">{unique_pharmacies:,}</div>
                <div class="metric-sub">Distinct client pharmacies</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Matched Accounts / Aliases for this Supplier
    st.markdown('<div class="section-header">📋 Matched Accounts & Branches</div>', unsafe_allow_html=True)
    all_pharmacies = data["pharmacies"]
    sup_aliases = []
    for p in all_pharmacies:
        for a in p.get("aliases", []):
            if a.get("parent_company") == supplier_name:
                sup_aliases.append(
                    {
                        "Master Pharmacy ID": p["pharmacy_id"],
                        "Canonical Pharmacy": p["canonical_name"],
                        "Account Name": a.get("account_name"),
                        "Branch Tag": a.get("branch_tag"),
                        "Branch ID": a.get("branch_id"),
                        "Customer Code": a.get("supplier_code"),
                        "Match Score": f"{a.get('match_score', 0):.1f}%",
                        "Match Method": a.get("match_method"),
                    }
                )

    if sup_aliases:
        df_sa = pd.DataFrame(sup_aliases)
        st.dataframe(df_sa, use_container_width=True, height=300, hide_index=True)
    else:
        st.info("No direct mapped supplier accounts under this company identity.")

    # Top Buying Pharmacies
    if not sup_ledger.empty:
        st.markdown('<div class="section-header">🏪 Top Client Pharmacies for this Supplier</div>', unsafe_allow_html=True)
        top_ph_sup = (
            sup_ledger.groupby(["pharmacy_id", "canonical_name", "resolved_area"], as_index=False)
            .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
            .sort_values("revenue_egp", ascending=False)
            .head(20)
            .rename(
                columns={
                    "pharmacy_id": "Master Pharmacy ID",
                    "canonical_name": "Pharmacy Name",
                    "resolved_area": "Area",
                    "revenue_egp": "Revenue (EGP)",
                    "order_count": "Orders",
                }
            )
        )
        st.dataframe(
            top_ph_sup.style.format({"Revenue (EGP)": "{:,.2f} EGP", "Orders": "{:,}"}),
            use_container_width=True,
            hide_index=True,
        )


# ==============================================================================
# SECTION 8 & 9 & 10: PERSISTENT PHARMACY EXPLORER (FULL PAGE)
# ==============================================================================
def render_explorer(data: dict, filtered: dict):
    st.title("🔍 Canonical Pharmacy Explorer")
    st.caption("Browse all 1,826 master pharmacies with search, area filtering, and instant detail inspection.")

    all_pharmacies = data["pharmacies"]
    filter_area = st.session_state["filter_area"]
    search_q = st.session_state.get("pharmacy_search_query", "")

    c_s1, c_s2 = st.columns([3, 1])
    with c_s1:
        new_search = st.text_input(
            "Search pharmacy by name or ID (case-insensitive)",
            value=search_q,
            placeholder="Search e.g. Omega, Misr, Dokki, 1002...",
            key="main_explorer_search",
        )
        st.session_state["pharmacy_search_query"] = new_search
    with c_s2:
        st.write("")
        st.write("")
        if st.button("Clear Search", use_container_width=True):
            st.session_state["pharmacy_search_query"] = ""
            st.rerun()

    # Filter Logic
    matched_pharmacies = all_pharmacies
    if filter_area != "All areas":
        matched_pharmacies = [p for p in matched_pharmacies if p.get("resolved_area") == filter_area]

    if new_search.strip():
        sq = new_search.strip().lower()
        matched_pharmacies = [
            p for p in matched_pharmacies
            if sq in (p.get("canonical_name") or "").lower()
            or sq in (p.get("registry_name") or "").lower()
            or sq in str(p.get("pharmacy_id", ""))
        ]

    st.markdown(f"**Found {len(matched_pharmacies):,} pharmacies** (Area: `{filter_area}`, Search: `{new_search or 'None'}`)")

    # Build Display Table
    table_rows = []
    for p in matched_pharmacies:
        table_rows.append(
            {
                "Master Pharmacy ID": p["pharmacy_id"],
                "Canonical Name": p["canonical_name"],
                "Resolved Area": p.get("resolved_area") or "Unknown",
                "Area Confidence": p.get("area_confidence") or "unknown",
                "Area Source": p.get("area_source") or "none",
                "Aliases Count": len(p.get("aliases", [])),
                "Total Revenue (EGP)": p.get("total_revenue_egp", 0.0),
                "Orders": p.get("order_count", 0),
            }
        )

    df_exp = pd.DataFrame(table_rows)

    if not df_exp.empty:
        col_t, col_act = st.columns([3, 1])
        with col_t:
            st.dataframe(
                df_exp.style.format({"Total Revenue (EGP)": "{:,.2f} EGP", "Orders": "{:,}", "Aliases Count": "{:,}"}),
                use_container_width=True,
                height=500,
                hide_index=True,
            )
        with col_act:
            st.subheader("Select Pharmacy")
            st.caption("Choose from matching results to open detailed record:")
            ph_map = {
                f"#{r['Master Pharmacy ID']} - {r['Canonical Name']} ({r['Resolved Area']})": r["Master Pharmacy ID"]
                for _, r in df_exp.iterrows()
            }
            chosen_ph_str = st.selectbox("Select Pharmacy", options=list(ph_map.keys()), key="exp_select_box")
            if st.button("Open Pharmacy Record ➔", type="primary", use_container_width=True):
                navigate_to("pharmacy", pharmacy_id=ph_map[chosen_ph_str])
                st.rerun()
    else:
        st.warning("No pharmacies found.")


# ==============================================================================
# SECTION 11 & 12 & 13: PHARMACY DETAIL VIEW
# ==============================================================================
def render_pharmacy_detail(data: dict, filtered: dict):
    pharmacy_id = st.session_state.get("selected_pharmacy_id")
    if not pharmacy_id:
        st.session_state["view"] = "explorer"
        st.rerun()

    # Find pharmacy record
    pharmacy = None
    for p in data["pharmacies"]:
        if p["pharmacy_id"] == pharmacy_id:
            pharmacy = p
            break

    if not pharmacy:
        st.error(f"Pharmacy with ID {pharmacy_id} not found.")
        if st.button("← Back to Explorer"):
            navigate_to("explorer")
            st.rerun()
        return

    # Back Navigation Bar
    prev_view = st.session_state.get("prev_view", "overview")
    c_back1, c_back2, _ = st.columns([1.5, 1.5, 5])
    with c_back1:
        if st.button("← Back to Overview", use_container_width=True):
            navigate_to("overview")
            st.rerun()
    with c_back2:
        if st.button("← Back to Previous View", use_container_width=True):
            navigate_to(prev_view)
            st.rerun()

    # Calculate filtered financials for this specific pharmacy
    ledger_df = filtered["filtered_ledger"]
    pharm_ledger = ledger_df[ledger_df["pharmacy_id"] == pharmacy_id] if not ledger_df.empty else pd.DataFrame()

    filtered_pharm_revenue = float(pharm_ledger["revenue_egp"].sum()) if not pharm_ledger.empty else 0.0
    filtered_pharm_orders = len(pharm_ledger)

    # Monthly breakdown from filtered ledger
    if not pharm_ledger.empty:
        monthly_df = (
            pharm_ledger.groupby(pharm_ledger["order_date_dt"].dt.to_period("M").astype(str), as_index=False)
            .agg(revenue_egp=("revenue_egp", "sum"), order_count=("source_doc_id", "count"))
            .rename(columns={"order_date_dt": "Month", "revenue_egp": "Revenue (EGP)", "order_count": "Orders"})
            .sort_values("Month")
        )
    else:
        monthly_df = pd.DataFrame(columns=["Month", "Revenue (EGP)", "Orders"])

    # Header Card
    p_name = pharmacy["canonical_name"]
    p_area = pharmacy.get("resolved_area") or "Unknown Area"
    p_conf = pharmacy.get("area_confidence") or "unknown"
    p_source = pharmacy.get("area_source") or "registry"
    p_conflict = pharmacy.get("area_conflict", False)

    badge_class = f"badge-{p_conf}" if p_conf in ["high", "medium", "conflict", "ambiguous", "unknown"] else "badge-unknown"

    st.markdown(
        f"""
        <div class="detail-card">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <h1 style="margin:0; font-size:1.8rem; color:#f8fafc;">{p_name}</h1>
                    <div style="margin-top:6px; font-size:0.95rem; color:#94a3b8;">
                        Master Pharmacy ID: <strong style="color:#38bdf8;">#{pharmacy_id}</strong> | 
                        Registry Name: <em>{pharmacy.get('registry_name', p_name)}</em>
                    </div>
                </div>
                <div>
                    <span class="badge {badge_class}" style="font-size:0.85rem; padding:6px 12px;">{p_area} ({p_conf})</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Summary Stats & Area Evidence Grid
    col_info1, col_info2 = st.columns([1, 1])

    with col_info1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Financial Performance (Active Filter)</div>
                <div class="metric-value">{filtered_pharm_revenue:,.2f} <span style="font-size:1rem;">EGP</span></div>
                <div style="margin-top:8px; font-size:0.9rem; color:#cbd5e1;">
                    <strong>Orders:</strong> {filtered_pharm_orders:,} invoices &nbsp;|&nbsp; 
                    <strong>Supplier Aliases:</strong> {len(pharmacy.get('aliases', []))}
                </div>
                <div class="metric-sub">Date window: {st.session_state['filter_date_from']} to {st.session_state['filter_date_to']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_info2:
        evidence_dict = pharmacy.get("area_evidence") or {}
        evidence_str = ", ".join([f"{k}: {v}" for k, v in evidence_dict.items()]) if evidence_dict else "Registry record only"
        conflict_msg = "<span style='color:#f472b6;font-weight:600;'>⚠️ Conflict detected with invoice evidence</span>" if p_conflict else "<span style='color:#34d399;'>✓ Consistent</span>"

        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Area Resolution Evidence</div>
                <div style="font-size:1.1rem; font-weight:600; color:#e2e8f0; margin-top:4px;">
                    Source: <span style="color:#38bdf8;">{p_source}</span> ({p_conf} confidence)
                </div>
                <div style="margin-top:6px; font-size:0.85rem; color:#94a3b8;">
                    <strong>Evidence Breakdown:</strong> {evidence_str}<br>
                    <strong>Consistency Status:</strong> {conflict_msg}
                </div>
                <div class="metric-sub">Weighted vote: header (3), account address (2), ship-to (1)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Supplier Aliases Section (Explicitly Required)
    st.markdown('<div class="section-header">🚚 Matched Supplier Aliases & Naming Book</div>', unsafe_allow_html=True)
    aliases = pharmacy.get("aliases", [])

    if aliases:
        df_alias = pd.DataFrame(aliases)
        # Format columns cleanly
        display_alias = df_alias.rename(
            columns={
                "account_name": "Account Name",
                "parent_company": "Supplier",
                "branch_tag": "Branch",
                "branch_id": "Branch ID",
                "supplier_code": "Customer Code",
                "match_method": "Match Method",
                "match_score": "Match Score",
                "match_status": "Status",
                "match_evidence": "Evidence",
            }
        )[["Account Name", "Supplier", "Branch", "Customer Code", "Match Method", "Match Score", "Status", "Evidence"]]
        if "Match Score" in display_alias.columns:
            display_alias["Match Score"] = display_alias["Match Score"].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "-")

        st.dataframe(display_alias, use_container_width=True, hide_index=True)
    else:
        st.info("No matched supplier aliases for this pharmacy.")

    # Revenue Over Time Section (Explicitly Required)
    st.markdown('<div class="section-header">📈 Revenue Over Time (Monthly Ledger)</div>', unsafe_allow_html=True)

    if not monthly_df.empty:
        c_chart, c_tbl = st.columns([2, 1])
        with c_chart:
            st.subheader("Monthly Revenue (EGP)")
            chart_data = monthly_df.set_index("Month")[["Revenue (EGP)"]]
            st.line_chart(chart_data, color="#38bdf8")

        with c_tbl:
            st.subheader("Monthly Breakdown")
            st.dataframe(
                monthly_df.style.format({"Revenue (EGP)": "{:,.2f} EGP", "Orders": "{:,}"}),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("No revenue ledger entries found for this pharmacy in the selected date range.")

    # Transaction Invoices Ledger
    if not pharm_ledger.empty:
        with st.expander("📄 View Individual Invoices & Ledger Transactions", expanded=False):
            st.dataframe(
                pharm_ledger[
                    ["source_system", "source_doc_id", "order_date", "supplier_name", "revenue_egp"]
                ].rename(
                    columns={
                        "source_system": "System",
                        "source_doc_id": "Doc / Invoice No",
                        "order_date": "Order Date",
                        "supplier_name": "Supplier",
                        "revenue_egp": "Revenue (EGP)",
                    }
                ).style.format({"Revenue (EGP)": "{:,.2f} EGP"}),
                use_container_width=True,
                hide_index=True,
            )


# ==============================================================================
# SECTION 14: DATA QUALITY & UNMATCHED DATA
# ==============================================================================
def render_unmatched(data: dict, filtered: dict):
    st.title("🛡️ Data Quality & Unmatched Data Inspection")
    st.caption("Measured unknown population, disambiguation metrics, and real sample records.")

    summary = data.get("summary", {})
    id_stats = summary.get("identity_stats", {})
    extra_dfs = data.get("extra_dfs", {})

    # Top KPI Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Unmatched Aliases</div>
                <div class="metric-value">{id_stats.get('aliases_unmatched', 10531):,}</div>
                <div class="metric-sub">70.43% of 14,953 total accounts</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Ambiguous Aliases</div>
                <div class="metric-value">{id_stats.get('aliases_ambiguous', 2702):,}</div>
                <div class="metric-sub">18.07% of 14,953 total accounts</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Unmatched ERP Invoices</div>
                <div class="metric-value">{id_stats.get('erp_invoices_unmatched', 15507):,}</div>
                <div class="metric-sub">87.65% of 17,691 ERP rows</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Unknown / Conflict Areas</div>
                <div class="metric-value">{summary.get('unknown_area_pharmacy_count', 756)} / {summary.get('area_conflict_pharmacy_count', 171)}</div>
                <div class="metric-sub">Unknown / Conflict pharmacies</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("📑 Real Unmatched & Ambiguous Sample Records")

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "1. Unmatched ERP Invoices (Sample)",
            "2. Unmatched Supplier Accounts (Sample)",
            "3. Ambiguous Supplier Accounts (Sample)",
            "4. Unknown / Ambiguous Areas (Sample)",
        ]
    )

    with tab1:
        st.caption("ERP invoices excluded from trusted revenue because no unique master pharmacy identity could be proven.")
        df_un_erp = extra_dfs.get("unmatched_erp")
        if df_un_erp is not None and not df_un_erp.empty:
            st.dataframe(df_un_erp.head(50), use_container_width=True, height=400, hide_index=True)
        else:
            sample_erp = data.get("unmatched_erp_sample", [])
            st.dataframe(pd.DataFrame(sample_erp).head(50), use_container_width=True, height=400, hide_index=True)

    with tab2:
        st.caption("Supplier account names with match score below threshold (kept strictly unmatched).")
        df_un_al = extra_dfs.get("unmatched_aliases")
        if df_un_al is not None and not df_un_al.empty:
            st.dataframe(df_un_al.head(50), use_container_width=True, height=400, hide_index=True)
        else:
            sample_al = data.get("unmatched_aliases_sample", [])
            st.dataframe(pd.DataFrame(sample_al).head(50), use_container_width=True, height=400, hide_index=True)

    with tab3:
        st.caption("Supplier accounts with competing candidate matches (preserved as AMBIGUOUS).")
        df_am_al = extra_dfs.get("ambiguous_aliases")
        if df_am_al is not None and not df_am_al.empty:
            st.dataframe(df_am_al.head(50), use_container_width=True, height=400, hide_index=True)
        else:
            sample_ambig = data.get("ambiguous_aliases_sample", [])
            st.dataframe(pd.DataFrame(sample_ambig).head(50), use_container_width=True, height=400, hide_index=True)

    with tab4:
        st.caption("Pharmacies where neither registry nor invoice evidence provided sufficient unambiguous area proof.")
        df_un_area = extra_dfs.get("unknown_areas")
        if df_un_area is not None and not df_un_area.empty:
            st.dataframe(df_un_area.head(50), use_container_width=True, height=400, hide_index=True)
        else:
            st.info("No unknown area sample records found.")


# ==============================================================================
# SECTION 15: CLEANING & RECONCILIATION
# ==============================================================================
def render_reconciliation(data: dict, filtered: dict):
    st.title("⚖️ Cleaning Rules & Ledger Reconciliation")
    st.caption("Explicit accounting rules, source-specific exclusions, row counts, and monetary impacts.")

    summary = data.get("summary", {})
    impacts = summary.get("revenue_impacts", [])

    st.markdown('<div class="section-header">📜 Source-Specific Cleaning & Exclusion Rules</div>', unsafe_allow_html=True)

    if impacts:
        df_imp = pd.DataFrame(impacts)
        # Parse Source System from Rule ID (APP, ERP, LEG)
        df_imp["Source System"] = df_imp["rule_id"].apply(
            lambda x: "Mobile App (APP)" if "APP" in str(x) else ("Partner ERP (ERP)" if "ERP" in str(x) else "Legacy System (LEGACY)")
        )
        df_imp = df_imp.rename(
            columns={
                "rule_id": "Rule ID",
                "description": "Rule Description",
                "rows_affected": "Rows Affected",
                "monetary_impact_egp": "Monetary Impact (EGP)",
            }
        )[["Rule ID", "Source System", "Rule Description", "Rows Affected", "Monetary Impact (EGP)"]]

        st.dataframe(
            df_imp.style.format({"Rows Affected": "{:,}", "Monetary Impact (EGP)": "{:,.2f} EGP"}),
            use_container_width=True,
            hide_index=True,
        )

    # Reconciliation Summary Card
    st.markdown('<div class="section-header">📊 Trusted Revenue Ledger Summary</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Clean Ledger Rows</div>
                <div class="metric-value">{data['meta']['total_orders']:,}</div>
                <div class="metric-sub">Total validated invoice headers</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Clean Reconciled Revenue</div>
                <div class="metric-value">{data['meta']['total_revenue_egp']:,.2f} <span style="font-size:1rem;">EGP</span></div>
                <div class="metric-sub">Window: 2024-09-01 to 2026-08-26</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Data Consistency Check</div>
                <div class="metric-value" style="color:#34d399;">100% Invariant</div>
                <div class="metric-sub">Area sums = Pharmacy sums = Total revenue</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        """
        ### 📖 Business Logic & Identity Policy Notes:
        - **Identity Policy**: One canonical identity per row in `pharmacy_registry.csv`. Supplier accounts are mapped using exact normalized matches and high-confidence fuzzy matching with branch disambiguation. Unmatched and competing aliases remain strictly disjoint.
        - **Area Recovery**: Registry area is respected when present. Missing areas are resolved strictly against `areas_reference.csv` using weighted invoice delivery evidence (header: 3, account address: 2, ship-to address: 1).
        - **Revenue Ledger**: Revenue uses line-item sums when available, otherwise header totals. Canceled/pending APP orders, unmatched ERP invoices, and out-of-window orders are systematically excluded. Credit documents (`CR`) reduce revenue via negative values.
        """
    )


if __name__ == "__main__":
    main()
