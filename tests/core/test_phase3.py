"""
Tests for Phase 3: CI-native distribution (SARIF, error layer, pre-commit entry).
"""

import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, box

from geolint.core.checks import run_checks
from geolint.core.config import default_config
from geolint.core.error_layer import flagged_index_map, write_error_layer
from geolint.core.findings import collect_findings
from geolint.core.sarif import to_sarif
from geolint.core.validation import validate_geometries

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bowtie():
    return Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])  # self-intersecting


def _report(gdf):
    return {
        'validation': {'crs_present': gdf.crs is not None},
        'geometry_validation': validate_geometries(gdf),
        'checks': run_checks(gdf),
    }


class TestSarif:
    def test_structure_and_levels(self):
        report = {
            'validation': {'crs_present': True},
            'geometry_validation': {'invalid_count': 1, 'empty_count': 0, 'null_count': 0,
                                    'mixed_types': False, 'invalid_indices': [0]},
            'checks': {'topology': {'duplicate_geometries': {'duplicate_count': 2, 'sample_indices': [0, 1]}},
                       'attributes': {}, 'coordinates': {}},
        }
        findings = collect_findings(report, default_config())
        sarif = to_sarif(findings, "data.gpkg")
        assert sarif['version'] == '2.1.0'
        run = sarif['runs'][0]
        assert run['tool']['driver']['name'] == 'GeoLint'
        levels = {r['level'] for r in run['results']}
        assert 'error' in levels    # invalid_geometries
        assert 'warning' in levels  # duplicate_geometries
        assert all(r['locations'][0]['physicalLocation']['artifactLocation']['uri'] == 'data.gpkg'
                   for r in run['results'])


class TestErrorLayer:
    def test_flags_invalid_feature(self, tmp_path):
        gdf = gpd.GeoDataFrame({'id': [1, 2]}, geometry=[box(0, 0, 1, 1), _bowtie()], crs='EPSG:4326')
        index_map = flagged_index_map(gdf, _report(gdf))
        assert 1 in index_map
        assert 'invalid_geometries' in index_map[1]
        assert 0 not in index_map

        out = write_error_layer(gdf, _report(gdf), tmp_path / "errors.geojson")
        loaded = gpd.read_file(out)
        assert len(loaded) == 1
        assert 'geolint_checks' in loaded.columns

    def test_empty_when_clean(self, tmp_path):
        gdf = gpd.GeoDataFrame({'id': [1, 2]}, geometry=[box(0, 0, 1, 1), box(5, 5, 6, 6)], crs='EPSG:4326')
        out = write_error_layer(gdf, _report(gdf), tmp_path / "clean.geojson")
        data = json.loads(Path(out).read_text())
        assert data == {'type': 'FeatureCollection', 'features': []}


class TestPrecommitEntry:
    def _run(self, *args):
        code = (
            "import sys; sys.argv=['geolint-precommit', *%r]; "
            "from geolint.cli.main import precommit_app; precommit_app()" % (list(args),)
        )
        return subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO_ROOT)
        )

    def test_clean_file_exits_zero(self, tmp_path):
        path = tmp_path / "clean.gpkg"
        gpd.GeoDataFrame({'id': [1]}, geometry=[box(0, 0, 1, 1)], crs='EPSG:4326').to_file(path, driver='GPKG')
        assert self._run(str(path)).returncode == 0

    def test_strict_overlap_exits_one(self, tmp_path):
        path = tmp_path / "overlap.gpkg"
        gpd.GeoDataFrame(
            {'id': [1, 2]}, geometry=[box(0, 0, 2, 2), box(1, 1, 3, 3)], crs='EPSG:4326'
        ).to_file(path, driver='GPKG')
        assert self._run(str(path), "--strict").returncode == 1
