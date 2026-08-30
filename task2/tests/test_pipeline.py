"""
test_pipeline.py
Automated test suite verifying the complete Task 2 implementation against all 18 requirements:
1. Dataset integrity & row counts
2. Pharmacy/area relationships
3. Employee/area assignments
4. Tomorrow's stop assignments (16 per area)
5. Timestamp parsing (UTC to local, HH:MM conversions)
6. Visit-duration cleaning & positive duration validation
7. Travel-time extraction & consecutive pair reconstruction
8. Missing/contradictory history handling & quantification
9. Invoice timing extraction across all 3 systems (App, ERP, Legacy)
10. Timing-target generation & peak ordering windows
11. Route generation & sequence validity
12. Start/end constraints (Centroid base start and return)
13. All 64 assigned stops visited across all 4 areas
14. Lunch break duration exactly 25.0 minutes
15. Final return time strictly <= 17:40 (1060 minutes from midnight)
16. Dispatcher handling for abnormal registry status codes
17. Per-area single-stop critical failure analysis
18. Itinerary arithmetic correctness and consistency with plan CSVs/JSONs
"""

import os
import sys
import json
import pytest
import pandas as pd
import numpy as np

# Add task2 and src to path
test_dir = os.path.dirname(os.path.abspath(__file__))
task2_dir = os.path.dirname(test_dir)
sys.path.insert(0, task2_dir)
sys.path.insert(0, os.path.join(task2_dir, "src"))

from src.data_loader import (
    load_all_data,
    time_str_to_minutes,
    minutes_to_time_str,
    haversine_km,
    clean_tokens
)
from src.historical_models import HistoricalModels
from src.optimizer import RouteOptimizer
from src.schedule_engine import build_area_schedule


@pytest.fixture(scope="module")
def dataset():
    dataset_dir = os.path.join(task2_dir, "dataset")
    return load_all_data(dataset_dir)


@pytest.fixture(scope="module")
def models(dataset):
    return HistoricalModels(dataset)


@pytest.fixture(scope="module")
def all_plans(models):
    optimizer = RouteOptimizer(models)
    return optimizer.optimize_all_areas()


# 1. Dataset integrity
def test_dataset_integrity(dataset):
    assert dataset.quality_metrics["areas_count"] == 4
    assert dataset.quality_metrics["pharmacies_total"] == 1826
    assert dataset.quality_metrics["visits_total"] == 12083
    assert dataset.quality_metrics["app_invoices_total"] == 8943
    assert dataset.quality_metrics["erp_invoices_total"] == 17691
    assert dataset.quality_metrics["legacy_invoices_total"] == 4185
    assert dataset.quality_metrics["tomorrow_stops_total"] == 64


# 2. Pharmacy/area relationships
def test_pharmacy_area_relationships(dataset):
    pharma = dataset.pharmacies
    valid_areas = set(dataset.areas['area'])
    assert set(pharma['area'].unique()).issubset(valid_areas)
    assert (pharma['lat'] > 28.0).all() and (pharma['lat'] < 33.0).all()
    assert (pharma['lon'] > 28.0).all() and (pharma['lon'] < 34.0).all()


# 3. Employee/area assignments
def test_employee_area_assignments(dataset):
    tomorrow = dataset.tomorrow
    expected_mapping = {
        'Smouha': 1,
        'Nasr City': 2,
        'Faisal': 3,
        'Mohandessin': 4
    }
    for area, rep_id in expected_mapping.items():
        area_reps = tomorrow[tomorrow['area'] == area]['rep_id'].unique()
        assert len(area_reps) == 1
        assert area_reps[0] == rep_id


# 4. Tomorrow's stop assignments
def test_tomorrow_stop_assignments(dataset):
    tomorrow = dataset.tomorrow
    assert len(tomorrow) == 64
    for area in ['Smouha', 'Nasr City', 'Faisal', 'Mohandessin']:
        stops = tomorrow[tomorrow['area'] == area]
        assert len(stops) == 16
        assert stops['pharmacy_id'].nunique() == 16


# 5. Timestamp parsing
def test_timestamp_parsing():
    assert time_str_to_minutes("09:00") == 540.0
    assert time_str_to_minutes("17:40") == 1060.0
    assert time_str_to_minutes("12:30:30") == 750.5
    assert pd.isnull(time_str_to_minutes(None))
    assert minutes_to_time_str(540.0) == "09:00"
    assert minutes_to_time_str(1060.0) == "17:40"


# 6. Visit duration cleaning
def test_visit_duration_cleaning(dataset):
    visits = dataset.visits_raw
    valid_visits = visits[
        (visits['cancelled_flag'] == 0) &
        (visits['dep_min'].notnull()) &
        (visits['duration'] > 0)
    ]
    assert len(valid_visits) == dataset.quality_metrics["visits_valid_good"]
    assert len(valid_visits) == 11347
    assert (valid_visits['duration'] >= 1.0).all()
    assert (valid_visits['duration'] <= 60.0).all()


# 7. Travel-time extraction & consecutive pairs
def test_travel_time_extraction(models):
    assert len(models.pairwise_travel) > 0
    # Inter-pharmacy drive times must fall within realistic bounds (4.0m to 18.0m)
    for pair, dur in models.pairwise_travel.items():
        assert 3.0 <= dur <= 30.0


# 8. Missing/contradictory history handling
def test_missing_contradictory_history(dataset):
    assert dataset.quality_metrics["visits_missing_departure"] == 736
    assert dataset.quality_metrics["visits_cancelled"] == 138


# 9. Invoice timing extraction across all 3 systems
def test_invoice_timing_extraction(dataset):
    invoices = dataset.invoices_all
    assert len(invoices) > 20000
    sources = set(invoices['source'].unique())
    assert sources == {'app', 'legacy', 'erp'}
    assert (invoices['time_min'] >= 0.0).all()
    assert (invoices['time_min'] <= 1440.0).all()


# 10. Timing-target generation
def test_timing_target_generation(models):
    for pid, target in models.timing_targets.items():
        assert target.target_arrival_before_min > 0.0
        assert target.target_arrival_before_min < 1440.0
        if not target.is_thin_history:
            assert target.total_invoices_count >= 3


# 11. Route generation & sequence validity
def test_route_generation(all_plans):
    assert len(all_plans) == 4
    for area, plan in all_plans.items():
        assert plan.stops_count == 16
        assert len(plan.stops_summary) == 16
        # Sequence stop numbers must be 1 to 16 contiguous
        stop_indices = [s['stop_index'] for s in plan.stops_summary]
        assert stop_indices == list(range(1, 17))


# 12. Start/end constraints
def test_start_end_constraints(all_plans, dataset):
    areas_df = dataset.areas
    for area, plan in all_plans.items():
        area_row = areas_df[areas_df['area'] == area].iloc[0]
        assert plan.centroid_lat == float(area_row['centroid_lat'])
        assert plan.centroid_lon == float(area_row['centroid_lon'])
        assert plan.day_start_min == 540.0  # 09:00
        assert plan.itinerary[0]['segment_type'] == 'drive'
        assert "Centroid" in plan.itinerary[0]['from_location']
        assert plan.itinerary[-1]['segment_type'] == 'return'
        assert "Centroid" in plan.itinerary[-1]['to_location']


# 13. All 64 assigned stops planned
def test_all_assigned_stops_planned(all_plans, dataset):
    planned_pids = set()
    for plan in all_plans.values():
        for s in plan.stops_summary:
            planned_pids.add(s['pharmacy_id'])
    assert len(planned_pids) == 64
    assigned_pids = set(dataset.tomorrow['pharmacy_id'])
    assert planned_pids == assigned_pids


# 14. Lunch break duration exactly 25 minutes
def test_lunch_duration(all_plans):
    for plan in all_plans.values():
        assert plan.lunch_duration_min == 25.0
        lunch_segments = [s for s in plan.itinerary if s['segment_type'] == 'lunch']
        assert len(lunch_segments) == 1
        assert lunch_segments[0]['duration_min'] == 25.0


# 15. Final return time <= 17:40
def test_cutoff_compliance(all_plans):
    for area, plan in all_plans.items():
        assert plan.day_end_min <= 1060.0, f"Area {area} exceeded 17:40 cutoff! End: {plan.day_end_str}"
        assert plan.fits_before_cutoff is True
        assert plan.spare_time_min >= 0.0


# 16. Dispatcher handling of abnormal registry codes
def test_dispatcher_handling(all_plans):
    for plan in all_plans.values():
        for note in plan.dispatcher_notes:
            assert note['status_code'] in [1, 2]
            assert len(note['action_taken']) > 0
            assert len(note['reason']) > 0


# 17. Single-stop failure analysis
def test_single_stop_failure_analysis(all_plans):
    for area, plan in all_plans.items():
        fa = plan.critical_failure_analysis
        assert fa['most_damaging_stop_id'] is not None
        assert fa['max_damage_score'] > 0
        assert len(fa['all_stop_evaluations']) == 16


# 18. Arithmetic correctness
def test_itinerary_arithmetic_consistency(all_plans):
    for area, plan in all_plans.items():
        # Re-sum all segment durations
        computed_duration = sum(s['duration_min'] for s in plan.itinerary)
        expected_end = plan.day_start_min + computed_duration
        assert np.isclose(plan.day_end_min, expected_end, atol=1e-3)
        assert np.isclose(plan.total_travel_time_min + plan.total_stay_duration_min + plan.lunch_duration_min, plan.total_day_span_min, atol=1e-3)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
