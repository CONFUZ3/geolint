"""
Tests for the GeoLint CLI (geolint.cli.main).

The CLI is invoked as a subprocess using the project's venv interpreter so the
end-to-end exit codes and JSON contract are exercised exactly as a user would.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

PYTHON = r"E:/cursor/geolint/.venv/Scripts/python.exe"


def _run_validate(path):
    """Run `geolint validate <path> --json` and return the CompletedProcess."""
    return subprocess.run(
        [PYTHON, "-m", "geolint.cli.main", "validate", str(path), "--json"],
        capture_output=True,
        text=True,
    )


class TestCliValidate:
    """Test the validate subcommand via subprocess."""

    def test_clean_geojson_returns_zero_and_json(self):
        with tempfile.NamedTemporaryFile(suffix='.geojson', delete=False) as tmp_file:
            geojson_path = Path(tmp_file.name)

        try:
            gdf = gpd.GeoDataFrame(
                {'id': [1, 2, 3], 'geometry': [Point(0, 0), Point(1, 1), Point(2, 2)]},
                crs='EPSG:4326'
            )
            gdf.to_file(geojson_path, driver='GeoJSON')

            result = _run_validate(geojson_path)

            assert result.returncode == 0
            payload = json.loads(result.stdout)
            assert 'health_score' in payload
            assert 'checks' in payload
        finally:
            geojson_path.unlink(missing_ok=True)

    def test_quality_issues_warns_but_succeeds(self):
        with tempfile.NamedTemporaryFile(suffix='.geojson', delete=False) as tmp_file:
            geojson_path = Path(tmp_file.name)

        try:
            gdf = gpd.GeoDataFrame(
                {
                    'id': [1, 2, 2],  # duplicate id
                    'geometry': [Point(10, 5), Point(200, 5), Point(20, 5)]  # lon=200 out of range
                },
                crs='EPSG:4326'
            )
            gdf.to_file(geojson_path, driver='GeoJSON')

            result = _run_validate(geojson_path)

            assert result.returncode == 0
            payload = json.loads(result.stdout)
            assert payload['health_score'] < 100
        finally:
            geojson_path.unlink(missing_ok=True)

    def test_corrupt_file_returns_one(self):
        with tempfile.NamedTemporaryFile(suffix='.geojson', delete=False) as tmp_file:
            geojson_path = Path(tmp_file.name)
            geojson_path.write_text("not a geo file")

        try:
            result = _run_validate(geojson_path)
            assert result.returncode == 1
        finally:
            geojson_path.unlink(missing_ok=True)

    def test_nonexistent_path_returns_one(self):
        result = _run_validate("definitely_does_not_exist_12345.geojson")
        assert result.returncode == 1
