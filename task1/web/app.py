"""Flask website for Task 1 clean data browsing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

TASK1_ROOT = Path(__file__).resolve().parent.parent
if str(TASK1_ROOT) not in sys.path:
    sys.path.insert(0, str(TASK1_ROOT))

from pipeline.analytics import filter_analytics

OUTPUT_DIR = TASK1_ROOT / "output"
ANALYTICS_PATH = OUTPUT_DIR / "analytics.json"

app = Flask(__name__, template_folder="templates", static_folder="static")


def load_analytics() -> dict:
    if not ANALYTICS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {ANALYTICS_PATH}. Run the pipeline first (run_pipeline.py)."
        )
    with ANALYTICS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/summary")
def api_summary():
    data = load_analytics()
    date_start = request.args.get("date_start")
    date_end = request.args.get("date_end")
    area = request.args.get("area") or None
    if date_start or date_end or area:
        data = filter_analytics(data, date_start, date_end, area)
    # This is a view-level measure derived from the same generated ledger used
    # for supplier revenue. It is not a new cleaning or matching rule.
    supplier_pharmacies = {}
    for row in data.get("ledger", []):
        key = (row.get("supplier_key"), row.get("supplier_name"))
        supplier_pharmacies.setdefault(key, set()).add(row.get("pharmacy_id"))
    top_suppliers = []
    for row in data["top_suppliers"]:
        item = dict(row)
        item["pharmacies_served"] = len(supplier_pharmacies.get((row.get("supplier_key"), row.get("supplier_name")), set()))
        top_suppliers.append(item)
    return jsonify(
        {
            "meta": data["meta"],
            "summary": data["summary"],
            "pharmacies_per_area": data["pharmacies_per_area"],
            "revenue_per_area": data["revenue_per_area"],
            "top_pharmacies": data["top_pharmacies"],
            "top_pharmacies_by_area": data["top_pharmacies_by_area"],
            "top_suppliers": top_suppliers,
            "data_quality": data.get("data_quality", {}),
            "cleaning_impact": data.get("summary", {}).get("revenue_impacts", []),
        }
    )


@app.route("/api/pharmacies")
def api_pharmacies():
    data = load_analytics()
    area = request.args.get("area") or None
    if area == "All areas":
        area = None
    pharmacies = data["pharmacies"]
    if area:
        pharmacies = [p for p in pharmacies if p.get("resolved_area") == area]
    q = (request.args.get("q") or "").lower()
    if q:
        pharmacies = [p for p in pharmacies if q in (p.get("canonical_name") or "").lower()]
    return jsonify(pharmacies)


@app.route("/api/pharmacy/<int:pharmacy_id>")
def api_pharmacy(pharmacy_id: int):
    data = load_analytics()
    date_start = request.args.get("date_start")
    date_end = request.args.get("date_end")

    for p in data["pharmacies"]:
        if p["pharmacy_id"] == pharmacy_id:
            result = dict(p)
            if date_start or date_end:
                import pandas as pd

                ledger = pd.DataFrame(data["ledger"])
                ledger = ledger[ledger["pharmacy_id"] == pharmacy_id]
                ledger["order_date"] = pd.to_datetime(ledger["order_date"])
                if date_start:
                    ledger = ledger[ledger["order_date"] >= pd.Timestamp(date_start)]
                if date_end:
                    ledger = ledger[ledger["order_date"] < (pd.Timestamp(date_end) + pd.Timedelta(days=1))]
                result["total_revenue_egp"] = float(ledger["revenue_egp"].sum())
                result["order_count"] = int(len(ledger))
                ts = (
                    ledger.groupby(ledger["order_date"].dt.to_period("M").astype(str))["revenue_egp"]
                    .sum()
                    .reset_index()
                    .rename(columns={"order_date": "month", "revenue_egp": "revenue_egp"})
                )
                result["revenue_by_month"] = ts.to_dict(orient="records")
            return jsonify(result)
    return jsonify({"error": "not found"}), 404


@app.route("/api/unmatched")
def api_unmatched():
    data = load_analytics()
    return jsonify(
        {
            "unmatched_aliases_sample": data.get("unmatched_aliases_sample", []),
            "unmatched_erp_sample": data.get("unmatched_erp_sample", []),
            "summary": data["summary"],
        }
    )


def main():
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
