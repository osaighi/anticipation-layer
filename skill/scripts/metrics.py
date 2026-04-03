#!/usr/bin/env python3
"""
Metrics reporter for the Anticipation Layer.

Analyzes archive data and current state to compute performance metrics:
- Realization rate: how often predictions came true
- Invalidation rate: how often predictions were wrong
- Calibration: are confidence scores accurate?
- Temporal bias: over/under-estimation by horizon

Usage:
    python metrics.py [anticipations_dir]
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime


def scan_files_for_entries(directory: str) -> list[dict]:
    """
    Scan anticipation JSON files and return a flat list of entry dicts.

    Reads the three horizon files (short_term.json, medium_term.json,
    long_term.json) plus all JSON files under archives/.
    Each entry already contains 'id', 'status', 'confidence', 'category',
    'impact', and 'horizon' fields — no parsing needed.
    """
    entries = []
    horizon_files = ["short_term.json", "medium_term.json", "long_term.json"]

    # Current horizon files
    for filename in horizon_files:
        filepath = os.path.join(directory, filename)
        if not os.path.exists(filepath):
            continue
        with open(filepath, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
        for entry in data:
            entries.append(entry)

    # Archived files under archives/
    archives_dir = os.path.join(directory, "archives")
    if os.path.isdir(archives_dir):
        for root, dirs, files in os.walk(archives_dir):
            for filename in files:
                if not filename.endswith(".json"):
                    continue
                filepath = os.path.join(root, filename)
                with open(filepath, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        continue
                for entry in data:
                    entries.append(entry)

    return entries


def compute_metrics(entries: list[dict], meta: dict) -> dict:
    """Compute all performance metrics."""
    total = len(entries)
    if total == 0:
        return {"error": "No entries found"}

    by_status = defaultdict(int)
    by_horizon = defaultdict(lambda: defaultdict(int))
    confidence_buckets = defaultdict(lambda: {"total": 0, "realized": 0})

    for entry in entries:
        status = entry.get("status", "unknown")
        horizon = entry.get("horizon", "unknown")
        confidence = float(entry.get("confidence", 0.5))

        by_status[status] += 1
        by_horizon[horizon][status] += 1

        # Bucket confidence into 10% bands
        bucket = round(confidence, 1)
        confidence_buckets[bucket]["total"] += 1
        if status == "realized":
            confidence_buckets[bucket]["realized"] += 1

    realized = by_status.get("realized", 0)
    invalidated = by_status.get("invalidated", 0)
    expired = by_status.get("expired", 0)
    active = by_status.get("active", 0)
    resolved = realized + invalidated + expired  # entries with known outcomes

    metrics = {
        "overview": {
            "total_entries": total,
            "active": active,
            "realized": realized,
            "invalidated": invalidated,
            "expired": expired,
        },
        "rates": {
            "realization_rate": round(realized / resolved, 3) if resolved > 0 else None,
            "invalidation_rate": round(invalidated / resolved, 3) if resolved > 0 else None,
            "expiry_rate": round(expired / resolved, 3) if resolved > 0 else None,
        },
        "by_horizon": {},
        "calibration": {},
    }

    # Per-horizon breakdown
    for horizon in ["short_term", "medium_term", "long_term"]:
        h_data = by_horizon.get(horizon, {})
        h_total = sum(h_data.values())
        h_realized = h_data.get("realized", 0)
        h_invalidated = h_data.get("invalidated", 0)
        h_resolved = h_realized + h_invalidated + h_data.get("expired", 0)

        metrics["by_horizon"][horizon] = {
            "total": h_total,
            "active": h_data.get("active", 0),
            "realized": h_realized,
            "invalidated": h_invalidated,
            "realization_rate": round(h_realized / h_resolved, 3) if h_resolved > 0 else None,
        }

    # Calibration: for each confidence bucket, what % actually realized?
    for bucket in sorted(confidence_buckets.keys()):
        data = confidence_buckets[bucket]
        actual_rate = data["realized"] / data["total"] if data["total"] > 0 else 0
        metrics["calibration"][f"{bucket:.0%}"] = {
            "expected": bucket,
            "actual": round(actual_rate, 3),
            "sample_size": data["total"],
            "gap": round(abs(bucket - actual_rate), 3),
        }

    # Meta stats
    metrics["meta"] = {
        "initialized": meta.get("initialized"),
        "last_consolidation": meta.get("last_consolidation"),
        "from_meta": meta.get("stats", {}),
    }

    return metrics


def print_report(metrics: dict):
    """Pretty-print the metrics report."""
    if "error" in metrics:
        print(f"Error: {metrics['error']}")
        return

    ov = metrics["overview"]
    rates = metrics["rates"]

    print("=" * 50)
    print("  ANTICIPATION LAYER — PERFORMANCE METRICS")
    print("=" * 50)

    print(f"\n📊 Overview")
    print(f"  Total entries:  {ov['total_entries']}")
    print(f"  Active:         {ov['active']}")
    print(f"  Realized:       {ov['realized']}")
    print(f"  Invalidated:    {ov['invalidated']}")
    print(f"  Expired:        {ov['expired']}")

    print(f"\n📈 Rates")
    for key, val in rates.items():
        label = key.replace("_", " ").title()
        print(f"  {label}: {val:.1%}" if val is not None else f"  {label}: N/A")

    print(f"\n🔭 By Horizon")
    for horizon, data in metrics["by_horizon"].items():
        label = horizon.replace("_", " ").title()
        rate_str = f"{data['realization_rate']:.1%}" if data["realization_rate"] is not None else "N/A"
        print(f"  {label}: {data['total']} total, {data['active']} active, realization={rate_str}")

    if metrics["calibration"]:
        print(f"\n🎯 Calibration (confidence vs reality)")
        for bucket, data in metrics["calibration"].items():
            bar = "█" * int(data["actual"] * 20) + "░" * (20 - int(data["actual"] * 20))
            print(f"  {bucket:>4s} conf → {data['actual']:.0%} actual [{bar}] (n={data['sample_size']})")

    print()


def main(ant_dir: str = ".anticipations"):
    if not os.path.exists(ant_dir):
        print(f"Error: {ant_dir} not found.", file=sys.stderr)
        sys.exit(1)

    # Scan all entries (active + archived)
    entries = scan_files_for_entries(ant_dir)

    # Load meta
    meta = {}
    meta_path = os.path.join(ant_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)

    metrics = compute_metrics(entries, meta)

    # JSON to stdout
    print(json.dumps(metrics, indent=2))

    # Human-readable to stderr
    print_report(metrics)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else ".anticipations"
    main(d)
