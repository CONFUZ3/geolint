"""
Tests for the quality checks module.
"""

import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString, box

from geolint.core.checks import (
    check_duplicate_geometries,
    check_overlapping_polygons,
    check_sliver_and_zero_geometries,
    check_duplicate_vertices,
    check_id_uniqueness,
    check_null_attributes,
    check_shapefile_field_names,
    check_winding_order,
    check_coordinate_range,
    run_checks,
)


class TestCheckDuplicateGeometries:
    """Test duplicate geometry detection."""

    def test_duplicate_geometries_found(self, sample_duplicate_geom_gdf):
        result = check_duplicate_geometries(sample_duplicate_geom_gdf)

        assert result['duplicate_count'] == 1
        assert result['duplicate_groups'] == 1
        assert isinstance(result['sample_indices'], list)

    def test_no_duplicate_geometries(self, sample_point_gdf):
        result = check_duplicate_geometries(sample_point_gdf)

        assert result['duplicate_count'] == 0
        assert result['duplicate_groups'] == 0
        assert result['sample_indices'] == []

    def test_duplicate_geometries_empty_gdf(self, sample_empty_gdf):
        result = check_duplicate_geometries(sample_empty_gdf)

        assert result['duplicate_count'] == 0
        assert result['duplicate_groups'] == 0
        assert result['sample_indices'] == []


class TestCheckOverlappingPolygons:
    """Test overlapping polygon detection."""

    def test_overlapping_polygons_found(self, sample_overlapping_gdf):
        result = check_overlapping_polygons(sample_overlapping_gdf)

        assert result['applicable'] is True
        assert result['skipped'] is False
        assert result['overlap_pair_count'] == 1
        assert result['features_involved'] == 2

    def test_touching_polygons_not_flagged(self, sample_touching_gdf):
        result = check_overlapping_polygons(sample_touching_gdf)

        assert result['applicable'] is True
        assert result['overlap_pair_count'] == 0
        assert result['features_involved'] == 0

    def test_no_polygons_not_applicable(self, sample_point_gdf):
        result = check_overlapping_polygons(sample_point_gdf)

        assert result['applicable'] is False
        assert result['overlap_pair_count'] == 0

    def test_overlapping_polygons_empty_gdf(self, sample_empty_gdf):
        result = check_overlapping_polygons(sample_empty_gdf)

        assert result['applicable'] is False
        assert result['overlap_pair_count'] == 0
        assert result['sample_pairs'] == []


class TestCheckSliverAndZeroGeometries:
    """Test sliver / zero-area / zero-length detection."""

    def test_slivers_found(self, sample_sliver_gdf):
        result = check_sliver_and_zero_geometries(sample_sliver_gdf)

        assert result['zero_area_polygons'] == 1
        assert result['zero_length_lines'] == 1
        assert len(result['sample_indices']) >= 1

    def test_no_slivers(self, sample_point_gdf):
        result = check_sliver_and_zero_geometries(sample_point_gdf)

        assert result['zero_area_polygons'] == 0
        assert result['zero_length_lines'] == 0
        assert result['sample_indices'] == []

    def test_slivers_empty_gdf(self, sample_empty_gdf):
        result = check_sliver_and_zero_geometries(sample_empty_gdf)

        assert result['zero_area_polygons'] == 0
        assert result['zero_length_lines'] == 0
        assert result['sample_indices'] == []


class TestCheckDuplicateVertices:
    """Test consecutive duplicate vertex detection."""

    def test_duplicate_vertices_found(self, sample_dup_vertex_gdf):
        result = check_duplicate_vertices(sample_dup_vertex_gdf)

        assert result['features_with_duplicate_vertices'] == 1
        assert result['sample_indices'] == [0]

    def test_clean_line_not_flagged(self):
        gdf = gpd.GeoDataFrame(
            {'id': [1], 'geometry': [LineString([(0, 0), (1, 1)])]},
            crs='EPSG:4326'
        )
        result = check_duplicate_vertices(gdf)

        assert result['features_with_duplicate_vertices'] == 0
        assert result['sample_indices'] == []

    def test_closed_ring_not_flagged(self):
        """A normally closed polygon ring must NOT be flagged."""
        gdf = gpd.GeoDataFrame(
            {'id': [1], 'geometry': [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]},
            crs='EPSG:4326'
        )
        result = check_duplicate_vertices(gdf)

        assert result['features_with_duplicate_vertices'] == 0

    def test_duplicate_vertices_empty_gdf(self, sample_empty_gdf):
        result = check_duplicate_vertices(sample_empty_gdf)

        assert result['features_with_duplicate_vertices'] == 0
        assert result['sample_indices'] == []


class TestCheckIdUniqueness:
    """Test identifier uniqueness checks."""

    def test_duplicate_ids_found(self, sample_dup_id_gdf):
        result = check_id_uniqueness(sample_dup_id_gdf)

        assert result['id_column'] == 'id'
        assert result['duplicate_count'] == 2
        assert 2 in result['sample_values']

    def test_no_id_like_column(self):
        gdf = gpd.GeoDataFrame(
            {'name': ['a', 'b'], 'geometry': [Point(0, 0), Point(1, 1)]},
            crs='EPSG:4326'
        )
        result = check_id_uniqueness(gdf)

        assert result['id_column'] is None
        assert result['duplicate_count'] == 0

    def test_unique_ids(self, sample_point_gdf):
        result = check_id_uniqueness(sample_point_gdf)

        assert result['id_column'] == 'id'
        assert result['duplicate_count'] == 0

    def test_id_uniqueness_empty_gdf(self, sample_empty_gdf):
        result = check_id_uniqueness(sample_empty_gdf)

        assert result['duplicate_count'] == 0
        assert result['sample_values'] == []


class TestCheckNullAttributes:
    """Test null attribute counting."""

    def test_null_attributes_counts(self):
        gdf = gpd.GeoDataFrame(
            {
                'id': [1, 2, 3],
                'name': [None, 'b', None],
                'empty_col': [None, None, None],
                'geometry': [Point(0, 0), Point(1, 1), Point(2, 2)]
            },
            crs='EPSG:4326'
        )
        result = check_null_attributes(gdf)

        assert result['null_counts']['name'] == 2
        assert 'empty_col' in result['fully_null_columns']
        assert result['total_columns'] == 3

    def test_no_nulls(self, sample_point_gdf):
        result = check_null_attributes(sample_point_gdf)

        assert result['null_counts'] == {}
        assert result['fully_null_columns'] == []
        assert result['total_columns'] == 2

    def test_null_attributes_empty_gdf(self, sample_empty_gdf):
        result = check_null_attributes(sample_empty_gdf)

        assert result['null_counts'] == {}
        assert result['fully_null_columns'] == []
        assert result['total_columns'] == 0


class TestCheckShapefileFieldNames:
    """Test shapefile DBF field name constraint checks."""

    def test_long_and_collision_names(self, sample_long_fieldname_gdf):
        result = check_shapefile_field_names(sample_long_fieldname_gdf)

        assert 'a_very_long_field_name' in result['long_names']
        # description_1 and description_2 share their first 10 chars
        collision_groups = [set(g) for g in result['truncation_collisions']]
        assert {'description_1', 'description_2'} in collision_groups

    def test_compliant_field_names(self, sample_point_gdf):
        result = check_shapefile_field_names(sample_point_gdf)

        assert result['long_names'] == []
        assert result['truncation_collisions'] == []
        assert result['non_ascii_names'] == []

    def test_field_names_empty_gdf(self, sample_empty_gdf):
        result = check_shapefile_field_names(sample_empty_gdf)

        assert result['long_names'] == []
        assert result['truncation_collisions'] == []
        assert result['non_ascii_names'] == []


class TestCheckWindingOrder:
    """Test polygon winding order checks (RFC 7946)."""

    def test_clockwise_exterior_flagged(self, sample_wrong_winding_gdf):
        result = check_winding_order(sample_wrong_winding_gdf)

        assert result['applicable'] is True
        assert result['non_compliant_count'] == 1
        assert result['sample_indices'] == [0]

    def test_counterclockwise_compliant(self):
        gdf = gpd.GeoDataFrame(
            {'id': [1], 'geometry': [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]},
            crs='EPSG:4326'
        )
        result = check_winding_order(gdf)

        assert result['applicable'] is True
        assert result['non_compliant_count'] == 0

    def test_no_polygons_not_applicable(self, sample_point_gdf):
        result = check_winding_order(sample_point_gdf)

        assert result['applicable'] is False
        assert result['non_compliant_count'] == 0

    def test_winding_order_empty_gdf(self, sample_empty_gdf):
        result = check_winding_order(sample_empty_gdf)

        assert result['applicable'] is False
        assert result['non_compliant_count'] == 0


class TestCheckCoordinateRange:
    """Test geographic coordinate range checks."""

    def test_out_of_range_geographic(self, sample_out_of_range_gdf):
        result = check_coordinate_range(sample_out_of_range_gdf)

        assert result['applicable'] is True
        assert result['out_of_range_count'] == 1
        assert result['sample_indices'] == [1]

    def test_projected_not_applicable(self, sample_out_of_range_gdf):
        projected = sample_out_of_range_gdf.to_crs('EPSG:3857')
        result = check_coordinate_range(projected)

        assert result['applicable'] is False
        assert result['out_of_range_count'] == 0

    def test_in_range_geographic(self, sample_point_gdf):
        result = check_coordinate_range(sample_point_gdf)

        assert result['applicable'] is True
        assert result['out_of_range_count'] == 0

    def test_coordinate_range_empty_gdf(self, sample_empty_gdf):
        result = check_coordinate_range(sample_empty_gdf)

        assert result['applicable'] is False
        assert result['out_of_range_count'] == 0


class TestRunChecks:
    """Test the aggregate run_checks entrypoint."""

    def test_run_checks_structure(self, sample_overlapping_gdf):
        result = run_checks(sample_overlapping_gdf)

        assert set(result.keys()) == {'topology', 'attributes', 'coordinates'}
        assert 'duplicate_geometries' in result['topology']
        assert 'overlapping_polygons' in result['topology']
        assert 'slivers' in result['topology']
        assert 'duplicate_vertices' in result['topology']
        assert 'id_uniqueness' in result['attributes']
        assert 'null_attributes' in result['attributes']
        assert 'shapefile_field_names' in result['attributes']
        assert 'winding_order' in result['coordinates']
        assert 'coordinate_range' in result['coordinates']

    def test_run_checks_empty_gdf(self):
        gdf = gpd.GeoDataFrame(geometry=[], crs='EPSG:4326')
        result = run_checks(gdf)

        assert result['topology']['duplicate_geometries']['duplicate_count'] == 0
        assert result['coordinates']['winding_order']['applicable'] is False
