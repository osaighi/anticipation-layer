#!/usr/bin/env python3
"""
Initialize the .anticipations/ directory structure.

Usage:
    python init.py [project_root]

If project_root is not provided, uses the current directory.
"""

import json
import os
import sys
from datetime import datetime


TEMPLATE_HEADER = """# {title}
# Horizon: {horizon_desc}
# Last updated: {timestamp}

"""

HORIZONS = {
    "short_term": {
        "title": "Short Term Anticipations",
        "desc": "1-7 days ahead — tactical, immediate concerns",
        "filename": "short_term.md",
    },
    "medium_term": {
        "title": "Medium Term Anticipations",
        "desc": "1-3 months ahead — strategic, project-level developments",
        "filename": "medium_term.md",
    },
    "long_term": {
        "title": "Long Term Anticipations",
        "desc": "6-12 months ahead — vision, trends, structural changes",
        "filename": "long_term.md",
    },
}

META_TEMPLATE = {
    "initialized": None,
    "last_consolidation": None,
    "last_refresh": {
        "short_term": None,
        "medium_term": None,
        "long_term": None,
    },
    "stats": {
        "total_generated": 0,
        "total_invalidated": 0,
        "total_realized": 0,
        "total_expired": 0,
    },
    "config": {
        "decay_lambda": {
            "short_term": 0.3,
            "medium_term": 0.05,
            "long_term": 0.01,
        },
        "ttl_hours": {
            "short_term": 48,
            "medium_term": 336,
            "long_term": 1440,
        },
        "cascade_thresholds": {
            "short_to_medium": 0.3,
            "medium_to_long": 0.5,
        },
    },
}


def init(project_root: str = "."):
    ant_dir = os.path.join(project_root, ".anticipations")
    archive_dir = os.path.join(ant_dir, "archive")

    if os.path.exists(ant_dir):
        print(f"[anticipation-layer] .anticipations/ already exists at {ant_dir}")
        print("[anticipation-layer] Use --force to reinitialize (will not delete existing data)")
        if "--force" not in sys.argv:
            return

    os.makedirs(ant_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    now = datetime.utcnow().isoformat() + "Z"

    # Create horizon files
    for key, info in HORIZONS.items():
        filepath = os.path.join(ant_dir, info["filename"])
        if not os.path.exists(filepath):
            content = TEMPLATE_HEADER.format(
                title=info["title"],
                horizon_desc=info["desc"],
                timestamp=now,
            )
            content += "<!-- No anticipations yet. They will be generated on first use. -->\n"
            with open(filepath, "w") as f:
                f.write(content)
            print(f"[anticipation-layer] Created {info['filename']}")

    # Create meta.json
    meta_path = os.path.join(ant_dir, "meta.json")
    if not os.path.exists(meta_path):
        meta = META_TEMPLATE.copy()
        meta["initialized"] = now
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[anticipation-layer] Created meta.json")

    # Add to .gitignore if it exists
    gitignore_path = os.path.join(project_root, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            content = f.read()
        if ".anticipations/" not in content:
            with open(gitignore_path, "a") as f:
                f.write("\n# Anticipation Layer (agent temporal awareness)\n.anticipations/\n")
            print("[anticipation-layer] Added .anticipations/ to .gitignore")

    print(f"[anticipation-layer] Initialized at {ant_dir}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "."
    init(root)
