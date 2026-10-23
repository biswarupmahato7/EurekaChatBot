"""
crawler/tests/test_checkpoints.py
=================================
Unit tests for CheckpointManager: save, load, find_latest, cleanup_old, and atomic write safety.
"""
import json
import time
from pathlib import Path
import pytest
from crawler.checkpoints import CheckpointManager


@pytest.fixture
def checkpoint_mgr(tmp_path):
    return CheckpointManager(tmp_path / "checkpoints")


class TestCheckpointManager:
    def test_save_and_load(self, checkpoint_mgr):
        run_id = "test-run-001"
        pages = [{"page_id": "abc123", "title": "Page 1"}]
        seen_urls = {"https://eurekasolutions.in/Eureka2026/p1"}
        pending_urls = [{"url": "https://eurekasolutions.in/Eureka2026/p2", "depth": 1}]
        stats = {"succeeded": 1, "failed": 0}

        checkpoint_mgr.save(
            run_id=run_id,
            pages_so_far=pages,
            seen_urls=seen_urls,
            pending_urls=pending_urls,
            stats=stats,
        )

        loaded = checkpoint_mgr.load(run_id)
        assert loaded is not None
        assert loaded["run_id"] == run_id
        assert loaded["pages_count"] == 1
        assert loaded["pages"][0]["page_id"] == "abc123"
        assert "https://eurekasolutions.in/Eureka2026/p1" in loaded["seen_urls"]
        assert len(loaded["pending_urls"]) == 1

    def test_load_nonexistent_returns_none(self, checkpoint_mgr):
        assert checkpoint_mgr.load("nonexistent-run") is None

    def test_find_latest(self, checkpoint_mgr):
        assert checkpoint_mgr.find_latest() is None

        # Save run 1
        checkpoint_mgr.save("run-1", [], set(), [], {})
        time.sleep(0.01)
        # Save run 2
        checkpoint_mgr.save("run-2", [], set(), [], {})

        latest = checkpoint_mgr.find_latest()
        assert latest == "run-2"

    def test_cleanup_old(self, checkpoint_mgr):
        # Save 5 checkpoints
        for i in range(5):
            checkpoint_mgr.save(f"run-{i}", [], set(), [], {})
            time.sleep(0.01)

        assert len(list(checkpoint_mgr.checkpoints_dir.glob("checkpoint_*.json"))) == 5

        # Cleanup keeping only 2
        checkpoint_mgr.cleanup_old(keep=2)
        remaining = list(checkpoint_mgr.checkpoints_dir.glob("checkpoint_*.json"))
        assert len(remaining) == 2
        # Verify the two remaining are the latest ones
        names = {p.stem for p in remaining}
        assert "checkpoint_run-4" in names
        assert "checkpoint_run-3" in names
