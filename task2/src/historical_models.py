"""
historical_models.py
Statistical models for Task 2 derived entirely from historical data:
1. Stop Duration Model (per pharmacy with area fallback for thin history)
2. Travel Time Model (consecutive visit history, pairwise observations, empirical distance calibration)
3. Pharmacy Ordering Rhythm / Timing Target Model (App, ERP, Legacy invoice distributions)
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Any, Optional
from dataclasses import dataclass

try:
    from src.data_loader import DatasetContainer, haversine_km, minutes_to_time_str
except ImportError:
    from data_loader import DatasetContainer, haversine_km, minutes_to_time_str


@dataclass
class StopDurationStats:
    pharmacy_id: int
    area: str
    historical_visits_count: int
    mean_duration_min: float
    median_duration_min: float
    std_duration_min: float
    min_duration_min: float
    max_duration_min: float
    is_thin_history: bool
    estimated_duration_min: float
    duration_source: str


@dataclass
class TimingTargetStats:
    pharmacy_id: int
    area: str
    total_invoices_count: int
    app_invoices_count: int
    legacy_invoices_count: int
    erp_invoices_count: int
    earliest_order_min: float
    median_order_min: float
    mean_order_min: float
    p25_order_min: float
    p75_order_min: float
    latest_order_min: float
    is_thin_history: bool
    target_arrival_before_min: float
    target_window_str: str


class HistoricalModels:
    def __init__(self, data: DatasetContainer):
        self.data = data
        self._build_stop_duration_model()
        self._build_travel_time_model()
        self._build_timing_targets_model()

    def _build_stop_duration_model(self):
        """Builds stop duration model from trustworthy historical visit records."""
        visits = self.data.visits_raw
        pharma = self.data.pharmacies

        # Quality filter: non-cancelled, non-null departed_at, positive duration
        good_visits = visits[
            (visits['cancelled_flag'] == 0) &
            (visits['dep_min'].notnull()) &
            (visits['duration'] > 0)
        ].copy()

        good_visits = good_visits.merge(
            pharma[['id', 'area']],
            left_on='pharmacy_id',
            right_on='id',
            how='left'
        )

        # Area-level benchmarks
        self.area_duration_medians = good_visits.groupby('area')['duration'].median().to_dict()
        self.overall_duration_median = float(good_visits['duration'].median())

        # Per-pharmacy aggregation
        pharma_stats = good_visits.groupby('pharmacy_id')['duration'].agg(
            count='count',
            mean='mean',
            median='median',
            std='std',
            min='min',
            max='max'
        ).reset_index()

        self.duration_stats: Dict[int, StopDurationStats] = {}

        # Precompute for all pharmacies in registry
        for _, p in pharma.iterrows():
            pid = int(p['id'])
            area = str(p['area'])
            match = pharma_stats[pharma_stats['pharmacy_id'] == pid]

            if len(match) > 0 and match['count'].iloc[0] >= 2:
                row = match.iloc[0]
                cnt = int(row['count'])
                mean_d = float(row['mean'])
                med_d = float(row['median'])
                std_d = float(row['std']) if not pd.isnull(row['std']) else 0.0
                min_d = float(row['min'])
                max_d = float(row['max'])
                is_thin = False
                est_d = round(med_d, 1)
                src = f"Historical Median ({cnt} visits)"
            else:
                cnt = int(match['count'].iloc[0]) if len(match) > 0 else 0
                mean_d = float(match['mean'].iloc[0]) if len(match) > 0 else np.nan
                med_d = float(match['median'].iloc[0]) if len(match) > 0 else np.nan
                std_d = np.nan
                min_d = np.nan
                max_d = np.nan
                is_thin = True
                area_med = self.area_duration_medians.get(area, self.overall_duration_median)
                est_d = round(area_med, 1)
                src = f"Area Benchmark Fallback ({area} median = {area_med:.1f}m)"

            self.duration_stats[pid] = StopDurationStats(
                pharmacy_id=pid,
                area=area,
                historical_visits_count=cnt,
                mean_duration_min=mean_d,
                median_duration_min=med_d,
                std_duration_min=std_d,
                min_duration_min=min_d,
                max_duration_min=max_d,
                is_thin_history=is_thin,
                estimated_duration_min=est_d,
                duration_source=src
            )

    def _build_travel_time_model(self):
        """Builds realistic travel time model based on historical consecutive visits."""
        visits = self.data.visits_raw.copy()
        pharma = self.data.pharmacies

        visits = visits.merge(
            pharma[['id', 'lat', 'lon', 'area']],
            left_on='pharmacy_id',
            right_on='id',
            how='left'
        )

        visits = visits.sort_values(['rep_id', 'visit_date', 'stop_index']).reset_index(drop=True)
        visits['prev_rep'] = visits['rep_id'].shift(1)
        visits['prev_date'] = visits['visit_date'].shift(1)
        visits['prev_stop_index'] = visits['stop_index'].shift(1)
        visits['prev_dep_min'] = visits['dep_min'].shift(1)
        visits['prev_pharmacy_id'] = visits['pharmacy_id'].shift(1)
        visits['prev_lat'] = visits['lat'].shift(1)
        visits['prev_lon'] = visits['lon'].shift(1)
        visits['prev_cancelled'] = visits['cancelled_flag'].shift(1)

        valid_trips = (
            (visits['rep_id'] == visits['prev_rep']) &
            (visits['visit_date'] == visits['prev_date']) &
            (visits['stop_index'] == visits['prev_stop_index'] + 1) &
            (visits['cancelled_flag'] == 0) &
            (visits['prev_cancelled'] == 0) &
            (visits['dep_min'].notnull()) &
            (visits['prev_dep_min'].notnull()) &
            (visits['arr_min'].notnull())
        )

        trips_df = visits[valid_trips].copy()
        trips_df['travel_time'] = trips_df['arr_min'] - trips_df['prev_dep_min']
        trips_df['dist_km'] = trips_df.apply(
            lambda r: haversine_km(r['prev_lat'], r['prev_lon'], r['lat'], r['lon']),
            axis=1
        )

        # Filter impossible / corrupt trip durations
        clean_trips = trips_df[(trips_df['travel_time'] >= 1.0) & (trips_df['travel_time'] <= 45.0)]

        # 1. Pairwise historical direct movements
        pair_agg = clean_trips.groupby(['prev_pharmacy_id', 'pharmacy_id'])['travel_time'].agg(
            ['count', 'mean', 'median']
        ).reset_index()

        self.pairwise_travel: Dict[Tuple[int, int], float] = {}
        for _, row in pair_agg.iterrows():
            p_from = int(row['prev_pharmacy_id'])
            p_to = int(row['pharmacy_id'])
            self.pairwise_travel[(p_from, p_to)] = float(row['median'])

        # 2. Area-level travel statistics and empirical distance-calibrated models
        self.area_travel_stats = {}
        for area_name, grp in clean_trips.groupby('area'):
            self.area_travel_stats[area_name] = {
                'count': len(grp),
                'median_time': float(grp['travel_time'].median()),
                'mean_time': float(grp['travel_time'].mean()),
                'p25_time': float(grp['travel_time'].quantile(0.25)),
                'p75_time': float(grp['travel_time'].quantile(0.75)),
                'mean_dist': float(grp['dist_km'].mean()),
                'median_dist': float(grp['dist_km'].median()),
                'avg_speed_kmh': float((grp['dist_km'] / (grp['travel_time'] / 60.0)).mean())
            }

        # 3. Morning departure from centroid model
        # Stop 1 arrival times historically:
        stop1_visits = visits[
            (visits['stop_index'] == 1) &
            (visits['cancelled_flag'] == 0) &
            (visits['arr_min'].notnull())
        ].copy()
        # Reps start at 09:00 (540 min); Stop 1 arrival mean is ~560.7 min (~20.7 min travel from base)
        self.centroid_departure_stats = {}
        for area_name, grp in stop1_visits.groupby('area'):
            self.centroid_departure_stats[area_name] = {
                'mean_stop1_arr': float(grp['arr_min'].mean()),
                'median_stop1_arr': float(grp['arr_min'].median()),
                'implied_morning_drive_mean': float(grp['arr_min'].mean() - 540.0),
                'implied_morning_drive_median': float(grp['arr_min'].median() - 540.0),
            }

    def _build_timing_targets_model(self):
        """Builds ordering rhythm and timing targets from all three invoice systems."""
        invoices = self.data.invoices_all
        pharma = self.data.pharmacies

        inv_stats = invoices.groupby('pharmacy_id').agg(
            total_count=('time_min', 'count'),
            earliest=('time_min', 'min'),
            median=('time_min', 'median'),
            mean=('time_min', 'mean'),
            p25=('time_min', lambda x: np.percentile(x, 25)),
            p75=('time_min', lambda x: np.percentile(x, 75)),
            latest=('time_min', 'max'),
        ).reset_index()

        src_counts = invoices.groupby(['pharmacy_id', 'source']).size().unstack(fill_value=0).reset_index()

        merged_inv = inv_stats.merge(src_counts, on='pharmacy_id', how='left')

        self.timing_targets: Dict[int, TimingTargetStats] = {}

        for _, p in pharma.iterrows():
            pid = int(p['id'])
            area = str(p['area'])
            m = merged_inv[merged_inv['pharmacy_id'] == pid]

            if len(m) > 0 and m['total_count'].iloc[0] >= 3:
                r = m.iloc[0]
                tot = int(r['total_count'])
                app_cnt = int(r['app']) if 'app' in r else 0
                leg_cnt = int(r['legacy']) if 'legacy' in r else 0
                erp_cnt = int(r['erp']) if 'erp' in r else 0
                earliest = float(r['earliest'])
                median_t = float(r['median'])
                mean_t = float(r['mean'])
                p25_t = float(r['p25'])
                p75_t = float(r['p75'])
                latest = float(r['latest'])
                is_thin = False
                # Target: Visit before their median ordering time to capture orders before closing
                target_min = round(median_t, 1)
                window_str = f"{minutes_to_time_str(earliest)} - {minutes_to_time_str(median_t)} (Peak: {minutes_to_time_str(median_t)})"
            elif len(m) > 0 and m['total_count'].iloc[0] > 0:
                r = m.iloc[0]
                tot = int(r['total_count'])
                app_cnt = int(r['app']) if 'app' in r else 0
                leg_cnt = int(r['legacy']) if 'legacy' in r else 0
                erp_cnt = int(r['erp']) if 'erp' in r else 0
                earliest = float(r['earliest'])
                median_t = float(r['median'])
                mean_t = float(r['mean'])
                p25_t = float(r['p25'])
                p75_t = float(r['p75'])
                latest = float(r['latest'])
                is_thin = True
                target_min = round(median_t, 1)
                window_str = f"Thin History ({tot} inv): ~{minutes_to_time_str(median_t)}"
            else:
                tot = 0
                app_cnt = 0
                leg_cnt = 0
                erp_cnt = 0
                earliest = np.nan
                median_t = np.nan
                mean_t = np.nan
                p25_t = np.nan
                p75_t = np.nan
                latest = np.nan
                is_thin = True
                # Default mid-day rhythm for thin history
                target_min = 750.0  # 12:30
                window_str = "No History: Default Mid-day (12:30)"

            self.timing_targets[pid] = TimingTargetStats(
                pharmacy_id=pid,
                area=area,
                total_invoices_count=tot,
                app_invoices_count=app_cnt,
                legacy_invoices_count=leg_cnt,
                erp_invoices_count=erp_cnt,
                earliest_order_min=earliest,
                median_order_min=median_t,
                mean_order_min=mean_t,
                p25_order_min=p25_t,
                p75_order_min=p75_t,
                latest_order_min=latest,
                is_thin_history=is_thin,
                target_arrival_before_min=target_min,
                target_window_str=window_str
            )

    def get_stop_duration(self, pharmacy_id: int, area: str) -> float:
        """Returns estimated stop duration in minutes."""
        if pharmacy_id in self.duration_stats:
            return self.duration_stats[pharmacy_id].estimated_duration_min
        area_med = self.area_duration_medians.get(area, self.overall_duration_median)
        return float(round(area_med, 1))

    def get_travel_time(
        self,
        area: str,
        from_id: int,
        to_id: int,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float
    ) -> float:
        """
        Derives realistic travel time between two pharmacies.
        Prioritizes direct historical pair movement; falls back to empirical
        area distance-calibrated travel model.
        """
        # 1. Direct directed pair
        if (from_id, to_id) in self.pairwise_travel:
            return round(self.pairwise_travel[(from_id, to_id)], 1)

        # 2. Reverse pair
        if (to_id, from_id) in self.pairwise_travel:
            return round(self.pairwise_travel[(to_id, from_id)], 1)

        # 3. Distance-calibrated empirical area model
        dist_km = haversine_km(from_lat, from_lon, to_lat, to_lon)
        area_stat = self.area_travel_stats.get(area, {
            'median_time': 7.0,
            'median_dist': 1.2,
            'avg_speed_kmh': 12.0
        })

        # Speed in urban district conditions: clamp between 8 km/h and 22 km/h
        speed_kmh = max(8.0, min(22.0, area_stat.get('avg_speed_kmh', 12.0)))
        # Base fixed time for parking/maneuvering + driving time
        drive_time = 3.0 + (dist_km / speed_kmh) * 60.0
        # Historical inter-stop drive times are observed strictly between 4.0m and 18.0m
        clamped_time = max(4.0, min(18.0, drive_time))
        return round(clamped_time, 1)

    def get_centroid_travel_time(
        self,
        area: str,
        stop_id: int,
        stop_lat: float,
        stop_lon: float,
        centroid_lat: float,
        centroid_lon: float,
        is_return: bool = False
    ) -> float:
        """
        Derives travel time between the area map center (centroid) and a pharmacy.
        Calibrated against historical Stop 1 arrival times (departure from centroid at 09:00).
        """
        dist_km = haversine_km(centroid_lat, centroid_lon, stop_lat, stop_lon)
        dep_stat = self.centroid_departure_stats.get(area, {'implied_morning_drive_median': 20.0})
        base_drive = dep_stat.get('implied_morning_drive_median', 20.0)

        # Calibrate with distance from centroid (median distance ~1.0 km)
        drive_time = (base_drive - 5.0) + (dist_km * 5.0)
        # Bounded between 12.0 and 26.0 minutes to match Stop 1 empirical arrivals (09:12 - 09:28)
        clamped = max(12.0, min(26.0, drive_time))
        return round(clamped, 1)


if __name__ == "__main__":
    try:
        from src.data_loader import load_all_data
    except ImportError:
        from data_loader import load_all_data
    data = load_all_data()
    models = HistoricalModels(data)
    print("Historical models built successfully.")
    print("Area duration medians:", models.area_duration_medians)
    print("Area travel stats summary:", {k: v['median_time'] for k, v in models.area_travel_stats.items()})
    print("Centroid departure implied drives:", {k: v['implied_morning_drive_median'] for k, v in models.centroid_departure_stats.items()})
