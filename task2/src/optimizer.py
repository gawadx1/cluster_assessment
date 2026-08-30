"""
optimizer.py
Deterministic Multi-Objective Route Optimizer for Task 2.
Optimizes stop sequences for all four field reps, respecting historical travel times,
stop durations, invoice ordering rhythms, priority tiers, lunch, and return deadline.
"""

from typing import List, Dict, Any, Tuple
import numpy as np
import pandas as pd

try:
    from src.data_loader import DatasetContainer, haversine_km, minutes_to_time_str
    from src.historical_models import HistoricalModels
    from src.schedule_engine import build_area_schedule, AreaDayPlan
except ImportError:
    from data_loader import DatasetContainer, haversine_km, minutes_to_time_str
    from historical_models import HistoricalModels
    from schedule_engine import build_area_schedule, AreaDayPlan


class RouteOptimizer:
    def __init__(self, models: HistoricalModels):
        self.models = models
        self.data = models.data

    def optimize_area(
        self,
        area: str,
        rep_id: int,
        day_start_min: float = 540.0,
        cutoff_min: float = 1060.0
    ) -> AreaDayPlan:
        """
        Optimizes the 16-stop sequence for an area deterministically.
        """
        tomorrow_df = self.data.tomorrow
        area_tomorrow = tomorrow_df[tomorrow_df['area'] == area].copy()
        stop_ids = area_tomorrow['pharmacy_id'].tolist()

        if len(stop_ids) != 16:
            raise ValueError(f"Expected 16 stops for area {area}, found {len(stop_ids)}")

        # Step 1: Initial constructive heuristic (Rhythm & Distance Aware)
        best_sequence = self._construct_initial_tour(area, stop_ids, day_start_min)

        # Step 2: 2-Opt and Swap Local Search
        best_sequence = self._local_search(area, rep_id, best_sequence, day_start_min, cutoff_min)

        # Step 3: Build finalized day plan
        plan = build_area_schedule(
            area=area,
            rep_id=rep_id,
            ordered_pharmacy_ids=best_sequence,
            models=self.models,
            day_start_min=day_start_min,
            cutoff_min=cutoff_min
        )

        return plan

    def _eval_sequence_cost(
        self,
        area: str,
        rep_id: int,
        sequence: List[int],
        day_start_min: float,
        cutoff_min: float
    ) -> float:
        """
        Multi-objective cost function:
        - Total travel time
        - Invoice rhythm lateness penalty (weighted by Priority)
        - Priority 1 arrival timeliness
        - Cutoff breach penalty (huge if > 17:40)
        """
        plan = build_area_schedule(
            area=area,
            rep_id=rep_id,
            ordered_pharmacy_ids=sequence,
            models=self.models,
            day_start_min=day_start_min,
            cutoff_min=cutoff_min
        )

        # 1. Travel time cost (weight = 1.0)
        cost = plan.total_travel_time_min * 1.0

        # 2. Rhythm alignment penalty
        tomorrow_df = self.data.tomorrow
        for stop in plan.stops_summary:
            pid = stop['pharmacy_id']
            prio = stop['priority']
            arr_min = stop['arrival_time']
            # parse arrival minutes
            parts = arr_min.split(':')
            arr_m = int(parts[0]) * 60 + int(parts[1])

            target_stat = self.models.timing_targets.get(pid)
            if target_stat and not target_stat.is_thin_history:
                tgt = target_stat.target_arrival_before_min
                lateness = max(0.0, arr_m - tgt)
                # P1: 3.0x weight, P2: 2.0x, P3: 1.0x
                w = {1: 3.0, 2: 2.0, 3: 1.0}.get(prio, 1.0)
                cost += lateness * w * 0.5
            elif prio == 1:
                # For P1 stops with thin history, prefer before 13:00 (780m)
                lateness = max(0.0, arr_m - 780.0)
                cost += lateness * 2.0

        # 3. Cutoff overrun penalty
        if plan.day_end_min > cutoff_min:
            cost += (plan.day_end_min - cutoff_min) * 1000.0

        return cost

    def _construct_initial_tour(
        self,
        area: str,
        stop_ids: List[int],
        day_start_min: float
    ) -> List[int]:
        """
        Constructs an initial tour prioritizing early timing targets and spatial proximity.
        """
        pharma_df = self.data.pharmacies
        areas_df = self.data.areas
        area_row = areas_df[areas_df['area'] == area].iloc[0]
        c_lat = float(area_row['centroid_lat'])
        c_lon = float(area_row['centroid_lon'])

        unvisited = list(stop_ids)
        tour = []

        # Sort stops by composite score: target time + distance from base
        def stop_urgency(pid):
            tgt_stat = self.models.timing_targets.get(pid)
            tgt_time = tgt_stat.target_arrival_before_min if tgt_stat else 750.0
            p_row = pharma_df[pharma_df['id'] == pid].iloc[0]
            d_base = haversine_km(c_lat, c_lon, float(p_row['lat']), float(p_row['lon']))
            t_row = self.data.tomorrow[self.data.tomorrow['pharmacy_id'] == pid].iloc[0]
            prio = int(t_row['priority'])
            prio_bonus = {1: -60.0, 2: -30.0, 3: 0.0}.get(prio, 0.0)
            return tgt_time + prio_bonus + (d_base * 10.0)

        # First stop: earliest urgent stop
        unvisited.sort(key=stop_urgency)
        curr_id = unvisited.pop(0)
        tour.append(curr_id)

        while unvisited:
            curr_row = pharma_df[pharma_df['id'] == curr_id].iloc[0]
            curr_lat = float(curr_row['lat'])
            curr_lon = float(curr_row['lon'])

            def step_cost(pid):
                p_row = pharma_df[pharma_df['id'] == pid].iloc[0]
                p_lat = float(p_row['lat'])
                p_lon = float(p_row['lon'])
                drive = self.models.get_travel_time(
                    area=area,
                    from_id=curr_id,
                    to_id=pid,
                    from_lat=curr_lat,
                    from_lon=curr_lon,
                    to_lat=p_lat,
                    to_lon=p_lon
                )
                tgt_stat = self.models.timing_targets.get(pid)
                tgt_time = tgt_stat.target_arrival_before_min if tgt_stat else 750.0
                t_row = self.data.tomorrow[self.data.tomorrow['pharmacy_id'] == pid].iloc[0]
                prio = int(t_row['priority'])
                prio_bias = {1: -10.0, 2: -5.0, 3: 0.0}.get(prio, 0.0)
                return drive * 2.0 + (tgt_time * 0.05) + prio_bias

            unvisited.sort(key=step_cost)
            next_id = unvisited.pop(0)
            tour.append(next_id)
            curr_id = next_id

        return tour

    def _local_search(
        self,
        area: str,
        rep_id: int,
        tour: List[int],
        day_start_min: float,
        cutoff_min: float
    ) -> List[int]:
        """
        Deterministic 2-opt and node-relocate local search.
        """
        best_tour = list(tour)
        best_cost = self._eval_sequence_cost(area, rep_id, best_tour, day_start_min, cutoff_min)
        improved = True
        iterations = 0
        max_iterations = 200

        n = len(tour)
        while improved and iterations < max_iterations:
            improved = False
            iterations += 1

            # 1. 2-Opt segment reversals
            for i in range(n - 1):
                for j in range(i + 2, n):
                    new_tour = best_tour[:i] + best_tour[i:j+1][::-1] + best_tour[j+1:]
                    cost = self._eval_sequence_cost(area, rep_id, new_tour, day_start_min, cutoff_min)
                    if cost < best_cost - 1e-4:
                        best_cost = cost
                        best_tour = new_tour
                        improved = True
                        break
                if improved:
                    break

            if improved:
                continue

            # 2. Relocate / Insertion moves
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    item = best_tour[i]
                    temp = [x for k, x in enumerate(best_tour) if k != i]
                    new_tour = temp[:j] + [item] + temp[j:]
                    cost = self._eval_sequence_cost(area, rep_id, new_tour, day_start_min, cutoff_min)
                    if cost < best_cost - 1e-4:
                        best_cost = cost
                        best_tour = new_tour
                        improved = True
                        break
                if improved:
                    break

        return best_tour

    def optimize_all_areas(self) -> Dict[str, AreaDayPlan]:
        """
        Runs optimization across all four areas/employees and returns their plans.
        """
        areas_df = self.data.areas
        plans = {}

        # Rep to Area mapping:
        # Rep 1: Smouha, Rep 2: Nasr City, Rep 3: Faisal, Rep 4: Mohandessin
        rep_mapping = {
            'Smouha': 1,
            'Nasr City': 2,
            'Faisal': 3,
            'Mohandessin': 4
        }

        for area_name, rep_id in rep_mapping.items():
            plan = self.optimize_area(area=area_name, rep_id=rep_id)
            plans[area_name] = plan

        return plans


if __name__ == "__main__":
    try:
        from src.data_loader import load_all_data
        from src.historical_models import HistoricalModels
    except ImportError:
        from data_loader import load_all_data
        from historical_models import HistoricalModels

    data = load_all_data()
    models = HistoricalModels(data)
    optimizer = RouteOptimizer(models)

    print("Optimizing routes for all 4 areas...")
    plans = optimizer.optimize_all_areas()

    for area, plan in plans.items():
        print(f"\n================ AREA: {area} (Rep {plan.rep_id}) ================")
        print(f"Start: {plan.day_start_str} | End: {plan.day_end_str} | Fits <= 17:40: {plan.fits_before_cutoff}")
        print(f"Equation: {plan.arithmetic_equation}")
        print(f"Total Drives: {plan.total_travel_time_min}m | Stays: {plan.total_stay_duration_min}m | Lunch: {plan.lunch_duration_min}m")
        print(f"Worst Failure Stop: {plan.critical_failure_analysis['most_damaging_stop_name']} (P{plan.critical_failure_analysis['most_damaging_priority']}) - Score {plan.critical_failure_analysis['max_damage_score']}")
