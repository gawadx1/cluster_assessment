# Task 2: Field Representative Tomorrow's Dispatch Plan

## Overview

This repository contains the complete, deterministic, and 100% offline dispatch planning engine and interactive route viewer for **Task 2**. 

Four field sales representatives are permanently assigned to four metropolitan districts in Egypt (Smouha, Nasr City, Faisal, Mohandessin). Tomorrow morning, each representative must visit **16 assigned pharmacy stops** defined in `route_plan_tomorrow.csv`.

Every timing in this solution—including visit durations, inter-pharmacy travel times, morning departure from centroid base, and pharmacy ordering rhythms—is derived from historical data across seven dataset files rather than guesswork or external APIs.

---

## Quick Start & Verification

### 1. Launch the Interactive Web Viewer
Double-click `run.bat` inside the `task2/` folder or run:
```bash
cd task2
run.bat
```
This automatically verifies the pipeline and opens the local route viewer at `http://localhost:8502`.

### 2. Regenerate All Plans Deterministically via CLI
To re-run the entire analysis pipeline and regenerate all JSON plans, CSV exports, quality audits, and mathematical proofs:
```bash
python task2/generate_plans.py
```

### 3. Run the Automated Test Suite
To run the automated test suite covering all 18 validation criteria:
```bash
pytest -v task2/tests/test_pipeline.py
```

---

## Key Output Deliverables

All generated deliverables are stored deterministically in `task2/plans/`:
- `plans_all_areas.json`: Master structured JSON containing full chronological itineraries, segment details, KPIs, arithmetic proofs, dispatcher actions, and single-stop failure evaluations for all 4 areas.
- `plan_smouha.csv`: 16-stop finalized itinerary for Rep 1 (Smouha).
- `plan_nasr_city.csv`: 16-stop finalized itinerary for Rep 2 (Nasr City).
- `plan_faisal.csv`: 16-stop finalized itinerary for Rep 3 (Faisal).
- `plan_mohandessin.csv`: 16-stop finalized itinerary for Rep 4 (Mohandessin).
- `data_quality_report.json`: Quantified quality metrics and record validity statistics.
- `audit_proof.txt`: Printed arithmetic proof showing every area's total timeline fits comfortably before the 17:40 cutoff.

---

## Data Sources & Integrity Findings

The pipeline ingests and unifies 7 CSV datasets from `task2/dataset/`:

| Dataset File | Total Rows | Clean / Trustworthy Rows | Key Quality Observations & Cleaning Actions |
|---|---|---|---|
| `areas_reference.csv` | 4 | 4 | Map centers / centroids for Smouha, Nasr City, Faisal, Mohandessin. |
| `pharmacy_registry.csv` | 1,826 | 1,826 | Pharmacy coordinates (`lat`, `lon`), status codes (`0`, `1`, `2`), sales rep IDs. |
| `field_visit_log.csv` | 12,083 | 11,347 | **736 missing `departed_at`** values and **138 cancelled visits** (`cancelled_flag = 1`) detected and filtered out. 11,347 visits confirmed with valid, positive durations. |
| `invoices_app.csv` | 8,943 | 8,943 | Timestamps normalized from UTC to local Egypt time (UTC+2) to identify order placement hours. |
| `invoices_legacy.csv` | 4,185 | 4,185 | Account references parsed via regex (`P:<pharmacy_id>`) and `doc_time` converted to local minutes. |
| `invoices_erp.csv` | 17,691 | 7,436 matched | Entity resolution performed via tokenized inverted index across pharmacy names and inferred district areas. Match rate: 42.0%. |
| `route_plan_tomorrow.csv` | 64 | 64 | Exactly 16 requested stops per area across Priorities P1, P2, and P3. |

---

## Statistical Modeling Methodologies

### 1. Stop Duration Model
- Historical visit durations ($T_{\text{visit}} = \text{departed\_at} - \text{arrived\_at}$) from non-cancelled, complete records range from 7.0 to 41.0 minutes (median: 16.0 minutes).
- **Per-Pharmacy Estimation:** When a pharmacy has $\ge 2$ valid historical visits, its estimated stop duration is set to its historical median.
- **Thin History Fallback:** For pharmacies with $< 2$ historical visits, the model refuses to invent arbitrary numbers and falls back to the empirical median duration of that specific district:
  - Smouha: `16.0 min`
  - Nasr City: `18.0 min`
  - Faisal: `15.0 min`
  - Mohandessin: `16.0 min`

### 2. Travel Time Model
- Consecutive historical visits ($V_i, V_{i+1}$ on the same date by the same rep where neither was cancelled) were reconstructed across 9,903 historical transitions.
- Observed inter-pharmacy drive times strictly range between 4.0 and 18.0 minutes (mean: 6.87 min, median: 7.0 min).
- **Pairwise Direct Transitions:** When a direct historical movement $(P_A \to P_B)$ or reverse $(P_B \to P_A)$ exists in history, its historical median travel time is utilized.
- **Empirical District Model:** For unseen transitions, travel time is derived using the empirical district progression model calibrated from historical trips:
  $$T_{\text{drive}} = 3.0 + \left(\frac{D_{\text{km}}}{S_{\text{urban}}}\right) \times 60.0$$
  where $3.0\text{ min}$ represents parking/maneuvering overhead and $S_{\text{urban}}$ is the measured urban traffic speed for that district (clamped between 8.0 and 22.0 km/h; inter-stop times bounded between 4.0m and 18.0m).
- **Centroid Base Departures & Returns:** Historical Stop 1 arrivals indicate reps depart the centroid base at 09:00 (540 min) and arrive at their first stop between 09:12 and 09:28 (median travel time ~20 min).

### 3. Pharmacy Visit-Timing Rhythm (Invoice Integration)
- Across all three invoice systems (App, Legacy, ERP), a total of **20,564 invoice timestamps** were compiled across 1,777 unique pharmacies.
- For each pharmacy, ordering distributions were analyzed (earliest, 25th percentile, median, 75th percentile, latest).
- **Target Visit Window:** The representative is routed to arrive *before* the pharmacy's historical ordering peak ($T_{\text{arr}} \le T_{\text{median\_order}}$) to engage the pharmacist before orders close.

---

## Route Optimization Methodology

The optimizer uses a deterministic constructive heuristic followed by a 2-Opt and Relocate local search to solve the multi-objective dispatch problem:
1. **Minimizing Total Transit Time:** Reduces wasteful driving.
2. **Maximizing Rhythm Alignment:** Penalizes arrivals that occur after the pharmacy's historical ordering peak, weighted heavily by priority ($\text{P1} \times 3.0, \text{P2} \times 2.0, \text{P3} \times 1.0$).
3. **Hard Constraint:** Complete itinerary, including 25-minute lunch break, must return to base by $\le 17:40$ (1060 min).

---

## Mathematical Proof of Day Fit

Every itinerary is verified through code-generated arithmetic:

$$\text{Start (09:00)} + \sum \text{Drives} + \sum \text{Stays} + \text{Lunch (25m)} + \text{Return Drive} = \text{End Time} \le \text{17:40 (1060m)}$$

### Summary by Area

| Area | Sales Rep | Start Time | Total Driving | Total Stays | Lunch | Final Return | Spare Margin | Status |
|---|---|---|---|---|---|---|---|---|
| **Smouha** | Rep 1 | `09:00` (540.0m) | 146.7 min | 266.0 min | 25.0 min | `16:17` (977.7m) | **+82.3 min** | PASSED |
| **Nasr City** | Rep 2 | `09:00` (540.0m) | 133.4 min | 288.0 min | 25.0 min | `16:26` (986.4m) | **+73.6 min** | PASSED |
| **Faisal** | Rep 3 | `09:00` (540.0m) | 145.4 min | 251.0 min | 25.0 min | `16:01` (961.4m) | **+98.6 min** | PASSED |
| **Mohandessin** | Rep 4 | `09:00` (540.0m) | 134.5 min | 271.0 min | 25.0 min | `16:10` (970.5m) | **+89.5 min** | PASSED |

---

## Dispatcher Judgment & Abnormal Stop Handling

During dataset preparation, exactly **8 stops** in `route_plan_tomorrow.csv` were identified with non-zero registry status codes (2 stops per area):
- **Status Code 1 (Digital Active / Zero Physical Visits):** Pharmacies that actively order via the App/ERP/Legacy but have never received physical field rep visits.
  - *Policy:* Retain in tomorrow's route. Benchmark visit duration to the district median. Rep is tasked with validating account details and in-person onboarding.
- **Status Code 2 (Registry Dormant / Zero Physical Visits):** Pharmacies flagged inactive in registry but assigned for tomorrow's schedule.
  - *Policy:* Retain in tomorrow's route. Rep conducts an on-site verification audit to inspect store status and re-engage the customer.

---

## Single-Stop Failure Analysis (Worst-Case Stress Test)

A quantitative stress test simulated an unforeseen **45-minute delay / disruption** at each of the 16 stops for all 4 areas. The damage score accounts for stop priority, downstream Priority 1 stops jeopardized, and schedule overruns:

| Area | Most Damaging Stop Failure | Priority | Damage Score | Operational Impact |
|---|---|---|---|---|
| **Smouha** | Stop 10: Alpha Pharma - Zayed | P1 | `60.0` | Rep returns at 17:02 (+38m before cutoff). |
| **Nasr City** | Stop 3: Pharma Plus - Obour | P1 | `120.0` | Rep returns at 17:11; delays 4 downstream P1 stops. |
| **Faisal** | Stop 1: Care 24 Seven - Faisal | P1 | `150.0` | Rep returns at 16:46; delays 6 downstream P1 stops. |
| **Mohandessin** | Stop 1: Union Pharm - Haram | P1 | `165.0` | Rep returns at 16:55; delays 7 downstream P1 stops. |

Even under a 45-minute catastrophic stop delay, **all 4 reps still return to base before the 17:40 cutoff**, proving the resilience of the optimized dispatch schedules.
