# Task 1 — Pharmacy Identity and Revenue Explorer (Streamlit Dashboard)

## Overview & Architecture

This solution creates one master record per row in `pharmacy_registry.csv`, then deterministically maps supplier account names and ERP invoice headers to that master identity where sufficient evidence exists. The dashboard is built with **Python + Streamlit** and strictly consumes the generated outputs from the deterministic pipeline (`output/analytics.json` and generated output CSVs/JSONs).

```
RAW CSV DATA (dataset/)
      ↓
Deterministic Task 1 Pipeline (pipeline/)
      ↓
Clean Outputs & Ledger (output/)
      ↓
Streamlit Dashboard (app.py)
      ↓
Interactive Drill-Down & Visual Exploration
```

No numbers or constants are hardcoded in the Streamlit application; all KPIs, rankings, time-series metrics, and partition statistics are dynamically computed from the trusted outputs.

---

## Data Model & Identity Policy

- **Canonical Identity**: `pharmacy_id` (registry ID) serves as the sole master identity for all 1,826 client pharmacies.
- **Supplier Aliases**: 14,953 supplier account aliases across 38 supplier companies and 83 branches are partitioned into disjoint, non-overlapping subsets:
  - **Matched**: 1,720 accounts (11.50%)
  - **Ambiguous**: 2,702 accounts (18.07%)
  - **Unmatched**: 10,531 accounts (70.43%)
- **ERP Invoices**: 17,691 ERP invoice rows are partitioned into:
  - **Matched**: 2,184 rows (12.35%) representing 7,651,074.99 EGP in trusted revenue.
  - **Unmatched**: 15,507 rows (87.65%) representing 54,870,939.19 EGP excluded from trusted revenue.

---

## Area Recovery

- **Registry Priority**: Registry area is respected when present.
- **Evidence-Based Recovery**: For missing registry areas, only high-integrity invoice delivery signals are used (ERP header area: weight 3, ERP account address: weight 2, ERP ship-to address: weight 1).
- **Official Constraints**: Areas are strictly mapped to `areas_reference.csv` (Faisal, Mohandessin, Nasr City, Smouha).
- **Summary**:
  - **Resolved Areas**: 1,069 pharmacies (Smouha: 258, Nasr City: 271, Faisal: 255, Mohandessin: 285).
  - **Recovered from Invoices**: 68 pharmacies.
  - **Registry Conflicts**: 171 pharmacies.
  - **Unknown / Ambiguous Areas**: 757 pharmacies (isolated in `output/unknown_areas.csv` and `output/ambiguous_areas.csv`).

---

## Revenue Reconciliation & Accounting Rules

The trusted revenue ledger has one row per valid invoice header across APP, ERP, and LEGACY systems, totaling **11,773 rows** and **42,056,618.59 EGP** within the window **2024-09-01 through 2026-08-26**:

1. **APP-01**: Excluded canceled and pending-hold APP orders (3,060 rows, 10,911,303.72 EGP).
2. **APP-02**: Excluded out-of-window APP orders (411 rows, 1,477,071.30 EGP).
3. **ERP-01**: Excluded unmatched ERP invoices without proven pharmacy identity (15,507 rows, 55,927,326.98 EGP).
4. **ERP-02**: Excluded out-of-window ERP orders (14 rows, 41,758.52 EGP).
5. **LEG-01**: Credit documents (`CR`) reduce revenue via negative line amounts (78 rows, -16,372.40 EGP).

---

## Streamlit Dashboard Features

The Streamlit dashboard (`app.py`) provides:
1. **Executive Overview**: Real-time KPI summary cards, pipeline identity partitions, ERP row partitions, area resolution status, and revenue breakdown by area.
2. **Area Analysis & Top Pharmacies per Area**: Tabbed deep-dive for Faisal, Mohandessin, Nasr City, and Smouha, listing top pharmacies inside each area with instant click-to-detail navigation.
3. **Top Pharmacies Overall**: Ranked table of top canonical pharmacies with interactive search and detail drill-down.
4. **Supplier Performance Analysis**: Supplier rankings by clean revenue and orders, plus dedicated supplier drill-down showing branches, matched accounts, and top purchasing pharmacies.
5. **Persistent Pharmacy Explorer**: Searchable (case-insensitive) list of all 1,826 canonical pharmacies with live area filtering that never becomes empty.
6. **Pharmacy Detail View**:
   - Master Pharmacy ID, Canonical Name, Registry Name.
   - Area Resolution Box with Confidence badge and weighted vote breakdown.
   - Matched Supplier Aliases table (Account Name, Supplier, Branch, Code, Method, Score, Status).
   - Revenue Over Time: Monthly revenue chart and breakdown table respecting active date filter.
   - Ledger Invoices history table.
7. **Data Quality & Unmatched Data**: Measured quality percentages and real sample records for unmatched ERP invoices, unmatched supplier aliases, ambiguous aliases, and unknown areas.
8. **Cleaning & Reconciliation**: Explicit display of all source cleaning rules, row counts, and monetary impacts.

---

## Running the Dashboard

Double-click `run.bat` or execute:

```bat
task1\run.bat
```

`run.bat` automatically:
1. Validates offline Python dependencies (`pandas`, `rapidfuzz`, `streamlit`).
2. Runs the deterministic pipeline (`run_pipeline.py`).
3. Launches the Streamlit dashboard on `http://localhost:8501`.

To run tests:
```bash
python test_dashboard_logic.py
```
