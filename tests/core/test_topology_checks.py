"""
Tests for the deeper single-layer topology checks (Phase 1A):
coverage gaps, line dangles, line self-intersections, pseudo-nodes.
"""

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, box

from geolint.core.checks import (
    check_coverage_gaps,
    check_line_dangles,
    check_line_self_intersections,
    check_pseudo_nodes,
)


def _grid_minus_center():
    """3x3 grid of unit squares with the center square missing (one 1x1 gap)."""
    cells = [
        box(i, j, i + 1, j + 1)
        for i in range(3)
        for j in range(3)
        if not (i == 1 and j == 1)
    ]
    return gpd.GeoDataFrame({'id': range(len(cells)), 'geometry': cells}, crs='EPSG:4326')


def _full_grid():
    """2x2 grid of unit squares fully tiling a 2x2 block (no gaps)."""
    cells = [box(i, j, i + 1, j + 1) for i in range(2) for j in range(2)]
    return gpd.GeoDataFrame({'id': range(len(cells)), 'geometry': cells}, crs='EPSG:4326')


class TestCoverageGaps:
    def test_detects_enclosed_gap(self):
        result = check_coverage_gaps(_grid_minus_center())
        assert result['applicable'] is True
        assert result['skipped'] is False
        assert result['gap_count'] == 1
        assert result['largest_gap_area'] == 1.0
        assert abs(result['gap_area_total'] - 1.0) < 1e-9
        assert len(result['sample_gaps']) == 1
        gap = result['sample_gaps'][0]
        assert abs(gap['centroid'][0] - 1.5) < 1e-9
        assert abs(gap['centroid'][1] - 1.5) < 1e-9
        assert result['crs_is_geographic'] is True

    def test_complete_coverage_has_no_gaps(self):
        result = check_coverage_gaps(_full_grid())
        assert result['applicable'] is True
        assert result['gap_count'] == 0
        assert result['sample_gaps'] == []

    def test_area_tol_filters_small_gaps(self):
        # The single gap has area 1.0; a tolerance above it suppresses it.
        result = check_coverage_gaps(_grid_minus_center(), area_tol=2.0)
        assert result['gap_count'] == 0

    def test_not_applicable_without_polygons(self):
        gdf = gpd.GeoDataFrame(
            {'id': [1, 2], 'geometry': [Point(0, 0), Point(1, 1)]}, crs='EPSG:4326'
        )
        assert check_coverage_gaps(gdf)['applicable'] is False

    def test_empty(self):
        gdf = gpd.GeoDataFrame(geometry=[], crs='EPSG:4326')
        assert check_coverage_gaps(gdf)['applicable'] is False


class TestLineDangles:
    def test_connected_lines_have_two_dangles(self):
        # Two lines share node (1,1); only the two far endpoints dangle.
        gdf = gpd.GeoDataFrame({'geometry': [
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
        ]}, crs='EPSG:4326')
        result = check_line_dangles(gdf)
        assert result['applicable'] is True
        assert result['dangle_count'] == 2

    def test_isolated_line_has_two_dangles(self):
        gdf = gpd.GeoDataFrame({'geometry': [LineString([(0, 0), (5, 5)])]}, crs='EPSG:4326')
        assert check_line_dangles(gdf)['dangle_count'] == 2

    def test_closed_ring_has_no_dangles(self):
        ring = LineString([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = gpd.GeoDataFrame({'geometry': [ring]}, crs='EPSG:4326')
        assert check_line_dangles(gdf)['dangle_count'] == 0

    def test_tolerance_snaps_near_endpoints(self):
        gdf = gpd.GeoDataFrame({'geometry': [
            LineString([(0, 0), (1, 1)]),
            LineString([(1.001, 1.001), (2, 2)]),
        ]}, crs='EPSG:4326')
        # Exact: all four endpoints are isolated.
        assert check_line_dangles(gdf, tolerance=0.0)['dangle_count'] == 4
        # With tolerance the near pair connects, leaving the two far ends.
        assert check_line_dangles(gdf, tolerance=0.01)['dangle_count'] == 2

    def test_not_applicable_without_lines(self):
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]}, crs='EPSG:4326')
        assert check_line_dangles(gdf)['applicable'] is False


class TestLineSelfIntersections:
    def test_detects_self_crossing(self):
        bowtie = LineString([(0, 0), (2, 2), (0, 2), (2, 0)])  # crosses itself
        gdf = gpd.GeoDataFrame({'geometry': [bowtie]}, crs='EPSG:4326')
        result = check_line_self_intersections(gdf)
        assert result['applicable'] is True
        assert result['self_intersecting_count'] == 1
        assert 0 in result['sample_indices']

    def test_detects_doubled_back_segment(self):
        spike = LineString([(0, 0), (2, 0), (1, 0)])  # doubles back over itself
        gdf = gpd.GeoDataFrame({'geometry': [spike]}, crs='EPSG:4326')
        result = check_line_self_intersections(gdf)
        assert result['self_overlapping_count'] == 1

    def test_clean_line(self):
        gdf = gpd.GeoDataFrame({'geometry': [LineString([(0, 0), (1, 1), (2, 0)])]}, crs='EPSG:4326')
        result = check_line_self_intersections(gdf)
        assert result['self_intersecting_count'] == 0
        assert result['self_overlapping_count'] == 0


class TestPseudoNodes:
    def test_detects_pseudo_node(self):
        gdf = gpd.GeoDataFrame({'geometry': [
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
        ]}, crs='EPSG:4326')
        result = check_pseudo_nodes(gdf)
        assert result['applicable'] is True
        assert result['pseudo_node_count'] == 1
        assert result['sample_nodes'][0]['coord'] == [1.0, 1.0]

    def test_three_way_node_is_not_pseudo(self):
        gdf = gpd.GeoDataFrame({'geometry': [
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
            LineString([(1, 1), (2, 0)]),
        ]}, crs='EPSG:4326')
        assert check_pseudo_nodes(gdf)['pseudo_node_count'] == 0
