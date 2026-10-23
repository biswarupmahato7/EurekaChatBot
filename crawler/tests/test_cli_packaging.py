"""
crawler/tests/test_cli_packaging.py
===================================
Unit and smoke tests for CLI entry points (--help, argument parsing)
and ZIP packaging creation and verification.
"""
import subprocess
import sys
import zipfile
from pathlib import Path
import pytest
from crawler.packaging import create_zip_archive, verify_zip_archive

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestCliEntryPoints:
    @pytest.mark.parametrize("module", [
        "crawler.cli.crawl_website",
        "crawler.cli.validate_data",
        "crawler.cli.create_chunks",
        "crawler.cli.run_pipeline",
        "crawler.cli.package_data",
    ])
    def test_cli_help(self, module):
        res = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert res.returncode == 0
        assert "usage:" in res.stdout.lower() or "options:" in res.stdout.lower()


class TestPackaging:
    def test_create_and_verify_zip(self, tmp_path):
        zip_out = tmp_path / "eureka-rag-data.zip"
        created = create_zip_archive(zip_out, PROJECT_ROOT)
        assert created.exists()

        result = verify_zip_archive(created)
        assert result["valid"] is True, f"Zip verification failed: {result}"
        assert result["total_files"] > 10
        assert result["prohibited_found"] == []
        assert result["missing_required"] == []
        assert result["corrupted_json"] == []

    def test_verify_detects_prohibited_items(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr(".env", "GROQ_API_KEY=secret")
            zf.writestr("crawler/pipeline.py", "# code")

        result = verify_zip_archive(bad_zip)
        assert result["valid"] is False
        assert any(".env" in p for p in result["prohibited_found"])

    def test_verify_detects_corrupt_json(self, tmp_path):
        bad_zip = tmp_path / "bad_json.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("crawler/pipeline.py", "# code")
            zf.writestr("data.json", "{broken json")

        result = verify_zip_archive(bad_zip)
        assert result["valid"] is False
        assert len(result["corrupted_json"]) > 0
