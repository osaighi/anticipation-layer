#!/usr/bin/env python3
"""
Check anticipation files for stale/expired entries.

Parses the markdown anticipation files, computes temporal weight
for each entry, and reports which ones need attention.

Usage:
    python check_decay.py [anticipations_dir]

Output: JSON report of stale entries to stdout.
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timedelta


# Decay rates per horizon
DECAY_LAMBDA = {
    "short_term": 0.3,
    "medium_term": 0.05,
    "long_term": 0.01,
}

# TTL in hours
TTL_HOURS = {
    "short_term": 48,
    "medium_term": 336,    # 2 weeks
    "long_term": 1440,     # ~2 months
}

WEIGHT_FLOOR = 0.3
HORIZON_FILES = ["short_term.md", "medium_term.md", "long_term.md"]


def parse_anticipations(filepath: str) -> list[dict]:
    """Parse anticipation entries from a markdown file."""
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r") as f:
        content = f.read()

    entries = []
    # Split by ### headers (each anticipation starts with ### [ANT-...])
    blocks = re.split(r'^### ', content, flags=re.MULTILINE)

    for block in blocks:
        if not block.strip() or not block.startswith("[ANT-"):
            continue

        entry = {"raw": "### " + block}

        # Extract ID
        id_match = re.match(r'\[(ANT-[\w-]+)\]', block)
        if id_match:
            entry["id"] = id_match.group(1)

        # Extract fields
        for field in ["Status", "Created", "Expires", "Confidence", "Category", "Impact", "Domain"]:
            match = re.search(rf'\*\*{field}\*\*:\s*(.+)', block)
            if match:
                entry[field.lower()] = match.group(1).strip()

        # Extract prediction
        pred_match = re.search(r'\*\*Prediction\*\*:\s*(.+?)(?=\n\*\*|\Z)', block, re.DOTALL)
        if pred_match:
            entry["prediction"] = pred_match.group(1).strip()

        entries.append(entry)

    return entries


def compute_weight(entry: dict, horizon: str) -> float:
    """Compute the current weight of an anticipation."""
    confidence = float(entry.get("confidence", 0.5))
    created_str = entry.get("created", "")

    if not created_str:
        return confidence  # Can't compute decay without timestamp

    try:
        created = datetime.fromisoformat(created_str.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return confidence

    age_days = (datetime.utcnow() - created).total_seconds() / 86400
    lam = DECAY_LAMBDA.get(horizon, 0.1)

    impact_mult = {
        "low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0
    }.get(entry.get("impact", "medium"), 0.5)

    return confidence * math.exp(-lam * age_days) * impact_mult


def check_expired(entry: dict) -> bool:
    """Check if an anticipation has passed its expiry date."""
    expires_str = entry.get("expires", "")
    if not expires_str:
        return False
    try:
        expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00").replace("+00:00", ""))
        return datetime.utcnow() > expires
    except ValueError:
        return False


def check_horizon_stale(meta: dict, horizon: str) -> bool:
    """Check if a whole horizon file needs refresh based on last update time."""
    last_refresh = meta.get("last_refresh", {}).get(horizon)
    if not last_refresh:
        return True

    try:
        last = datetime.fromisoformat(last_refresh.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return True

    ttl = timedelta(hours=TTL_HOURS.get(horizon, 48))
    return datetime.utcnow() > last + ttl


def main(ant_dir: str = ".anticipations"):
    if not os.path.exists(ant_dir):
        print(json.dumps({"error": f"Directory {ant_dir} not found"}))
        sys.exit(1)

    # Load meta
    meta_path = os.path.join(ant_dir, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "stale_horizons": [],
        "expired_entries": [],
        "low_weight_entries": [],
        "healthy_entries": 0,
    }

    for horizon in ["short_term", "medium_term", "long_term"]:
        # Check if whole horizon is stale
        if check_horizon_stale(meta, horizon):
            report["stale_horizons"].append(horizon)

        # Check individual entries
        filepath = os.path.join(ant_dir, f"{horizon}.md")
        entries = parse_anticipations(filepath)

        for entry in entries:
            if entry.get("status", "active") != "active":
                continue

            if check_expired(entry):
                report["expired_entries"].append({
                    "id": entry.get("id", "unknown"),
                    "horizon": horizon,
                    "prediction": entry.get("prediction", "")[:80],
                    "expires": entry.get("expires", ""),
                })
            else:
                weight = compute_weight(entry, horizon)
                if weight < WEIGHT_FLOOR:
                    report["low_weight_entries"].append({
                        "id": entry.get("id", "unknown"),
                        "horizon": horizon,
                        "prediction": entry.get("prediction", "")[:80],
                        "weight": round(weight, 3),
                    })
                else:
                    report["healthy_entries"] += 1

    print(json.dumps(report, indent=2))

    # Summary to stderr for human readability
    total_issues = len(report["stale_horizons"]) + len(report["expired_entries"]) + len(report["low_weight_entries"])
    print(f"\n--- Decay Check Summary ---", file=sys.stderr)
    print(f"Healthy entries: {report['healthy_entries']}", file=sys.stderr)
    print(f"Stale horizons: {', '.join(report['stale_horizons']) or 'none'}", file=sys.stderr)
    print(f"Expired entries: {len(report['expired_entries'])}", file=sys.stderr)
    print(f"Low-weight entries: {len(report['low_weight_entries'])}", file=sys.stderr)

    if total_issues > 0:
        print(f"\n⚠️  {total_issues} issue(s) found. Consider running consolidation.", file=sys.stderr)
    else:
        print(f"\n✅ All anticipations are healthy.", file=sys.stderr)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else ".anticipations"
    main(d)
