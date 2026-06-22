"""
Tests for Phase 4: remote-path resolution and the optional DuckDB backend.

Network access is not exercised; only the pure URL-translation logic and the
DuckDB code path (skipped when duckdb is absent) are tested.
"""

import geopandas as gpd
import pytest
from shapely.geometry import Point

from geolint.core.duckdb_backend import can_handle, duckdb_available, quick_stats
from geolint.core.validation import is_remote, to_vsi_path


class TestRemotePaths:
    def test_is_remote(self):
        assert is_remote("s3://bucket/key.parquet")
        assert is_remote("https://example.com/data.geojson")
        assert is_remote("/vsicurl/https://x/y.gpkg")
        assert not is_remote("/local/path/data.gpkg")
        assert not is_remote("data.gpkg")

    def test_to_vsi_path(self):
        assert to_vsi_path("s3://b/k.gpkg") == "/vsis3/b/k.gpkg"
        assert to_vsi_path("gs://b/k.gpkg") == "/vsigs/b/k.gpkg"
        assert to_vsi_path("https://x/y.geojson") == "/vsicurl/https://x/y.geojson"
        assert to_vsi_path("/vsizip/foo.zip") == "/vsizip/foo.zip"
        assert to_vsi_path("/local/data.gpkg") == "/local/data.gpkg"


class TestDuckDBBackend:
    def test_can_handle_requires_duckdb_and_parquet(self):
        # gpkg is never handled regardless of duckdb availability
        assert can_handle("data.gpkg") is False
        # parquet handling tracks duckdb availability
        assert can_handle("data.parquet") == duckdb_available()

    def test_quick_stats(self, tmp_path):
        pytest.importorskip("duckdb")
        path = tmp_path / "pts.parquet"
        gpd.GeoDataFrame(
            {"id": [1, 2, 3]},
            geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
            crs="EPSG:4326",
        ).to_parquet(path)
        stats = quick_stats(path)
        assert stats["feature_count"] == 3
        assert stats["engine"] == "duckdb"
