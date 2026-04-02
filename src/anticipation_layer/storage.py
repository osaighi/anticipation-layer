"""
File-based storage backend for anticipations.

Stores anticipations as JSON files organized by horizon,
with an invalidation log and metadata file.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Anticipation, Horizon, Status


class Storage:
    """
    File-based storage for anticipations.

    Directory layout:
        storage_dir/
        ├── short_term.json
        ├── medium_term.json
        ├── long_term.json
        ├── invalidations.log
        ├── meta.json
        └── archives/
    """

    def __init__(self, storage_dir: str = "./anticipations"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "archives").mkdir(exist_ok=True)
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Create storage files if they don't exist."""
        for horizon in Horizon:
            path = self.storage_dir / f"{horizon.value}.json"
            if not path.exists():
                path.write_text(json.dumps([], indent=2))

        meta_path = self.storage_dir / "meta.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps({
                "created": datetime.utcnow().isoformat(),
                "last_consolidation": None,
                "total_generated": 0,
                "total_invalidated": 0,
                "total_realized": 0,
                "total_expired": 0,
            }, indent=2))

        log_path = self.storage_dir / "invalidations.log"
        if not log_path.exists():
            log_path.touch()

    def load_horizon(self, horizon: Horizon) -> list[Anticipation]:
        """Load all anticipations for a given horizon."""
        path = self.storage_dir / f"{horizon.value}.json"
        data = json.loads(path.read_text())
        return [Anticipation.from_dict(entry) for entry in data]

    def load_all_active(self) -> list[Anticipation]:
        """Load all active anticipations across all horizons."""
        result = []
        for horizon in Horizon:
            anticipations = self.load_horizon(horizon)
            result.extend(a for a in anticipations if a.status == Status.ACTIVE)
        return result

    def save_horizon(self, horizon: Horizon, anticipations: list[Anticipation]) -> None:
        """Save anticipations for a given horizon."""
        path = self.storage_dir / f"{horizon.value}.json"
        data = [a.to_dict() for a in anticipations]
        path.write_text(json.dumps(data, indent=2))

    def add(self, anticipation: Anticipation) -> None:
        """Add a single anticipation to the appropriate horizon file."""
        anticipations = self.load_horizon(anticipation.horizon)
        anticipations.append(anticipation)
        self.save_horizon(anticipation.horizon, anticipations)
        self._increment_meta("total_generated")

    def update(self, anticipation: Anticipation) -> None:
        """Update an existing anticipation in storage."""
        anticipations = self.load_horizon(anticipation.horizon)
        for i, a in enumerate(anticipations):
            if a.id == anticipation.id:
                anticipations[i] = anticipation
                break
        self.save_horizon(anticipation.horizon, anticipations)

    def log_invalidation(self, anticipation: Anticipation, event: str) -> None:
        """Append an invalidation entry to the log."""
        log_path = self.storage_dir / "invalidations.log"
        entry = (
            f"[{datetime.utcnow().isoformat()}] "
            f"ID={anticipation.id} | "
            f"PREDICTION=\"{anticipation.prediction[:80]}\" | "
            f"EVENT=\"{event}\" | "
            f"CONFIDENCE_WAS={anticipation.confidence:.2f}\n"
        )
        with open(log_path, "a") as f:
            f.write(entry)
        self._increment_meta("total_invalidated")

    def archive_horizon(self, horizon: Horizon) -> None:
        """Move non-active anticipations to the archive."""
        anticipations = self.load_horizon(horizon)
        active = [a for a in anticipations if a.status == Status.ACTIVE]
        archived = [a for a in anticipations if a.status != Status.ACTIVE]

        if archived:
            quarter = f"{datetime.utcnow().year}-Q{(datetime.utcnow().month - 1) // 3 + 1}"
            archive_dir = self.storage_dir / "archives" / quarter
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / f"{horizon.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            archive_path.write_text(json.dumps([a.to_dict() for a in archived], indent=2))

        self.save_horizon(horizon, active)

    def get_meta(self) -> dict:
        """Read metadata."""
        meta_path = self.storage_dir / "meta.json"
        return json.loads(meta_path.read_text())

    def update_meta(self, updates: dict) -> None:
        """Update metadata fields."""
        meta = self.get_meta()
        meta.update(updates)
        meta_path = self.storage_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))

    def _increment_meta(self, field: str) -> None:
        """Increment a counter in metadata."""
        meta = self.get_meta()
        meta[field] = meta.get(field, 0) + 1
        self.update_meta(meta)
