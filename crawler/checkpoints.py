"""
crawler/checkpoints.py
======================
Checkpoint management for resumable crawl runs.

Checkpoints store:
- The current crawl run_id
- All page records successfully processed so far
- The discovery queue state (seen set + remaining queue)
- Crawl statistics at time of checkpoint

A checkpoint is written atomically. If a run is interrupted, the next
run can resume from the checkpoint rather than starting from scratch.
The previous valid dataset is never deleted until a new complete dataset
is validated and atomically renamed.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Save and restore crawl checkpoints.

    Checkpoint files are named:
        <checkpoints_dir>/checkpoint_<run_id>.json
    """

    def __init__(self, checkpoints_dir: str | Path) -> None:
        self.checkpoints_dir = Path(checkpoints_dir)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _checkpoint_path(self, run_id: str) -> Path:
        return self.checkpoints_dir / f"checkpoint_{run_id}.json"

    def save(
        self,
        run_id: str,
        pages_so_far: list[dict[str, Any]],
        seen_urls: set[str],
        pending_urls: list[dict[str, Any]],
        stats: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Atomically save a checkpoint."""
        data = {
            "checkpoint_version": "1.0",
            "run_id": run_id,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pages_count": len(pages_so_far),
            "pages": pages_so_far,
            "seen_urls": sorted(seen_urls),
            "pending_urls": pending_urls,
            "stats": stats,
            "extra": extra or {},
        }
        path = self._checkpoint_path(run_id)
        self._atomic_write_json(path, data)
        logger.debug("Checkpoint saved: %s (%d pages)", path.name, len(pages_so_far))

    def load(self, run_id: str) -> Optional[dict[str, Any]]:
        """Load a checkpoint. Returns None if not found or invalid."""
        path = self._checkpoint_path(run_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded checkpoint %s (%d pages)", path.name, data.get("pages_count", 0))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load checkpoint %s: %s", path.name, exc)
            return None

    def find_latest(self) -> Optional[str]:
        """Return the run_id of the most recent checkpoint, or None."""
        checkpoints = sorted(
            self.checkpoints_dir.glob("checkpoint_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not checkpoints:
            return None
        name = checkpoints[0].stem  # "checkpoint_<run_id>"
        return name.removeprefix("checkpoint_")

    def cleanup_old(self, keep: int = 3) -> None:
        """Remove all but the most recent `keep` checkpoint files."""
        checkpoints = sorted(
            self.checkpoints_dir.glob("checkpoint_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in checkpoints[keep:]:
            try:
                old.unlink()
                logger.debug("Removed old checkpoint: %s", old.name)
            except OSError as exc:
                logger.warning("Could not remove checkpoint %s: %s", old.name, exc)

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        """Write JSON atomically: write temp → rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=".tmp_ckpt_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
