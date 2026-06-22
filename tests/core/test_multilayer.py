"""
Tests for Phase 1B: multi-layer plumbing and inter-layer checks.
"""

import geopandas as gpd
from shapely.geometry import Point, box

from geolint.core.checks import (
    check_cross_layer_overlap,
    check_must_be_covered_by,
    run_multilayer_checks,
)
from geolint.core.transform import align_layers_crs
from geolint.core.validation import (
    list_layers,
    load_layers,
    run_multilayer_validation,
)


def _gdf(geoms, crs='EPSG:4326'):
    return gpd.GeoDataFrame({'id': range(len(geoms)), 'geometry': geoms}, crs=crs)


class TestCrossLayerOverlap:
    def test_detects_overlap(self):
        a = _gdf([box(0, 0, 2, 2)])
        b = _gdf([box(1, 1, 3, 3)])
        result = check_cross_layer_overlap(a, b, name_a='a', name_b='b')
        assert result['applicable'] is True
        assert result['overlap_pair_count'] == 1
        assert result['features_involved_a'] == 1
        assert result['sample_pairs'][0] == {'a_index': 0, 'b_index': 0}

    def test_disjoint_layers(self):
        a = _gdf([box(0, 0, 1, 1)])
        b = _gdf([box(5, 5, 6, 6)])
        assert check_cross_layer_overlap(a, b)['overlap_pair_count'] == 0

    def test_touching_is_not_overlap(self):
        a = _gdf([box(0, 0, 1, 1)])
        b = _gdf([box(1, 0, 2, 1)])  # shares only an edge
        assert check_cross_layer_overlap(a, b)['overlap_pair_count'] == 0

    def test_not_applicable_without_polygons(self):
        a = _gdf([Point(0, 0)])
        b = _gdf([box(0, 0, 1, 1)])
        assert check_cross_layer_overlap(a, b)['applicable'] is False


class TestMustBeCoveredBy:
    def test_fully_covered(self):
        a = _gdf([box(1, 1, 2, 2)])
        b = _gdf([box(0, 0, 10, 10)])
        result = check_must_be_covered_by(a, b)
        assert result['applicable'] is True
        assert result['uncovered_count'] == 0
        assert result['uncovered_area_total'] == 0.0

    def test_partially_uncovered(self):
        a = _gdf([box(9, 9, 12, 12)])  # pokes outside the coverage
        b = _gdf([box(0, 0, 10, 10)])
        result = check_must_be_covered_by(a, b)
        assert result['uncovered_count'] == 1
        assert result['uncovered_area_total'] > 0
        assert result['sample_indices'] == [0]

    def test_points_in_and_out(self):
        a = _gdf([Point(5, 5), Point(50, 50)])
        b = _gdf([box(0, 0, 10, 10)])
        result = check_must_be_covered_by(a, b)
        assert result['uncovered_count'] == 1
        assert result['sample_indices'] == [1]


class TestAlignLayersCRS:
    def test_same_crs_error_policy_aligned(self):
        layers = {'a': _gdf([Point(0, 0)]), 'b': _gdf([Point(1, 1)])}
        _, report = align_layers_crs(layers, policy='error')
        assert report['aligned'] is True

    def test_different_crs_error_policy_blocks(self):
        layers = {
            'a': _gdf([Point(0, 0)], crs='EPSG:4326'),
            'b': _gdf([Point(1, 1)], crs='EPSG:3857'),
        }
        _, report = align_layers_crs(layers, policy='error')
        assert report['aligned'] is False
        assert 'differing' in report['reason']

    def test_missing_crs_error_policy_blocks(self):
        layers = {
            'a': _gdf([Point(0, 0)], crs='EPSG:4326'),
            'b': _gdf([Point(1, 1)], crs=None),
        }
        _, report = align_layers_crs(layers, policy='error')
        assert report['aligned'] is False

    def test_align_policy_reprojects(self):
        layers = {
            'a': _gdf([Point(0, 0)], crs='EPSG:4326'),
            'b': _gdf([Point(1, 1)], crs='EPSG:3857'),
        }
        aligned, report = align_layers_crs(layers, policy='align', target_crs='EPSG:4326')
        assert report['aligned'] is True
        assert 'b' in report['reprojected']
        assert aligned['b'].crs.to_epsg() == 4326


class TestRunMultilayerChecks:
    def test_overlap_rule(self):
        layers = {'parcels': _gdf([box(0, 0, 2, 2)]), 'roads': _gdf([box(1, 1, 3, 3)])}
        result = run_multilayer_checks(layers, must_not_overlap=[('parcels', 'roads')])
        assert result['must_not_overlap'][0]['overlap_pair_count'] == 1

    def test_unknown_layer_reports_error(self):
        layers = {'parcels': _gdf([box(0, 0, 2, 2)])}
        result = run_multilayer_checks(layers, must_not_overlap=[('parcels', 'ghost')])
        assert 'error' in result['must_not_overlap'][0]

    def test_default_coverage_layers_are_polygon_layers(self):
        layers = {'pts': _gdf([Point(0, 0)]), 'polys': _gdf([box(0, 0, 1, 1)])}
        result = run_multilayer_checks(layers)
        assert 'polys' in result['coverage_gaps']
        assert 'pts' not in result['coverage_gaps']


class TestLoadLayers:
    def test_multilayer_gpkg(self, tmp_path):
        path = tmp_path / "multi.gpkg"
        _gdf([box(0, 0, 1, 1)]).to_file(path, layer='parcels', driver='GPKG')
        _gdf([box(2, 2, 3, 3)]).to_file(path, layer='roads', driver='GPKG')

        assert set(list_layers(path)) == {'parcels', 'roads'}
        loaded = load_layers(path)
        assert set(loaded.keys()) == {'parcels', 'roads'}

    def test_multiple_files_keyed_by_stem(self, tmp_path):
        p1 = tmp_path / "alpha.geojson"
        p2 = tmp_path / "beta.geojson"
        _gdf([Point(0, 0)]).to_file(p1, driver='GeoJSON')
        _gdf([Point(1, 1)]).to_file(p2, driver='GeoJSON')
        loaded = load_layers([p1, p2])
        assert set(loaded.keys()) == {'alpha', 'beta'}


class TestRunMultilayerValidation:
    def test_end_to_end_with_overlap_rule(self, tmp_path):
        path = tmp_path / "multi.gpkg"
        _gdf([box(0, 0, 2, 2)]).to_file(path, layer='parcels', driver='GPKG')
        _gdf([box(1, 1, 3, 3)]).to_file(path, layer='roads', driver='GPKG')

        report, aligned = run_multilayer_validation(
            path, must_not_overlap=[('parcels', 'roads')]
        )
        assert report['inter_layer']['layer_count'] == 2
        assert set(report['per_layer'].keys()) == {'parcels', 'roads'}
        assert report['inter_layer']['crs_alignment']['aligned'] is True
        overlaps = report['inter_layer']['checks']['must_not_overlap']
        assert overlaps[0]['overlap_pair_count'] == 1
