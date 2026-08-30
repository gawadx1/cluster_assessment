import pandas as pd
import numpy as np

pharma = pd.read_csv('task2/dataset/pharmacy_registry.csv')
visits = pd.read_csv('task2/dataset/field_visit_log.csv')
app = pd.read_csv('task2/dataset/invoices_app.csv')
legacy = pd.read_csv('task2/dataset/invoices_legacy.csv')
erp = pd.read_csv('task2/dataset/invoices_erp.csv')
tomorrow = pd.read_csv('task2/dataset/route_plan_tomorrow.csv')

tm = tomorrow.merge(pharma[['id', 'name', 'status_code', 'area']], left_on='pharmacy_id', right_on='id')

print("Non-zero status_code stops in route_plan_tomorrow.csv:")
for _, r in tm[tm['status_code'] != 0].iterrows():
    pid = r['pharmacy_id']
    v_cnt = len(visits[visits['pharmacy_id'] == pid])
    app_cnt = len(app[app['customer_id'] == pid])
    leg_cnt = len(legacy[legacy['account_ref'] == f'P:{pid}'])
    print(f"Pharmacy {pid} ({r['name']}) [Area: {r['area_x']}, Rep: {r['rep_id']}, Prio: {r['priority']}, Status: {r['status_code']}] -> Visits: {v_cnt}, App Inv: {app_cnt}, Legacy Inv: {leg_cnt}")

print("\n--- Summary of all 64 tomorrow stops ---")
print(f"Total tomorrow stops: {len(tomorrow)}")
for area, grp in tomorrow.groupby('area'):
    p_ids = grp['pharmacy_id'].tolist()
    v_counts = [len(visits[visits['pharmacy_id'] == p]) for p in p_ids]
    print(f"Area {area}: {len(p_ids)} stops, zero-visit pharmacies: {sum(1 for v in v_counts if v == 0)}")
