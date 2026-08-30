"""
app.py
Streamlit Web Viewer for Task 2: Tomorrow's Dispatch Plan.
Zero external visualization dependencies (pure SVG/HTML rendering via components.v1.html).

Allows the evaluator to:
1. Select any of the four areas / field representatives.
2. Inspect the complete planned day from start to return base.
3. View the visual route map with numbered stops, connected path lines, and start/end centroids.
4. Review the chronological step-by-step itinerary with exact arrival/departure timings.
5. Verify the code-generated arithmetic mathematical proof that the day fits inside the 17:40 cutoff.
6. Inspect dispatcher actions on abnormal status codes.
7. Inspect the critical single-stop failure damage analysis.
8. Explore dataset quality metrics and invoice rhythm distributions.
"""

import os
import sys
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)
sys.path.insert(0, os.path.join(base_dir, "src"))

st.set_page_config(
    page_title="Task 2 - Field Rep Dispatch Plan",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 26px;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 4px;
    }
    .sub-header {
        font-size: 15px;
        color: #64748B;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 14px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .proof-card {
        background-color: #F0FDF4;
        border: 1px solid #BBF7D0;
        border-left: 5px solid #22C55E;
        border-radius: 8px;
        padding: 16px;
        font-family: monospace;
        font-size: 15px;
        color: #166534;
        margin: 15px 0;
    }
    .alert-card {
        background-color: #FEF2F2;
        border: 1px solid #FECACA;
        border-left: 5px solid #EF4444;
        border-radius: 8px;
        padding: 14px;
        color: #991B1B;
        margin: 12px 0;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_plans_data():
    """Loads precomputed plans or runs pipeline if missing."""
    plans_file = os.path.join(base_dir, "plans", "plans_all_areas.json")
    dq_file = os.path.join(base_dir, "plans", "data_quality_report.json")

    if not os.path.exists(plans_file) or not os.path.exists(dq_file):
        try:
            from generate_plans import run_pipeline
            run_pipeline()
        except Exception as e:
            st.error(f"Error generating plans: {e}")

    with open(plans_file, "r", encoding="utf-8") as f:
        plans = json.load(f)
    with open(dq_file, "r", encoding="utf-8") as f:
        quality_metrics = json.load(f)

    return plans, quality_metrics


plans, quality_metrics = load_plans_data()


def render_svg_route_map_html(plan: dict, width: int = 960, height: int = 540) -> str:
    """
    Renders an interactive, crisp SVG route map wrapped in isolated HTML for iframe display.
    """
    stops = plan['stops_summary']
    c_lat = plan['centroid_lat']
    c_lon = plan['centroid_lon']

    all_lats = [c_lat] + [s['lat'] for s in stops]
    all_lons = [c_lon] + [s['lon'] for s in stops]

    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lon, max_lon = min(all_lons), max(all_lons)

    # Margins / padding
    d_lat = max(max_lat - min_lat, 0.005)
    d_lon = max(max_lon - min_lon, 0.005)
    pad_lat = d_lat * 0.15
    pad_lon = d_lon * 0.15

    min_lat -= pad_lat
    max_lat += pad_lat
    min_lon -= pad_lon
    max_lon += pad_lon

    def to_xy(lat, lon):
        x = 60 + (lon - min_lon) / (max_lon - min_lon) * (width - 120)
        y = height - 50 - (lat - min_lat) / (max_lat - min_lat) * (height - 100)
        return round(x, 1), round(y, 1)

    bx, by = to_xy(c_lat, c_lon)

    # Build stop points
    stop_points = []
    for s in stops:
        sx, sy = to_xy(s['lat'], s['lon'])
        stop_points.append((sx, sy, s))

    # All sequence points: Base -> Stop 1 -> ... -> Stop 16 -> Base
    all_coords = [(bx, by)] + [(pt[0], pt[1]) for pt in stop_points] + [(bx, by)]

    svg_parts = []
    svg_parts.append(f'''
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body {{ margin:0; padding:0; background:transparent; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .svg-container {{ display: flex; justify-content: center; align-items: center; width: 100%; }}
        svg {{ max-width: 100%; height: auto; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .stop-node:hover circle {{ transform: scale(1.15); transform-origin: center; transition: 0.15s ease; }}
    </style>
    </head>
    <body>
    <div class="svg-container">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="{height}" style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px;">
    ''')

    # Definitions for arrows and drop shadows
    svg_parts.append("""
    <defs>
        <marker id="arrow-blue" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2563EB" />
        </marker>
        <marker id="arrow-red" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#DC2626" />
        </marker>
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="1" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.15"/>
        </filter>
    </defs>
    """)

    # Grid background lines
    for gx in range(80, width - 50, 100):
        svg_parts.append(f'<line x1="{gx}" y1="20" x2="{gx}" y2="{height-20}" stroke="#E2E8F0" stroke-width="1" stroke-dasharray="3,3" />')
    for gy in range(60, height - 40, 80):
        svg_parts.append(f'<line x1="30" y1="{gy}" x2="{width-30}" y2="{gy}" stroke="#E2E8F0" stroke-width="1" stroke-dasharray="3,3" />')

    # Draw Route Path Lines
    for i in range(len(all_coords) - 1):
        x1, y1 = all_coords[i]
        x2, y2 = all_coords[i + 1]
        is_departure = (i == 0)
        is_return = (i == len(all_coords) - 2)
        is_lunch = (i == 8)

        if is_departure or is_return:
            color = "#DC2626"
            stroke_style = 'stroke-dasharray="6,3"'
            marker = 'marker-mid="url(#arrow-red)"'
        elif is_lunch:
            color = "#D97706"
            stroke_style = 'stroke-dasharray="4,4"'
            marker = 'marker-mid="url(#arrow-blue)"'
        else:
            color = "#2563EB"
            stroke_style = ''
            marker = 'marker-mid="url(#arrow-blue)"'

        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0

        svg_parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5" {stroke_style} opacity="0.85" />')
        svg_parts.append(f'<circle cx="{mx}" cy="{my}" r="1" {marker} />')

    # Draw Centroid Base Marker
    svg_parts.append(f'''
    <g filter="url(#shadow)">
        <polygon points="{bx},{by-18} {bx+14},{by+12} {bx-14},{by+12}" fill="#16A34A" stroke="#FFFFFF" stroke-width="2"/>
        <circle cx="{bx}" cy="{by}" r="6" fill="#FFFFFF"/>
        <text x="{bx}" y="{by-22}" text-anchor="middle" font-size="11" font-weight="bold" fill="#166534">BASE (09:00 / Return)</text>
    </g>
    ''')

    # Draw Pharmacy Stop Nodes
    prio_fill = {1: '#EF4444', 2: '#F59E0B', 3: '#3B82F6'}
    for sx, sy, s in stop_points:
        idx = s['stop_index']
        prio = s['priority']
        fill = prio_fill.get(prio, '#64748B')
        name_short = s['name'].split('-')[0].strip()[:14]
        arr_time = s['arrival_time']

        svg_parts.append(f'''
        <g class="stop-node" filter="url(#shadow)">
            <circle cx="{sx}" cy="{sy}" r="13" fill="{fill}" stroke="#FFFFFF" stroke-width="2"/>
            <text x="{sx}" y="{sy+4}" text-anchor="middle" font-size="10" font-weight="bold" fill="#FFFFFF">{idx}</text>
            <rect x="{sx+16}" y="{sy-14}" width="112" height="26" rx="4" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1" opacity="0.95"/>
            <text x="{sx+20}" y="{sy-2}" font-size="9" font-weight="bold" fill="#1E293B">{idx}. {name_short}</text>
            <text x="{sx+20}" y="{sy+8}" font-size="8" fill="#64748B">Arr: {arr_time} (P{prio})</text>
        </g>
        ''')

    # Legend at top right
    svg_parts.append(f'''
    <g transform="translate({width-235}, 16)">
        <rect x="0" y="0" width="220" height="115" rx="6" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1" opacity="0.96"/>
        <text x="10" y="18" font-size="10" font-weight="bold" fill="#334155">Route Map Legend</text>
        
        <polygon points="18,34 24,44 12,44" fill="#16A34A"/>
        <text x="32" y="42" font-size="9" fill="#1E293B">Centroid Base (Start / End)</text>
        
        <circle cx="18" cy="56" r="6" fill="#EF4444"/>
        <text x="32" y="59" font-size="9" fill="#1E293B">Priority 1 (Urgent Stop)</text>
        
        <circle cx="18" cy="74" r="6" fill="#F59E0B"/>
        <text x="32" y="77" font-size="9" fill="#1E293B">Priority 2 (Standard Stop)</text>
        
        <circle cx="18" cy="92" r="6" fill="#3B82F6"/>
        <text x="32" y="95" font-size="9" fill="#1E293B">Priority 3 (Flexible Stop)</text>
        
        <line x1="12" y1="106" x2="26" y2="106" stroke="#2563EB" stroke-width="2"/>
        <text x="32" y="109" font-size="8.5" fill="#64748B">Transit Drive Trajectory</text>
    </g>
    ''')

    svg_parts.append('''
    </svg>
    </div>
    </body>
    </html>
    ''')
    return "".join(svg_parts)


# ----------------- SIDEBAR -----------------
st.sidebar.image("https://img.icons8.com/color/96/delivery.png", width=64)
st.sidebar.title("Dispatch Navigator")
st.sidebar.markdown("**Task 2: Tomorrow's Dispatch Plan**")

area_options = ["Smouha", "Nasr City", "Faisal", "Mohandessin"]
selected_area = st.sidebar.selectbox("Select Operational Area:", area_options, index=0)

area_rep_names = {
    "Smouha": "Field Rep 1 (Alexandria)",
    "Nasr City": "Field Rep 2 (Cairo)",
    "Faisal": "Field Rep 3 (Giza)",
    "Mohandessin": "Field Rep 4 (Giza)"
}

st.sidebar.info(f"**Assigned Personnel:**\n{area_rep_names.get(selected_area)}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Operational Rules")
st.sidebar.markdown("""
- **Start / End Base:** Area Centroid
- **Working Start:** `09:00 AM`
- **Return Cutoff:** `17:40 PM` (1060 min)
- **Mandatory Lunch:** `25 min` (after Stop 8)
- **Required Stops:** 16 per area
- **Offline / Deterministic:** Yes
""")

# ----------------- MAIN VIEW -----------------
plan = plans[selected_area]

st.markdown(f"<div class='main-header'>📍 Dispatch Plan: {selected_area}</div>", unsafe_allow_html=True)
st.markdown(
    f"<div class='sub-header'>Assigned to <b>{area_rep_names[selected_area]}</b> | "
    f"Base Centroid: ({plan['centroid_lat']:.5f}, {plan['centroid_lon']:.5f}) | "
    f"16 Mandatory Stops</div>",
    unsafe_allow_html=True
)

# Top KPI Metric Row
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric("Working Window", f"{plan['day_start_str']} → {plan['day_end_str']}", f"{plan['total_day_span_min']:.0f} min total")
with kpi2:
    st.metric("Driving Duration", f"{plan['total_travel_time_min']:.1f} min", f"{len(plan['stops_summary'])+1} legs")
with kpi3:
    st.metric("Pharmacy Stays", f"{plan['total_stay_duration_min']:.1f} min", "16 visits")
with kpi4:
    st.metric("Lunch Break", f"{plan['lunch_duration_min']:.0f} min", "Midday (Stop 8)")
with kpi5:
    status_label = "✅ ON-TIME" if plan['fits_before_cutoff'] else "❌ OVERRUN"
    st.metric("17:40 Cutoff Margin", f"+{plan['spare_time_min']:.1f} min", status_label)

# Mathematical Proof Banner
st.markdown("### 🧮 Auditable Mathematical Proof (Day Fit)")
st.markdown(f"""
<div class='proof-card'>
<b>PROVEN ARITHMETIC EQUATION:</b><br>
{plan['arithmetic_equation']}<br>
<b>RESULT:</b> Return at <b>{plan['day_end_str']}</b> leaves <b>+{plan['spare_time_min']:.1f} minutes</b> of safety buffer before the 17:40 cutoff.
</div>
""", unsafe_allow_html=True)

# Tabs for visual route, detailed table, dispatcher analysis, and failure stress-test
tab_route, tab_itinerary, tab_dispatcher, tab_failure, tab_data = st.tabs([
    "🗺️ Visual Route Plan",
    "📋 Step-by-Step Itinerary",
    "🛡️ Dispatcher Judgment & Audits",
    "⚡ Single-Stop Failure Analysis",
    "📊 Data Quality & Evidence"
])

# ----------------- TAB 1: VISUAL ROUTE MAP -----------------
with tab_route:
    st.markdown("#### Planned Geographic Trajectory")
    st.caption("Visual representation of the exact planned sequence from Centroid Base → Stop 1 → ... → Stop 16 → Return Base.")

    svg_html_content = render_svg_route_map_html(plan)
    components.html(svg_html_content, height=560, scrolling=False)

# ----------------- TAB 2: STEP-BY-STEP ITINERARY -----------------
with tab_itinerary:
    st.markdown("#### Chronological Itinerary & Stop Timings")
    st.caption("Complete code-generated arithmetic itinerary detailing every leg, arrival, duration, and departure.")

    display_rows = []
    for item in plan['itinerary']:
        stype = item['segment_type']
        if stype == 'drive':
            desc = f"🚗 {item['description']}"
            prio_str = "-"
            arr = item['start_time_str']
            dur = f"{item['duration_min']:.1f} min"
            dep = item['end_time_str']
            tgt = "-"
            status = "In Transit"
        elif stype == 'lunch':
            desc = f"🥪 {item['description']}"
            prio_str = "Break"
            arr = item['start_time_str']
            dur = f"{item['duration_min']:.0f} min"
            dep = item['end_time_str']
            tgt = "-"
            status = "Rest Break"
        elif stype == 'return':
            desc = f"🏁 {item['description']}"
            prio_str = "-"
            arr = item['start_time_str']
            dur = f"{item['duration_min']:.1f} min"
            dep = item['end_time_str']
            tgt = "17:40"
            status = "On-Time Base Return"
        else:
            prio = item['priority']
            desc = f"🏥 Stop {item['stop_index']}: {item['pharmacy_name']} (ID {item['pharmacy_id']})"
            prio_str = f"P{prio}"
            arr = item['start_time_str']
            dur = f"{item['duration_min']:.1f} min"
            dep = item['end_time_str']
            tgt = item['target_arrival_str']
            status = item['rhythm_status']

        display_rows.append({
            "Seg #": item['segment_index'],
            "Timeline Activity": desc,
            "Priority": prio_str,
            "Start / Arr": arr,
            "Duration": dur,
            "Depart / End": dep,
            "Invoice Target": tgt,
            "Rhythm Status / Notes": status
        })

    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, height=520)

# ----------------- TAB 3: DISPATCHER JUDGMENT -----------------
with tab_dispatcher:
    st.markdown("#### Dispatcher Review on Abnormal Status Codes")
    st.caption("Identification and documented handling policies for assigned stops with non-zero registry status codes or dormant history.")

    notes = plan['dispatcher_notes']
    if notes:
        st.markdown(f"**Found {len(notes)} stops requiring explicit dispatcher protocols:**")
        for n in notes:
            st.markdown(f"""
            <div class='metric-card' style='margin-bottom: 10px;'>
                <b style='color:#1E293B; font-size:15px;'>🏥 Pharmacy #{n['pharmacy_id']}: {n['name']}</b> (Registry Status: <code>{n['status_code']}</code>)<br>
                <span style='color:#2563EB; font-weight:600;'>Protocol Action:</span> {n['action_taken']}<br>
                <span style='color:#475569;'><b>Dispatcher Evidence & Rationale:</b> {n['reason']}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("All assigned stops in this area possess active registry status (Code 0).")

    st.markdown("---")
    st.markdown("#### Documented Dispatcher Policies")
    st.markdown("""
    1. **Status Code 1 (Digital/App Active):** Pharmacy submits orders digitally (App/ERP/Legacy) but has 0 physical visit logs. 
       - *Action:* Retained in route sequence. Stop duration benchmarked to empirical area median. Sales rep tasked with digital account onboarding validation.
    2. **Status Code 2 (Registry Flagged / Re-engagement):** Pharmacy flagged dormant in registry but scheduled for tomorrow's dispatch.
       - *Action:* Retained in route sequence. Rep conducts physical status verification audit to re-establish account relationship.
    3. **Thin Visit History Fallback:** When a pharmacy has < 2 historical visit records, the model refuses to invent numbers and cleanly applies the empirical median stay duration for that specific district.
    """)

# ----------------- TAB 4: SINGLE-STOP FAILURE ANALYSIS -----------------
with tab_failure:
    st.markdown("#### Single-Stop Failure Stress Test")
    st.caption("Quantitative impact evaluation per area: which single stop failure (e.g. 45-minute unforeseen delay) causes the greatest disruption to the schedule?")

    worst = plan['critical_failure_analysis']
    st.markdown(f"""
    <div class='alert-card'>
        <h4 style='margin:0 0 6px 0; color:#991B1B;'>⚠️ WORST SINGLE-STOP FAILURE FOR {selected_area.upper()}</h4>
        <b>Most Damaging Stop:</b> Stop #{worst['most_damaging_stop_index']} — <b>{worst['most_damaging_stop_name']}</b> (Priority P{worst['most_damaging_priority']})<br>
        <b>Calculated Damage Score:</b> <code>{worst['max_damage_score']:.1f}</code><br>
        <b>Impact Summary:</b> {worst['impact_summary']}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("##### Full Impact Breakdown Across All 16 Stops")
    fail_df = pd.DataFrame(worst['all_stop_evaluations'])
    fail_table = fail_df[['stop_index', 'name', 'priority', 'delayed_return_str', 'cutoff_breach_min', 'downstream_p1_affected', 'damage_score']].rename(
        columns={
            'stop_index': 'Stop #',
            'name': 'Pharmacy Name',
            'priority': 'Priority',
            'delayed_return_str': 'Delayed Return',
            'cutoff_breach_min': 'Cutoff Breach (min)',
            'downstream_p1_affected': 'Downstream P1 Risks',
            'damage_score': 'Damage Score'
        }
    )
    st.dataframe(fail_table, use_container_width=True, height=400)

# ----------------- TAB 5: DATA QUALITY & EVIDENCE -----------------
with tab_data:
    st.markdown("#### Dataset Inspection, Quality Audits & Cross-System Evidence")
    st.caption("Quantified summary of all 7 input datasets, data-cleaning corrections, and invoice system linkages.")

    q1, q2, q3, q4 = st.columns(4)
    with q1:
        st.metric("Total Visited Logs", f"{quality_metrics['visits_total']:,}", f"{quality_metrics['visits_valid_good']:,} valid trips")
    with q2:
        st.metric("Combined Invoices", f"{quality_metrics['invoices_combined_total']:,}", f"{quality_metrics['invoices_unique_pharmacies']:,} unique pharmacies")
    with q3:
        st.metric("ERP Match Rate", f"{quality_metrics['erp_match_rate']*100:.1f}%", f"{quality_metrics['erp_matched_count']:,} matched")
    with q4:
        st.metric("Registry Pharmacies", f"{quality_metrics['pharmacies_total']:,}", f"{quality_metrics['areas_count']} operational areas")

    st.markdown("##### Cleaned & Filtered Anomalies")
    st.markdown(f"""
    - **Visit Log Inconsistencies:** Out of {quality_metrics['visits_total']:,} historical visit records:
      * `{quality_metrics['visits_missing_departure']}` records had missing `departed_at` timestamps.
      * `{quality_metrics['visits_cancelled']}` records were flagged as cancelled (`cancelled_flag = 1`).
      * Both subsets were measured and excluded from visit duration and travel-time models to prevent corruption.
      * Resulted in `{quality_metrics['visits_valid_good']:,}` trustworthy visit records.
    - **Multi-System Invoices Integrated:**
      * App Invoices: `{quality_metrics['app_invoices_total']:,}` (UTC converted to Egypt Local UTC+2)
      * Legacy Invoices: `{quality_metrics['legacy_invoices_total']:,}` (`P:<id>` regex account linkage)
      * ERP Invoices: `{quality_metrics['erp_invoices_total']:,}` (`{quality_metrics['erp_matched_count']:,}` resolved via tokenized inverted index)
    """)

# Footer
st.markdown("---")
st.markdown("<div style='text-align:center; color:#94A3B8; font-size:12px;'>Task 2 Automated Dispatch Pipeline | Deterministic & Offline Execution | Google Antigravity</div>", unsafe_allow_html=True)
