"""
Tests for the geometry module.
"""

import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString

from geolint.core.geometry import (
    fix_geometries, remove_empty_geometries, explode_multipart,
    simplify_geometries, validate_geometry_types, get_geometry_bounds,
    process_geometries
)


class TestFixGeometries:
    """Test geometry fixing functionality."""
    
    def test_fix_geometries_valid_gdf(self, sample_point_gdf):
        """Test fixing geometries on already valid geometries."""
        fixed_gdf, report = fix_geometries(sample_point_gdf)
        
        assert isinstance(fixed_gdf, gpd.GeoDataFrame)
        assert len(fixed_gdf) == len(sample_point_gdf)
        assert report['geometries_fixed'] == 0
        assert report['geometries_removed'] == 0
        assert report['total_processed'] == len(sample_point_gdf)
    
    def test_fix_geometries_invalid_gdf(self, sample_invalid_gdf):
        """Test fixing geometries with invalid ones."""
        fixed_gdf, report = fix_geometries(sample_invalid_gdf)
        
        assert isinstance(fixed_gdf, gpd.GeoDataFrame)
        assert report['geometries_fixed'] > 0
        assert report['total_processed'] == len(sample_invalid_gdf)
        
        # Check that invalid geometries were fixed
        invalid_count_after = (~fixed_gdf.geometry.is_valid).sum()
        assert invalid_count_after < report['geometries_fixed']
    
    def test_fix_geometries_empty_gdf(self, sample_empty_gdf):
        """Test fixing geometries on empty GeoDataFrame."""
        fixed_gdf, report = fix_geometries(sample_empty_gdf)
        
        assert isinstance(fixed_gdf, gpd.GeoDataFrame)
        assert len(fixed_gdf) == 0
        assert report['geometries_fixed'] == 0
        assert report['geometries_removed'] == 0
        assert report['total_processed'] == 0


class TestRemoveEmptyGeometries:
    """Test empty geometry removal functionality."""
    
    def test_remove_empty_geometries_with_empty(self, sample_invalid_gdf):
        """Test removing empty geometries."""
        cleaned_gdf, report = remove_empty_geometries(sample_invalid_gdf)
        
        assert isinstance(cleaned_gdf, gpd.GeoDataFrame)
        assert report['geometries_removed'] > 0
        assert report['remaining_count'] == len(cleaned_gdf)
        assert len(cleaned_gdf) < len(sample_invalid_gdf)
    
    def test_remove_empty_geometries_no_empty(self, sample_point_gdf):
        """Test removing empty geometries when none exist."""
        cleaned_gdf, report = remove_empty_geometries(sample_point_gdf)
        
        assert isinstance(cleaned_gdf, gpd.GeoDataFrame)
        assert len(cleaned_gdf) == len(sample_point_gdf)
        assert report['geometries_removed'] == 0
        assert report['remaining_count'] == len(sample_point_gdf)
    
    def test_remove_empty_geometries_empty_gdf(self, sample_empty_gdf):
        """Test removing empty geometries from empty GeoDataFrame."""
        cleaned_gdf, report = remove_empty_geometries(sample_empty_gdf)
        
        assert isinstance(cleaned_gdf, gpd.GeoDataFrame)
        assert len(cleaned_gdf) == 0
        assert report['geometries_removed'] == 0
        assert report['remaining_count'] == 0


class TestExplodeMultipart:
    """Test multipart geometry explosion functionality."""
    
    def test_explode_multipart_no_multipart(self, sample_point_gdf):
        """Test exploding multipart geometries when none exist."""
        exploded_gdf, report = explode_multipart(sample_point_gdf)
        
        assert isinstance(exploded_gdf, gpd.GeoDataFrame)
        assert len(exploded_gdf) == len(sample_point_gdf)
        assert report['multipart_count'] == 0
        assert report['exploded_count'] == 0
        assert report['result_count'] == len(sample_point_gdf)
    
    def test_explode_multipart_with_multipart(self):
        """Test exploding multipart geometries."""
        from shapely.geometry import MultiPoint, MultiPolygon
        
        # Create GeoDataFrame with multipart geometries
        data = {
            'id': [1, 2],
            'name': ['MultiPoint', 'MultiPolygon'],
            'geometry': [
                MultiPoint([(0, 0), (1, 1)]),
                MultiPolygon([
                    Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                    Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])
                ])
            ]
        }
        gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')
        
        exploded_gdf, report = explode_multipart(gdf)
        
        assert isinstance(exploded_gdf, gpd.GeoDataFrame)
        assert report['multipart_count'] == 2
        assert report['exploded_count'] > 0
        assert report['result_count'] == len(exploded_gdf)
        assert len(exploded_gdf) > len(gdf)
    
    def test_explode_multipart_empty_gdf(self, sample_empty_gdf):
        """Test exploding multipart geometries from empty GeoDataFrame."""
        exploded_gdf, report = explode_multipart(sample_empty_gdf)
        
        assert isinstance(exploded_gdf, gpd.GeoDataFrame)
        assert len(exploded_gdf) == 0
        assert report['multipart_count'] == 0
        assert report['exploded_count'] == 0
        assert report['result_count'] == 0


class TestSimplifyGeometries:
    """Test geometry simplification functionality."""
    
    def test_simplify_geometries(self, sample_polygon_gdf):
        """Test simplifying geometries."""
        simplified_gdf, report = simplify_geometries(sample_polygon_gdf, tolerance=0.1)
        
        assert isinstance(simplified_gdf, gpd.GeoDataFrame)
        assert len(simplified_gdf) == len(sample_polygon_gdf)
        assert report['geometries_simplified'] == len(sample_polygon_gdf)
        assert report['original_vertices'] > 0
        assert report['simplified_vertices'] > 0
        assert report['vertices_reduced'] >= 0
    
    def test_simplify_geometries_no_reduction(self, sample_point_gdf):
        """Test simplifying geometries that don't need simplification."""
        simplified_gdf, report = simplify_geometries(sample_point_gdf, tolerance=0.001)
        
        assert isinstance(simplified_gdf, gpd.GeoDataFrame)
        assert len(simplified_gdf) == len(sample_point_gdf)
        assert report['geometries_simplified'] == len(sample_point_gdf)
    
    def test_simplify_geometries_empty_gdf(self, sample_empty_gdf):
        """Test simplifying geometries from empty GeoDataFrame."""
        simplified_gdf, report = simplify_geometries(sample_empty_gdf)
        
        assert isinstance(simplified_gdf, gpd.GeoDataFrame)
        assert len(simplified_gdf) == 0
        assert report['geometries_simplified'] == 0
        assert report['original_vertices'] == 0
        assert report['simplified_vertices'] == 0


class TestValidateGeometryTypes:
    """Test geometry type validation functionality."""
    
    def test_validate_geometry_types_single_type(self, sample_point_gdf):
        """Test validating geometry types for single type."""
        type_counts = validate_geometry_types(sample_point_gdf)
        
        assert isinstance(type_counts, dict)
        assert 'Point' in type_counts
        assert type_counts['Point'] == len(sample_point_gdf)
        assert type_counts['total_features'] == len(sample_point_gdf)
        assert type_counts['unique_types'] == 1
    
    def test_validate_geometry_types_mixed_types(self, sample_mixed_gdf):
        """Test validating geometry types for mixed types."""
        type_counts = validate_geometry_types(sample_mixed_gdf)
        
        assert isinstance(type_counts, dict)
        assert type_counts['total_features'] == len(sample_mixed_gdf)
        assert type_counts['unique_types'] == 3  # Point, LineString, Polygon
        assert 'Point' in type_counts
        assert 'LineString' in type_counts
        assert 'Polygon' in type_counts
    
    def test_validate_geometry_types_empty_gdf(self, sample_empty_gdf):
        """Test validating geometry types for empty GeoDataFrame."""
        type_counts = validate_geometry_types(sample_empty_gdf)
        
        assert isinstance(type_counts, dict)
        assert type_counts['total_features'] == 0
        assert type_counts['unique_types'] == 0


class TestGetGeometryBounds:
    """Test geometry bounds calculation functionality."""
    
    def test_get_geometry_bounds(self, sample_point_gdf):
        """Test getting geometry bounds."""
        bounds = get_geometry_bounds(sample_point_gdf)
        
        assert isinstance(bounds, dict)
        assert 'minx' in bounds
        assert 'miny' in bounds
        assert 'maxx' in bounds
        assert 'maxy' in bounds
        assert 'width' in bounds
        assert 'height' in bounds
        assert 'area' in bounds
        
        assert bounds['minx'] <= bounds['maxx']
        assert bounds['miny'] <= bounds['maxy']
        assert bounds['width'] == bounds['maxx'] - bounds['minx']
        assert bounds['height'] == bounds['maxy'] - bounds['miny']
        assert bounds['area'] == bounds['width'] * bounds['height']
    
    def test_get_geometry_bounds_empty_gdf(self, sample_empty_gdf):
        """Test getting geometry bounds for empty GeoDataFrame."""
        bounds = get_geometry_bounds(sample_empty_gdf)
        
        assert isinstance(bounds, dict)
        assert bounds['minx'] == 0
        assert bounds['miny'] == 0
        assert bounds['maxx'] == 0
        assert bounds['maxy'] == 0
        assert bounds['width'] == 0
        assert bounds['height'] == 0
        assert bounds['area'] == 0


class TestProcessGeometries:
    """Test comprehensive geometry processing functionality."""
    
    def test_process_geometries_all_options(self, sample_invalid_gdf):
        """Test processing geometries with all options enabled."""
        processed_gdf, report = process_geometries(
            sample_invalid_gdf,
            fix_invalid=True,
            remove_empty=True,
            explode_multipart=False,
            simplify=True,
            simplify_tolerance=0.01
        )
        
        assert isinstance(processed_gdf, gpd.GeoDataFrame)
        assert isinstance(report, dict)
        assert 'operations' in report
        assert 'original_count' in report
        assert 'final_count' in report
        assert 'total_removed' in report
        assert 'geometry_types' in report
        assert 'bounds' in report
        
        assert len(report['operations']) > 0
        assert report['original_count'] == len(sample_invalid_gdf)
        assert report['final_count'] == len(processed_gdf)
    
    def test_process_geometries_no_options(self, sample_point_gdf):
        """Test processing geometries with no options enabled."""
        processed_gdf, report = process_geometries(
            sample_point_gdf,
            fix_invalid=False,
            remove_empty=False,
            explode_multipart=False,
            simplify=False
        )
        
        assert isinstance(processed_gdf, gpd.GeoDataFrame)
        assert len(processed_gdf) == len(sample_point_gdf)
        assert report['original_count'] == len(sample_point_gdf)
        assert report['final_count'] == len(processed_gdf)
        assert report['total_removed'] == 0
    
    def test_process_geometries_empty_gdf(self, sample_empty_gdf):
        """Test processing geometries for empty GeoDataFrame."""
        processed_gdf, report = process_geometries(
            sample_empty_gdf,
            fix_invalid=True,
            remove_empty=True,
            explode_multipart=True,
            simplify=True
        )
        
        assert isinstance(processed_gdf, gpd.GeoDataFrame)
        assert len(processed_gdf) == 0
        assert report['original_count'] == 0
        assert report['final_count'] == 0
        assert report['total_removed'] == 0
    
    def test_process_geometries_operation_tracking(self, sample_invalid_gdf):
        """Test that operations are properly tracked."""
        processed_gdf, report = process_geometries(
            sample_invalid_gdf,
            fix_invalid=True,
            remove_empty=True,
            explode_multipart=False,
            simplify=False
        )
        
        operations = report['operations']
        operation_names = [op['operation'] for op in operations]
        
        assert 'fix_invalid' in operation_names
        assert 'remove_empty' in operation_names
        assert 'explode_multipart' not in operation_names
        assert 'simplify' not in operation_names
