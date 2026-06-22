"""
Tests for Phase 1C: spec conformance profiles.
"""

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, box

from geolint.core.profiles import list_profiles, run_profile
from geolint.core.validation import run_validation


def _gdf(geoms, crs='EPSG:4326'):
    return gpd.GeoDataFrame({'id': range(len(geoms)), 'geometry': geoms}, crs=crs)


class TestProfileRegistry:
    def test_list_profiles(self):
        names = {p['name'] for p in list_profiles()}
        assert names == {'rfc7946', 'geopackage', 'geoparquet'}

    def test_unknown_profile(self):
        result = run_profile(_gdf([Point(0, 0)]), 'does-not-exist')
        assert result['error'] == 'unknown profile'
        assert 'rfc7946' in result['available']


class TestRFC7946:
    def test_clean_wgs84_is_conformant(self):
        gdf = _gdf([Point(0, 0), Point(1, 1)])
        result = run_profile(gdf, 'rfc7946')
        assert result['conformant'] is True
        assert result['checks']['rfc7946.crs']['status'] == 'pass'

    def test_non_wgs84_crs_fails(self):
        gdf = _gdf([Point(0, 0)], crs='EPSG:3857')
        result = run_profile(gdf, 'rfc7946')
        assert result['conformant'] is False
        assert result['checks']['rfc7946.crs']['status'] == 'fail'

    def test_wrong_winding_fails(self):
        # Clockwise exterior ring violates the right-hand rule.
        cw = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
        gdf = _gdf([cw])
        result = run_profile(gdf, 'rfc7946')
        assert result['checks']['rfc7946.winding']['status'] == 'fail'
        assert result['conformant'] is False

    def test_out_of_range_fails(self):
        gdf = _gdf([Point(200, 5)])
        result = run_profile(gdf, 'rfc7946')
        assert result['checks']['rfc7946.coord_range']['status'] == 'fail'


class TestGeoPackage:
    def test_conformant_gpkg(self, tmp_path):
        path = tmp_path / "data.gpkg"
        _gdf([box(0, 0, 1, 1)]).to_file(path, driver='GPKG')
        result = run_profile(path, 'geopackage')
        assert result['conformant'] is True
        assert result['checks']['gpkg.contents']['status'] == 'pass'
        assert result['checks']['gpkg.application_id']['status'] == 'pass'

    def test_path_checks_skip_on_gdf(self):
        result = run_profile(_gdf([box(0, 0, 1, 1)]), 'geopackage')
        # No file on disk -> every path check skips, nothing fails.
        assert result['conformant'] is True
        assert all(c['status'] == 'skip' for c in result['checks'].values())

    def test_skips_on_non_gpkg_path(self, tmp_path):
        path = tmp_path / "data.geojson"
        _gdf([Point(0, 0)]).to_file(path, driver='GeoJSON')
        result = run_profile(path, 'geopackage')
        assert all(c['status'] == 'skip' for c in result['checks'].values())


class TestGeoParquet:
    def test_conformant_geoparquet(self, tmp_path):
        path = tmp_path / "data.parquet"
        _gdf([Point(0, 0)]).to_parquet(path)
        result = run_profile(path, 'geoparquet')
        assert result['conformant'] is True
        assert result['checks']['geoparquet.geo_metadata']['status'] == 'pass'
        assert result['checks']['geoparquet.primary_column']['status'] == 'pass'

    def test_plain_parquet_fails(self, tmp_path):
        path = tmp_path / "plain.parquet"
        pd.DataFrame({'a': [1, 2, 3]}).to_parquet(path)
        result = run_profile(path, 'geoparquet')
        assert result['conformant'] is False
        assert result['checks']['geoparquet.geo_metadata']['status'] == 'fail'
        # Dependent checks skip rather than error.
        assert result['checks']['geoparquet.version']['status'] == 'skip'


class TestRunValidationWithProfile:
    def test_profile_attached_to_report(self, tmp_path):
        path = tmp_path / "data.geojson"
        _gdf([Point(0, 0)]).to_file(path, driver='GeoJSON')
        report, _ = run_validation(path, profile='rfc7946')
        assert 'conformance' in report
        assert report['conformance']['profile'] == 'rfc7946'

    def test_no_profile_no_conformance_key(self, tmp_path):
        path = tmp_path / "data.geojson"
        _gdf([Point(0, 0)]).to_file(path, driver='GeoJSON')
        report, _ = run_validation(path)
        assert 'conformance' not in report
