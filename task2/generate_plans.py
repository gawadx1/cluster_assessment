"""
generate_plans.py
Master execution pipeline for Task 2.
Loads datasets, trains statistical models from historical records,
runs deterministic multi-objective route optimization, and generates:
- JSON master plans (plans_all_areas.json)
- Per-area CSV plans (plan_smouha.csv, plan_nasr_city.csv, plan_faisal.csv, plan_mohandessin.csv)
- Comprehensive Data Quality Audit Report (data_quality_report.json)
- Auditable Mathematical Proof Log (audit_proof.txt)
"""

import os
import sys
import json
from dataclasses import asdict
import pandas as pd

# Add current directory and task2 directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

try:
    from src.data_loader import load_all_data
    from src.historical_models import HistoricalModels
    from src.optimizer import RouteOptimizer
except ImportError:
    from data_loader import load_all_data
    from historical_models import HistoricalModels
    from optimizer import RouteOptimizer


def run_pipeline(output_dir: str = None) -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if output_dir is None:
        output_dir = os.path.join(base_dir, "plans")
    os.makedirs(output_dir, exist_ok=True)

    dataset_dir = os.path.join(base_dir, "dataset")
    print(f"Loading datasets from {dataset_dir}...")
    data = load_all_data(dataset_dir)

    print("Building historical duration, travel-time, and invoice-rhythm models...")
    models = HistoricalModels(data)

    print("Running deterministic multi-objective route optimizer...")
    optimizer = RouteOptimizer(models)
    plans = optimizer.optimize_all_areas()

    # Save Data Quality Report
    dq_path = os.path.join(output_dir, "data_quality_report.json")
    with open(dq_path, "w", encoding="utf-8") as f:
        json.dump(data.quality_metrics, f, indent=2)
    print(f"Saved Data Quality Report -> {dq_path}")

    # Prepare master JSON container
    plans_json_data = {}
    proof_lines = []
    proof_lines.append("=" * 80)
    proof_lines.append("TASK 2 - DISPATCH ROUTE ARITHMETIC AUDIT PROOF")
    proof_lines.append("Constraint: Return to Centroid Base <= 17:40 (1060.0 minutes from midnight)")
    proof_lines.append("=" * 80 + "\n")

    area_filenames = {
        'Smouha': 'plan_smouha.csv',
        'Nasr City': 'plan_nasr_city.csv',
        'Faisal': 'plan_faisal.csv',
        'Mohandessin': 'plan_mohandessin.csv'
    }

    for area_name, plan in plans.items():
        plan_dict = asdict(plan)
        plans_json_data[area_name] = plan_dict

        # Export CSV for this area
        csv_filename = area_filenames.get(area_name, f"plan_{area_name.lower().replace(' ', '_')}.csv")
        csv_path = os.path.join(output_dir, csv_filename)
        df_stops = pd.DataFrame(plan.stops_summary)
        df_stops.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"Saved Area CSV: {csv_filename} ({len(df_stops)} stops)")

        # Format audit proof
        proof_lines.append(f"AREA: {area_name.upper()} (Representative ID: {plan.rep_id})")
        proof_lines.append(f"Map Centroid Base: ({plan.centroid_lat:.6f}, {plan.centroid_lon:.6f})")
        proof_lines.append(f"Planned Stops: {plan.stops_count}")
        proof_lines.append(f"Start Departure: {plan.day_start_str} (Minute {plan.day_start_min:.1f})")
        proof_lines.append(f"Final Return:    {plan.day_end_str} (Minute {plan.day_end_min:.1f})")
        proof_lines.append(f"Return Deadline: {plan.cutoff_time_str} (Minute {plan.cutoff_time_min:.1f})")
        proof_lines.append(f"Spare Margin:    +{plan.spare_time_min:.1f} minutes")
        proof_lines.append(f"Cutoff Check:    {'PASSED (<= 17:40)' if plan.fits_before_cutoff else 'FAILED'}")
        proof_lines.append(f"Exact Equation:  {plan.arithmetic_equation}")
        proof_lines.append("-" * 60)
        proof_lines.append(f"  * Total Driving Travel Time : {plan.total_travel_time_min:.1f} min")
        proof_lines.append(f"  * Total Pharmacy Stay Time   : {plan.total_stay_duration_min:.1f} min")
        proof_lines.append(f"  * Mandatory Lunch Break      : {plan.lunch_duration_min:.1f} min (after Stop 8)")
        proof_lines.append(f"  * Total Working Day Span     : {plan.total_day_span_min:.1f} min")
        proof_lines.append("-" * 60)
        proof_lines.append(f"Critical Failure Analysis:")
        worst = plan.critical_failure_analysis
        proof_lines.append(f"  * Most Damaging Stop Failure : Stop {worst['most_damaging_stop_index']} - {worst['most_damaging_stop_name']} (Priority P{worst['most_damaging_priority']})")
        proof_lines.append(f"  * Damage Score               : {worst['max_damage_score']:.1f}")
        proof_lines.append(f"  * Impact Description         : {worst['impact_summary']}")
        proof_lines.append("\n" + "=" * 80 + "\n")

    # Save master JSON
    master_json_path = os.path.join(output_dir, "plans_all_areas.json")
    with open(master_json_path, "w", encoding="utf-8") as f:
        json.dump(plans_json_data, f, indent=2)
    print(f"Saved Master JSON Plans -> {master_json_path}")

    # Save Audit Proof
    proof_path = os.path.join(output_dir, "audit_proof.txt")
    with open(proof_path, "w", encoding="utf-8") as f:
        f.write("\n".join(proof_lines))
    print(f"Saved Auditable Proof -> {proof_path}")

    print("\n" + "\n".join(proof_lines))
    return plans_json_data


if __name__ == "__main__":
    run_pipeline()
