#!/usr/bin/env python3
"""
Consolidation script — the agent's "sleep cycle".

Archives non-active anticipations, updates meta.json timestamps,
and reports what needs regeneration.

Usage:
    python consolidate.py [anticipations_dir]

This script handles the mechanical parts of consolidation.
The actual regeneration of anticipations is done by Claude
after reading this script's output.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime


def parse_entries(filepath: str) -> list[dict]:
    """Parse anticipation entries, returning raw blocks with extracted status."""
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r") as f:
        content = f.read()

    entries = []
    blocks = re.split(r'(?=^### \[ANT-)', content, flags=re.MULTILINE)

    for block in blocks:
        if not block.strip().startswith("### [ANT-"):
            continue

        status_match = re.search(r'\*\*Status\*\*:\s*(\w+)', block)
        status = status_match.group(1) if status_match else "active"

        id_match = re.match(r'### \[(ANT-[\w-]+)\]', block.strip())
        entry_id = id_match.group(1) if id_match else "unknown"

        entries.append({
            "id": entry_id,
            "status": status,
            "raw": block,
        })

    return entries


def get_header(filepath: str) -> str:
    """Extract the file header (everything before the first ### entry)."""
    if not os.path.exists(filepath):
        return ""

    with open(filepath, "r") as f:
        content = f.read()

    match = re.split(r'(?=^### \[ANT-)', content, maxsplit=1, flags=re.MULTILINE)
    return match[0] if match else ""


def archive_entries(ant_dir: str, horizon: str, entries: list[dict]) -> int:
    """Move non-active entries to the archive directory."""
    non_active = [e for e in entries if e["status"] != "active"]
    if not non_active:
        return 0

    quarter = f"{datetime.utcnow().year}-Q{(datetime.utcnow().month - 1) // 3 + 1}"
    archive_dir = os.path.join(ant_dir, "archive", quarter)
    os.makedirs(archive_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(archive_dir, f"{horizon}_{timestamp}.md")

    with open(archive_path, "w") as f:
        f.write(f"# Archived {horizon} anticipations\n")
        f.write(f"# Archived on: {datetime.utcnow().isoformat()}Z\n\n")
        for entry in non_active:
            f.write(entry["raw"])
            f.write("\n")

    return len(non_active)


def rewrite_horizon_file(ant_dir: str, horizon: str, entries: list[dict]) -> int:
    """Rewrite horizon file keeping only active entries."""
    filepath = os.path.join(ant_dir, f"{horizon}.md")
    header = get_header(filepath)
    active = [e for e in entries if e["status"] == "active"]

    # Update header timestamp
    header = re.sub(
        r'# Last updated: .+',
        f'# Last updated: {datetime.utcnow().isoformat()}Z',
        header
    )

    with open(filepath, "w") as f:
        f.write(header)
        for entry in active:
            f.write(entry["raw"])
            f.write("\n")

    return len(active)


def update_meta(ant_dir: str, stats: dict):
    """Update meta.json with consolidation results."""
    meta_path = os.path.join(ant_dir, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)

    now = datetime.utcnow().isoformat() + "Z"
    meta["last_consolidation"] = now

    # Update stats
    if "stats" not in meta:
        meta["stats"] = {}
    for key, value in stats.items():
        meta["stats"][key] = meta["stats"].get(key, 0) + value

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def main(ant_dir: str = ".anticipations"):
    if not os.path.exists(ant_dir):
        print(f"Error: {ant_dir} not found. Run init.py first.", file=sys.stderr)
        sys.exit(1)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "archived": {},
        "remaining_active": {},
        "needs_regeneration": [],
    }

    total_archived = 0

    for horizon in ["short_term", "medium_term", "long_term"]:
        filepath = os.path.join(ant_dir, f"{horizon}.md")
        entries = parse_entries(filepath)

        # Archive non-active
        archived = archive_entries(ant_dir, horizon, entries)
        total_archived += archived
        report["archived"][horizon] = archived

        # Rewrite file with only active entries
        active_count = rewrite_horizon_file(ant_dir, horizon, entries)
        report["remaining_active"][horizon] = active_count

        # Flag horizons that need new anticipations
        if active_count < 3:
            report["needs_regeneration"].append({
                "horizon": horizon,
                "current_count": active_count,
                "needed": 3 - active_count,
            })

    # Update meta
    update_meta(ant_dir, {"total_archived_this_cycle": total_archived})

    # Output
    print(json.dumps(report, indent=2))

    print(f"\n--- Consolidation Summary ---", file=sys.stderr)
    for horizon in ["short_term", "medium_term", "long_term"]:
        a = report["archived"].get(horizon, 0)
        r = report["remaining_active"].get(horizon, 0)
        print(f"  {horizon}: {a} archived, {r} active remaining", file=sys.stderr)

    if report["needs_regeneration"]:
        print(f"\n⚠️  Regeneration needed:", file=sys.stderr)
        for item in report["needs_regeneration"]:
            print(f"  {item['horizon']}: needs {item['needed']} new anticipation(s)", file=sys.stderr)
    else:
        print(f"\n✅ All horizons have sufficient anticipations.", file=sys.stderr)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else ".anticipations"
    main(d)
