"""
scripts/export_openapi.py
=========================
Reproducible script to export FastAPI OpenAPI JSON schema.
Usage:
    python scripts/export_openapi.py [output_path]
"""
import json
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.app.main import app  # noqa: E402


def export_openapi(output_path: Path) -> None:
    """Generate and write the OpenAPI specification to disk as formatted JSON."""
    openapi_schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"Exported OpenAPI schema to {output_path} ({len(json.dumps(openapi_schema))} bytes)")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root_dir / "docs" / "openapi.json"
    export_openapi(out)
