"""
data_loader.py
Data loading, validation, cleaning, and linkage module for Task 2.
Loads all 7 dataset files, quantifies data quality, parses mixed timestamps,
and performs robust entity resolution for ERP invoices to pharmacies using an inverted token index.
"""

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Set, List, Optional
import pandas as pd
import numpy as np


def time_str_to_minutes(val: Any) -> float:
    """Converts HH:MM or HH:MM:SS string to minutes from midnight."""
    if pd.isnull(val):
        return np.nan
    s = str(val).strip()
    if not s:
        return np.nan
    parts = s.split(':')
    try:
        hrs = int(parts[0])
        mins = int(parts[1]) if len(parts) > 1 else 0
        secs = int(parts[2]) if len(parts) > 2 else 0
        return float(hrs * 60 + mins + secs / 60.0)
    except (ValueError, IndexError):
        return np.nan


def parse_utc_timestamp_to_local_min(val: Any) -> float:
    """
    Parses mixed-format UTC timestamps ('2024-09-15T07:24:52Z', '2024/09/05 15:37')
    and converts to Egypt Local Time (UTC+2) in minutes from midnight.
    """
    if pd.isnull(val):
        return np.nan
    s = str(val).strip()
    if not s:
        return np.nan
    try:
        if 'T' in s:
            time_part = s.split('T')[1].replace('Z', '')
            parts = time_part.split(':')
            hrs = int(parts[0])
            mins = int(parts[1])
            local_hrs = (hrs + 2) % 24
            return float(local_hrs * 60 + mins)
        if ' ' in s:
            time_part = s.split(' ')[1]
            parts = time_part.split(':')
            hrs = int(parts[0])
            mins = int(parts[1])
            local_hrs = (hrs + 2) % 24
            return float(local_hrs * 60 + mins)
    except Exception:
        pass
    return np.nan


def minutes_to_time_str(minutes: float) -> str:
    """Converts minutes from midnight to HH:MM format."""
    if pd.isnull(minutes):
        return "N/A"
    total_sec = int(round(minutes * 60))
    hrs = (total_sec // 3600) % 24
    mins = (total_sec % 3600) // 60
    return f"{hrs:02d}:{mins:02d}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great circle distance between two points in km."""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return float(R * c)


def clean_tokens(s: Any) -> Set[str]:
    """Extracts distinctive normalized tokens from pharmacy/account names."""
    if not isinstance(s, str):
        return set()
    s = s.lower().strip()
    s = re.sub(r'^(ph|py|ph/|py/|el-|el|ell|ph |py |pyy/)\s*', '', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    stop = {
        'pharmacy', 'ph', 'py', 'el', 'al', 'the', 'mall', 'branch',
        'st', 'wh', 'station', 'sst', 'road', 'main', 'zone', '6th',
        '2nd', 'br', '2', '1', 'and', 'of', 'near', 'dr'
    }
    tokens = {w for w in s.split() if w not in stop and not w.isdigit() and len(w) > 1}
    return tokens


@dataclass
class DatasetContainer:
    areas: pd.DataFrame
    pharmacies: pd.DataFrame
    visits_raw: pd.DataFrame
    invoices_app: pd.DataFrame
    invoices_erp: pd.DataFrame
    invoices_legacy: pd.DataFrame
    tomorrow: pd.DataFrame
    invoices_all: pd.DataFrame
    quality_metrics: Dict[str, Any]


def load_all_data(dataset_dir: str = "dataset") -> DatasetContainer:
    """
    Loads and validates all dataset CSV files from the given directory.
    Performs deterministic entity resolution and calculates comprehensive quality metrics.
    """
    # Check if dataset_dir exists directly or relative to task2
    if not os.path.isdir(dataset_dir):
        alt_path = os.path.join("task2", dataset_dir)
        if os.path.isdir(alt_path):
            dataset_dir = alt_path

    areas_df = pd.read_csv(os.path.join(dataset_dir, "areas_reference.csv"))
    pharmacies_df = pd.read_csv(os.path.join(dataset_dir, "pharmacy_registry.csv"))
    visits_raw_df = pd.read_csv(os.path.join(dataset_dir, "field_visit_log.csv"))
    app_df = pd.read_csv(os.path.join(dataset_dir, "invoices_app.csv"))
    erp_df = pd.read_csv(os.path.join(dataset_dir, "invoices_erp.csv"))
    legacy_df = pd.read_csv(os.path.join(dataset_dir, "invoices_legacy.csv"))
    tomorrow_df = pd.read_csv(os.path.join(dataset_dir, "route_plan_tomorrow.csv"))

    quality_metrics = {}

    quality_metrics["areas_count"] = len(areas_df)
    quality_metrics["pharmacies_total"] = len(pharmacies_df)
    quality_metrics["visits_total"] = len(visits_raw_df)
    quality_metrics["app_invoices_total"] = len(app_df)
    quality_metrics["erp_invoices_total"] = len(erp_df)
    quality_metrics["legacy_invoices_total"] = len(legacy_df)
    quality_metrics["tomorrow_stops_total"] = len(tomorrow_df)

    # 1. Process App Invoices (Universal Parser for UTC to Local Egypt UTC+2)
    app_df['time_min'] = app_df['placed_at_utc'].apply(parse_utc_timestamp_to_local_min)
    app_clean = app_df[['customer_id', 'time_min', 'grand_total']].rename(
        columns={'customer_id': 'pharmacy_id'}
    ).copy()
    app_clean['source'] = 'app'

    # 2. Process Legacy Invoices
    legacy_df['pharmacy_id'] = legacy_df['account_ref'].str.extract(r'(\d+)').astype(int)
    legacy_df['hour'] = legacy_df['doc_time'].str.split(':').apply(lambda x: int(x[0]))
    legacy_df['minute'] = legacy_df['doc_time'].str.split(':').apply(lambda x: int(x[1]))
    legacy_df['time_min'] = legacy_df['hour'] * 60 + legacy_df['minute']
    legacy_clean = legacy_df[['pharmacy_id', 'time_min', 'line_count']].copy()
    legacy_clean['source'] = 'legacy'

    # 3. Process ERP Invoices & Fast Inverted Index Linkage
    erp_df['hour'] = erp_df['entry_time'].str.split(':').apply(lambda x: int(x[0]))
    erp_df['minute'] = erp_df['entry_time'].str.split(':').apply(lambda x: int(x[1]))
    erp_df['time_min'] = erp_df['hour'] * 60 + erp_df['minute']

    def infer_area(row):
        if pd.notnull(row['area']):
            return str(row['area']).strip()
        if pd.notnull(row['account_address']):
            addr = str(row['account_address']).lower()
            if any(k in addr for k in ['smouha', 'souha', 'msouha']):
                return 'Smouha'
            if 'nasr' in addr:
                return 'Nasr City'
            if 'faisal' in addr:
                return 'Faisal'
            if any(k in addr for k in ['mohandessin', 'mhandessin']):
                return 'Mohandessin'
        return None

    erp_df['inferred_area'] = erp_df.apply(infer_area, axis=1)

    pharma_tokens = {}
    token_to_pids = defaultdict(list)
    for _, r in pharmacies_df.iterrows():
        pid = int(r['id'])
        toks = clean_tokens(r['name'])
        pharma_tokens[pid] = {
            'area': str(r['area']).strip(),
            'tokens': toks
        }
        for t in toks:
            token_to_pids[t].append(pid)

    erp_matches = []
    unmatched_erp_count = 0
    for _, row in erp_df.iterrows():
        tokens = clean_tokens(row['account_name'])
        area = row['inferred_area']
        if not tokens:
            unmatched_erp_count += 1
            continue

        # Candidate pharmacy IDs sharing at least one token
        candidates = set()
        for t in tokens:
            for pid in token_to_pids.get(t, []):
                if area is None or pharma_tokens[pid]['area'] == area:
                    candidates.add(pid)

        best_pid = None
        best_score = 0.0
        for pid in candidates:
            p_tok = pharma_tokens[pid]['tokens']
            overlap = len(tokens.intersection(p_tok))
            if overlap > 0:
                score = overlap / len(tokens.union(p_tok))
                if score > best_score:
                    best_score = score
                    best_pid = pid

        if best_pid is not None and best_score >= 0.4:
            erp_matches.append({
                'pharmacy_id': best_pid,
                'time_min': row['time_min'],
                'gross_value': row['gross_value'],
                'source': 'erp'
            })
        else:
            unmatched_erp_count += 1

    erp_clean = pd.DataFrame(erp_matches)
    quality_metrics["erp_matched_count"] = len(erp_clean)
    quality_metrics["erp_unmatched_count"] = unmatched_erp_count
    quality_metrics["erp_match_rate"] = len(erp_clean) / len(erp_df)

    # 4. Combine All Invoices from App, Legacy, and ERP
    invoices_all = pd.concat([
        app_clean[['pharmacy_id', 'time_min', 'source']],
        legacy_clean[['pharmacy_id', 'time_min', 'source']],
        erp_clean[['pharmacy_id', 'time_min', 'source']]
    ], ignore_index=True)

    quality_metrics["invoices_combined_total"] = len(invoices_all)
    quality_metrics["invoices_unique_pharmacies"] = int(invoices_all['pharmacy_id'].nunique())

    # 5. Quantify Visit Log Quality & Validity
    visits_raw_df['arr_min'] = visits_raw_df['arrived_at'].apply(time_str_to_minutes)
    visits_raw_df['dep_min'] = visits_raw_df['departed_at'].apply(time_str_to_minutes)
    visits_raw_df['duration'] = visits_raw_df['dep_min'] - visits_raw_df['arr_min']

    quality_metrics["visits_missing_departure"] = int(visits_raw_df['departed_at'].isnull().sum())
    quality_metrics["visits_cancelled"] = int((visits_raw_df['cancelled_flag'] == 1).sum())
    quality_metrics["visits_valid_good"] = int(
        ((visits_raw_df['cancelled_flag'] == 0) & 
         (visits_raw_df['dep_min'].notnull()) & 
         (visits_raw_df['duration'] > 0)).sum()
    )

    tomorrow_full = tomorrow_df.merge(
        pharmacies_df[['id', 'name', 'status_code', 'opens_at_hh', 'closes_at_hh', 'lat', 'lon', 'phone_last4']],
        left_on='pharmacy_id',
        right_on='id',
        how='left'
    )

    return DatasetContainer(
        areas=areas_df,
        pharmacies=pharmacies_df,
        visits_raw=visits_raw_df,
        invoices_app=app_df,
        invoices_erp=erp_df,
        invoices_legacy=legacy_df,
        tomorrow=tomorrow_full,
        invoices_all=invoices_all,
        quality_metrics=quality_metrics
    )


if __name__ == "__main__":
    data = load_all_data()
    print("Data loader self-test completed successfully.")
    for k, v in data.quality_metrics.items():
        print(f"  {k}: {v}")
