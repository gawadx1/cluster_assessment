"""
schedule_engine.py
Chronological itinerary generator and strict arithmetic verification engine.
Generates the exact step-by-step timeline and mathematical proof that the day fits.
"""

from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict

try:
    from src.data_loader import minutes_to_time_str, haversine_km
    from src.historical_models import HistoricalModels
except ImportError:
    from data_loader import minutes_to_time_str, haversine_km
    from historical_models import HistoricalModels


# For dataclass typing simplicity
Optional_int = Any


@dataclass
class ScheduleSegment:
    segment_index: int
    segment_type: str  # 'drive', 'stop', 'lunch', 'return'
    stop_index: Optional_int = None
    pharmacy_id: Optional_int = None
    pharmacy_name: str = ""
    priority: Optional_int = None
    status_code: Optional_int = None
    lat: float = 0.0
    lon: float = 0.0
    start_time_min: float = 0.0
    end_time_min: float = 0.0
    duration_min: float = 0.0
    start_time_str: str = ""
    end_time_str: str = ""
    target_arrival_str: str = ""
    timing_gap_min: float = 0.0
    rhythm_status: str = ""
    notes: str = ""


@dataclass
class AreaDayPlan:
    area: str
    rep_id: int
    centroid_lat: float
    centroid_lon: float
    stops_count: int
    day_start_min: float
    day_end_min: float
    day_start_str: str
    day_end_str: str
    total_travel_time_min: float
    total_stay_duration_min: float
    lunch_duration_min: float
    total_day_span_min: float
    fits_before_cutoff: bool
    cutoff_time_min: float
    cutoff_time_str: str
    spare_time_min: float
    arithmetic_equation: str
    itinerary: List[Dict[str, Any]]
    stops_summary: List[Dict[str, Any]]
    dispatcher_notes: List[Dict[str, Any]]
    critical_failure_analysis: Dict[str, Any]


def build_area_schedule(
    area: str,
    rep_id: int,
    ordered_pharmacy_ids: List[int],
    models: HistoricalModels,
    day_start_min: float = 540.0,  # 09:00
    cutoff_min: float = 1060.0,    # 17:40
    lunch_duration: float = 25.0,  # Exactly 25 minutes
    lunch_after_stop: int = 8      # Midway through 16 stops
) -> AreaDayPlan:
    """
    Constructs the step-by-step arithmetic timeline for an area route.
    """
    areas_df = models.data.areas
    area_row = areas_df[areas_df['area'] == area].iloc[0]
    c_lat = float(area_row['centroid_lat'])
    c_lon = float(area_row['centroid_lon'])

    pharma_df = models.data.pharmacies
    tomorrow_df = models.data.tomorrow

    itinerary: List[Dict[str, Any]] = []
    stops_summary: List[Dict[str, Any]] = []

    current_time = day_start_min
    seg_idx = 1
    total_drive_time = 0.0
    total_stay_time = 0.0

    prev_lat = c_lat
    prev_lon = c_lon
    prev_id = 0

    # 1. First Drive from Centroid to Stop 1
    first_pid = ordered_pharmacy_ids[0]
    p1_row = pharma_df[pharma_df['id'] == first_pid].iloc[0]
    p1_lat = float(p1_row['lat'])
    p1_lon = float(p1_row['lon'])

    d0_time = models.get_centroid_travel_time(
        area=area,
        stop_id=first_pid,
        stop_lat=p1_lat,
        stop_lon=p1_lon,
        centroid_lat=c_lat,
        centroid_lon=c_lon,
        is_return=False
    )
    total_drive_time += d0_time

    itinerary.append({
        'segment_index': seg_idx,
        'segment_type': 'drive',
        'description': f"Morning Departure from Centroid ({area}) to Stop 1 (ID {first_pid})",
        'from_location': f"Centroid ({area})",
        'to_location': f"Stop 1: {p1_row['name']} (ID {first_pid})",
        'start_time_min': current_time,
        'end_time_min': current_time + d0_time,
        'duration_min': d0_time,
        'start_time_str': minutes_to_time_str(current_time),
        'end_time_str': minutes_to_time_str(current_time + d0_time),
        'notes': f"Drive to first stop ({haversine_km(c_lat, c_lon, p1_lat, p1_lon):.2f} km)"
    })
    current_time += d0_time
    seg_idx += 1

    prev_lat = p1_lat
    prev_lon = p1_lon
    prev_id = first_pid

    # 2. Iterate through all 16 stops
    for idx, pid in enumerate(ordered_pharmacy_ids, start=1):
        p_row = pharma_df[pharma_df['id'] == pid].iloc[0]
        p_lat = float(p_row['lat'])
        p_lon = float(p_row['lon'])
        p_name = str(p_row['name'])
        status_code = int(p_row['status_code'])

        # Priority from tomorrow table
        t_match = tomorrow_df[tomorrow_df['pharmacy_id'] == pid]
        priority = int(t_match['priority'].iloc[0]) if len(t_match) > 0 else 2

        # Stay duration
        stay_dur = models.get_stop_duration(pid, area)
        total_stay_time += stay_dur

        # Drive duration to reach this stop (for stop 1, it was d0_time; for others, compute from prev)
        if idx == 1:
            drive_dur = d0_time
        else:
            drive_dur = models.get_travel_time(
                area=area,
                from_id=prev_id,
                to_id=pid,
                from_lat=prev_lat,
                from_lon=prev_lon,
                to_lat=p_lat,
                to_lon=p_lon
            )

        arrival_time = current_time
        departure_time = arrival_time + stay_dur

        # Rhythm & Timing target evaluation
        target_stat = models.timing_targets.get(pid)
        target_min = target_stat.target_arrival_before_min if target_stat else 720.0
        target_str = minutes_to_time_str(target_min)

        timing_gap = arrival_time - target_min  # Negative means arrived BEFORE target (ideal!)
        if target_stat and target_stat.is_thin_history:
            rhythm_status = "Thin History / On-Track"
        elif timing_gap <= 0:
            rhythm_status = f"Optimal (Arrived {abs(timing_gap):.0f}m before peak)"
        elif timing_gap <= 45:
            rhythm_status = f"Acceptable (+{timing_gap:.0f}m within order window)"
        else:
            rhythm_status = f"Late (+{timing_gap:.0f}m after peak)"

        dur_stat = models.duration_stats.get(pid)
        dur_note = dur_stat.duration_source if dur_stat else "Standard"

        itinerary.append({
            'segment_index': seg_idx,
            'segment_type': 'stop',
            'stop_index': idx,
            'pharmacy_id': pid,
            'pharmacy_name': p_name,
            'priority': priority,
            'status_code': status_code,
            'lat': p_lat,
            'lon': p_lon,
            'drive_time_min': drive_dur,
            'start_time_min': arrival_time,
            'end_time_min': departure_time,
            'duration_min': stay_dur,
            'start_time_str': minutes_to_time_str(arrival_time),
            'end_time_str': minutes_to_time_str(departure_time),
            'target_arrival_str': target_str,
            'timing_gap_min': round(timing_gap, 1),
            'rhythm_status': rhythm_status,
            'duration_source': dur_note,
            'notes': f"Priority P{priority} | Status: {status_code}"
        })
        seg_idx += 1

        stops_summary.append({
            'stop_index': idx,
            'pharmacy_id': pid,
            'name': p_name,
            'priority': priority,
            'status_code': status_code,
            'lat': p_lat,
            'lon': p_lon,
            'drive_to_stop_min': drive_dur,
            'arrival_time': minutes_to_time_str(arrival_time),
            'stay_duration_min': stay_dur,
            'departure_time': minutes_to_time_str(departure_time),
            'target_arrival': target_str,
            'rhythm_status': rhythm_status,
            'duration_source': dur_note
        })

        current_time = departure_time
        prev_lat = p_lat
        prev_lon = p_lon
        prev_id = pid

        # Insert Lunch exactly after designated stop
        if idx == lunch_after_stop:
            lunch_start = current_time
            lunch_end = lunch_start + lunch_duration
            itinerary.append({
                'segment_index': seg_idx,
                'segment_type': 'lunch',
                'description': "Mandatory Rep Lunch Break (25 minutes)",
                'start_time_min': lunch_start,
                'end_time_min': lunch_end,
                'duration_min': lunch_duration,
                'start_time_str': minutes_to_time_str(lunch_start),
                'end_time_str': minutes_to_time_str(lunch_end),
                'notes': f"25-min midday break (Stops 1-{idx} completed, Stops {idx+1}-16 remaining)"
            })
            seg_idx += 1
            current_time = lunch_end

        # Drive to next stop (if not last)
        if idx < len(ordered_pharmacy_ids):
            next_pid = ordered_pharmacy_ids[idx]
            next_row = pharma_df[pharma_df['id'] == next_pid].iloc[0]
            next_lat = float(next_row['lat'])
            next_lon = float(next_row['lon'])

            leg_drive = models.get_travel_time(
                area=area,
                from_id=pid,
                to_id=next_pid,
                from_lat=p_lat,
                from_lon=p_lon,
                to_lat=next_lat,
                to_lon=next_lon
            )
            total_drive_time += leg_drive

            itinerary.append({
                'segment_index': seg_idx,
                'segment_type': 'drive',
                'description': f"Drive from Stop {idx} (ID {pid}) to Stop {idx+1} (ID {next_pid})",
                'from_location': f"Stop {idx}: {p_name}",
                'to_location': f"Stop {idx+1}: {next_row['name']}",
                'start_time_min': current_time,
                'end_time_min': current_time + leg_drive,
                'duration_min': leg_drive,
                'start_time_str': minutes_to_time_str(current_time),
                'end_time_str': minutes_to_time_str(current_time + leg_drive),
                'notes': f"Inter-pharmacy drive ({haversine_km(p_lat, p_lon, next_lat, next_lon):.2f} km)"
            })
            seg_idx += 1
            current_time += leg_drive

    # 3. Return Drive from Stop 16 to Centroid
    last_pid = ordered_pharmacy_ids[-1]
    last_row = pharma_df[pharma_df['id'] == last_pid].iloc[0]
    last_lat = float(last_row['lat'])
    last_lon = float(last_row['lon'])

    d_return = models.get_centroid_travel_time(
        area=area,
        stop_id=last_pid,
        stop_lat=last_lat,
        stop_lon=last_lon,
        centroid_lat=c_lat,
        centroid_lon=c_lon,
        is_return=True
    )
    total_drive_time += d_return

    itinerary.append({
        'segment_index': seg_idx,
        'segment_type': 'return',
        'description': f"Evening Return Journey from Stop 16 (ID {last_pid}) to Centroid ({area})",
        'from_location': f"Stop 16: {last_row['name']} (ID {last_pid})",
        'to_location': f"Centroid ({area})",
        'start_time_min': current_time,
        'end_time_min': current_time + d_return,
        'duration_min': d_return,
        'start_time_str': minutes_to_time_str(current_time),
        'end_time_str': minutes_to_time_str(current_time + d_return),
        'notes': f"Return to dispatch base ({haversine_km(last_lat, last_lon, c_lat, c_lon):.2f} km)"
    })
    current_time += d_return

    day_end_min = current_time
    total_day_span = day_end_min - day_start_min
    spare_time = cutoff_min - day_end_min
    fits = day_end_min <= cutoff_min

    # Arithmetic Equation
    eq = (
        f"09:00 ({day_start_min:.1f}m) + Drives ({total_drive_time:.1f}m) + "
        f"Stays ({total_stay_time:.1f}m) + Lunch ({lunch_duration:.1f}m) = "
        f"{minutes_to_time_str(day_end_min)} ({day_end_min:.1f}m) <= 17:40 (1060.0m)"
    )

    # Dispatcher notes on abnormal status codes
    dispatcher_notes = []
    for pid in ordered_pharmacy_ids:
        p_row = pharma_df[pharma_df['id'] == pid].iloc[0]
        st = int(p_row['status_code'])
        if st != 0:
            if st == 1:
                action = "Serviced with Digital Account Validation"
                reason = "Status 1 (Digital/App Active, zero physical visit history). Dispatcher assigned rep to confirm contact details and app ordering sync."
            else:
                action = "Serviced with On-Site Verification Audit"
                reason = "Status 2 (Registry flagged inactive, zero visit history). Rep tasked with physical status verification and re-engagement."
            dispatcher_notes.append({
                'pharmacy_id': pid,
                'name': p_row['name'],
                'status_code': st,
                'action_taken': action,
                'reason': reason
            })

    # Critical single-stop failure analysis
    failure_analysis = analyze_single_stop_failures(
        area=area,
        rep_id=rep_id,
        ordered_ids=ordered_pharmacy_ids,
        models=models,
        base_plan_end_min=day_end_min,
        cutoff_min=cutoff_min
    )

    return AreaDayPlan(
        area=area,
        rep_id=rep_id,
        centroid_lat=c_lat,
        centroid_lon=c_lon,
        stops_count=len(ordered_pharmacy_ids),
        day_start_min=day_start_min,
        day_end_min=day_end_min,
        day_start_str=minutes_to_time_str(day_start_min),
        day_end_str=minutes_to_time_str(day_end_min),
        total_travel_time_min=round(total_drive_time, 1),
        total_stay_duration_min=round(total_stay_time, 1),
        lunch_duration_min=round(lunch_duration, 1),
        total_day_span_min=round(total_day_span, 1),
        fits_before_cutoff=fits,
        cutoff_time_min=cutoff_min,
        cutoff_time_str=minutes_to_time_str(cutoff_min),
        spare_time_min=round(spare_time, 1),
        arithmetic_equation=eq,
        itinerary=itinerary,
        stops_summary=stops_summary,
        dispatcher_notes=dispatcher_notes,
        critical_failure_analysis=failure_analysis
    )


def analyze_single_stop_failures(
    area: str,
    rep_id: int,
    ordered_ids: List[int],
    models: HistoricalModels,
    base_plan_end_min: float,
    cutoff_min: float = 1060.0
) -> Dict[str, Any]:
    """
    Simulates failure for each of the 16 stops (e.g. 45-minute delay / pharmacy issue)
    and computes the damage score to identify which single-stop failure hurts the day most.
    """
    pharma_df = models.data.pharmacies
    tomorrow_df = models.data.tomorrow

    results = []
    worst_pid = None
    max_damage_score = -1.0

    for idx, pid in enumerate(ordered_ids, start=1):
        p_row = pharma_df[pharma_df['id'] == pid].iloc[0]
        t_row = tomorrow_df[tomorrow_df['pharmacy_id'] == pid].iloc[0]
        priority = int(t_row['priority'])
        p_name = str(p_row['name'])

        # Failure scenario: 45-minute unexpected delay at this stop
        delay = 45.0
        new_end_min = base_plan_end_min + delay
        overrun_min = max(0.0, new_end_min - cutoff_min)

        # Damage score components:
        # 1. Priority weight (P1 = 3x, P2 = 2x, P3 = 1x)
        # 2. Downstream ripple on subsequent priority stops
        # 3. Schedule overrun beyond 17:40 cutoff
        prio_weight = {1: 3.0, 2: 2.0, 3: 1.0}.get(priority, 1.0)
        downstream_p1_count = sum(
            1 for p in ordered_ids[idx:]
            if int(tomorrow_df[tomorrow_df['pharmacy_id'] == p]['priority'].iloc[0]) == 1
        )

        damage_score = (prio_weight * 20.0) + (downstream_p1_count * 15.0) + (overrun_min * 2.0)

        item = {
            'stop_index': idx,
            'pharmacy_id': pid,
            'name': p_name,
            'priority': priority,
            'delayed_return_min': new_end_min,
            'delayed_return_str': minutes_to_time_str(new_end_min),
            'cutoff_breach_min': round(overrun_min, 1),
            'downstream_p1_affected': downstream_p1_count,
            'damage_score': round(damage_score, 1),
            'impact_description': (
                f"If Stop {idx} ({p_name}, P{priority}) fails, rep returns at "
                f"{minutes_to_time_str(new_end_min)} ({overrun_min:.0f}m breach) and jeopardizes "
                f"{downstream_p1_count} downstream Priority 1 stops."
            )
        }
        results.append(item)

        if damage_score > max_damage_score:
            max_damage_score = damage_score
            worst_pid = pid

    worst_stop = next(r for r in results if r['pharmacy_id'] == worst_pid)

    return {
        'most_damaging_stop_id': worst_pid,
        'most_damaging_stop_name': worst_stop['name'],
        'most_damaging_stop_index': worst_stop['stop_index'],
        'most_damaging_priority': worst_stop['priority'],
        'max_damage_score': worst_stop['damage_score'],
        'impact_summary': worst_stop['impact_description'],
        'all_stop_evaluations': results
    }
