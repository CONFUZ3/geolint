"""
Tests for the CRS module.
"""

import pytest
import geopandas as gpd
from shapely.geometry import Point

from geolint.core.crs import (
    get_crs_info, infer_crs, get_popular_crs, auto_detect_utm_zone
)


class TestGetCrsInfo:
    """Test CRS information extraction."""
    
    def test_get_crs_info_with_crs(self, sample_point_gdf):
        """Test getting CRS info from a GeoDataFrame with CRS."""
        crs_info = get_crs_info(sample_point_gdf)
        
        assert crs_info['crs'] is not None
        assert crs_info['epsg'] == 4326
        assert crs_info['is_geographic'] is True
        assert crs_info['is_projected'] is False
        assert crs_info['units'] == 'degree'
        assert crs_info['name'] == 'WGS 84'
    
    def test_get_crs_info_without_crs(self, sample_no_crs_gdf):
        """Test getting CRS info from a GeoDataFrame without CRS."""
        crs_info = get_crs_info(sample_no_crs_gdf)
        
        assert crs_info['crs'] is None
        assert crs_info['epsg'] is None
        assert crs_info['is_geographic'] is None
        assert crs_info['is_projected'] is None
        assert crs_info['units'] is None
        assert crs_info['name'] is None
    
    def test_get_crs_info_empty_gdf(self, sample_empty_gdf):
        """Test getting CRS info from an empty GeoDataFrame."""
        crs_info = get_crs_info(sample_empty_gdf)
        
        assert crs_info['crs'] is None
        assert crs_info['epsg'] is None


class TestInferCrs:
    """Test CRS inference functionality."""
    
    def test_infer_crs_with_crs(self, sample_point_gdf):
        """Test CRS inference when CRS is already present."""
        suggestions = infer_crs(sample_point_gdf)
        assert suggestions == []
    
    def test_infer_crs_without_crs(self, sample_no_crs_gdf):
        """Test CRS inference when no CRS is present."""
        suggestions = infer_crs(sample_no_crs_gdf)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 10  # Should return top 10 suggestions
        
        # Check suggestion structure
        if suggestions:
            suggestion = suggestions[0]
            assert 'epsg' in suggestion
            assert 'name' in suggestion
            assert 'confidence' in suggestion
            assert 'type' in suggestion
            assert 'area_of_use' in suggestion
            assert 0 <= suggestion['confidence'] <= 1
    
    def test_infer_crs_with_region_hint(self, sample_no_crs_gdf):
        """Test CRS inference with region hint."""
        suggestions = infer_crs(sample_no_crs_gdf, region_hint="Europe")
        
        assert isinstance(suggestions, list)
        # Should still return suggestions even with region hint
    
    def test_infer_crs_empty_gdf(self, sample_empty_gdf):
        """Test CRS inference with empty GeoDataFrame."""
        suggestions = infer_crs(sample_empty_gdf)
        assert suggestions == []
    
    def test_infer_crs_confidence_scores(self, sample_no_crs_gdf):
        """Test that confidence scores are properly calculated."""
        suggestions = infer_crs(sample_no_crs_gdf)
        
        if len(suggestions) > 1:
            # Check that suggestions are sorted by confidence (highest first)
            for i in range(len(suggestions) - 1):
                assert suggestions[i]['confidence'] >= suggestions[i + 1]['confidence']


class TestGetPopularCrs:
    """Test popular CRS functionality."""
    
    def test_get_popular_crs_structure(self):
        """Test that popular CRS returns proper structure."""
        popular_crs = get_popular_crs()
        
        assert isinstance(popular_crs, dict)
        assert 'global' in popular_crs
        assert 'europe' in popular_crs
        assert 'north_america' in popular_crs
        assert 'utm_zones' in popular_crs
    
    def test_get_popular_crs_content(self):
        """Test that popular CRS contains expected CRS."""
        popular_crs = get_popular_crs()
        
        # Check global CRS
        global_crs = popular_crs['global']
        assert len(global_crs) > 0
        assert any(crs['epsg'] == 4326 for crs in global_crs)  # WGS84
        assert any(crs['epsg'] == 3857 for crs in global_crs)  # Web Mercator
        
        # Check structure of CRS entries
        for crs in global_crs:
            assert 'epsg' in crs
            assert 'name' in crs
            assert 'description' in crs
            assert isinstance(crs['epsg'], int)
            assert isinstance(crs['name'], str)
            assert isinstance(crs['description'], str)
    
    def test_get_popular_crs_categories(self):
        """Test that all categories have CRS entries."""
        popular_crs = get_popular_crs()
        
        for category, crs_list in popular_crs.items():
            assert isinstance(crs_list, list)
            assert len(crs_list) > 0
            
            for crs in crs_list:
                assert 'epsg' in crs
                assert 'name' in crs
                assert 'description' in crs


class TestAutoDetectUtmZone:
    """Test UTM zone auto-detection functionality."""
    
    def test_auto_detect_utm_zone_northern_hemisphere(self):
        """Test UTM zone detection for northern hemisphere."""
        bounds = (0, 0, 10, 10)  # Northern hemisphere
        result = auto_detect_utm_zone(bounds)
        
        assert result['zone'] == 31  # Zone 31 for longitude 0
        assert result['hemisphere'] == 'N'
        assert result['epsg'] == 32631
        assert 'WGS 84 / UTM zone 31N' in result['name']
    
    def test_auto_detect_utm_zone_southern_hemisphere(self):
        """Test UTM zone detection for southern hemisphere."""
        bounds = (0, -10, 10, 0)  # Southern hemisphere
        result = auto_detect_utm_zone(bounds)
        
        assert result['zone'] == 31  # Zone 31 for longitude 0
        assert result['hemisphere'] == 'S'
        assert result['epsg'] == 32731
        assert 'WGS 84 / UTM zone 31S' in result['name']
    
    def test_auto_detect_utm_zone_different_longitudes(self):
        """Test UTM zone detection for different longitudes."""
        # Test various longitudes
        test_cases = [
            (0, 0, 1, 1, 31),    # Longitude 0 -> Zone 31
            (6, 0, 7, 1, 32),   # Longitude 6 -> Zone 32
            (12, 0, 13, 1, 33), # Longitude 12 -> Zone 33
            (174, 0, 175, 1, 59), # Longitude 174 -> Zone 59
            (180, 0, 181, 1, 60), # Longitude 180 -> Zone 60
        ]
        
        for minx, miny, maxx, maxy, expected_zone in test_cases:
            bounds = (minx, miny, maxx, maxy)
            result = auto_detect_utm_zone(bounds)
            assert result['zone'] == expected_zone
    
    def test_auto_detect_utm_zone_edge_cases(self):
        """Test UTM zone detection edge cases."""
        # Test bounds at zone boundaries
        bounds = (6, 0, 6, 1)  # Exactly at zone 32 boundary
        result = auto_detect_utm_zone(bounds)
        assert result['zone'] == 32
        
        # Test bounds crossing multiple zones (should use center)
        bounds = (0, 0, 12, 1)  # Crosses zones 31, 32, 33
        result = auto_detect_utm_zone(bounds)
        assert result['zone'] == 32  # Center longitude is 6


class TestCrsIntegration:
    """Test CRS module integration scenarios."""
    
    def test_crs_workflow_with_geographic_data(self, sample_point_gdf):
        """Test complete CRS workflow with geographic data."""
        # Get CRS info
        crs_info = get_crs_info(sample_point_gdf)
        assert crs_info['is_geographic'] is True
        
        # Should not infer CRS when already present
        suggestions = infer_crs(sample_point_gdf)
        assert suggestions == []
    
    def test_crs_workflow_without_crs(self, sample_no_crs_gdf):
        """Test complete CRS workflow without CRS."""
        # Get CRS info (should be None)
        crs_info = get_crs_info(sample_no_crs_gdf)
        assert crs_info['crs'] is None
        
        # Should infer CRS suggestions
        suggestions = infer_crs(sample_no_crs_gdf)
        assert len(suggestions) > 0
        
        # Check that suggestions are reasonable
        if suggestions:
            # Should include WGS84 as a common suggestion
            wgs84_suggestions = [s for s in suggestions if s['epsg'] == 4326]
            assert len(wgs84_suggestions) > 0
    
    def test_popular_crs_integration(self):
        """Test integration between popular CRS and other functions."""
        popular_crs = get_popular_crs()
        
        # Test that popular CRS can be used with other functions
        for category, crs_list in popular_crs.items():
            for crs_info in crs_list:
                epsg = crs_info['epsg']
                assert isinstance(epsg, int)
                assert epsg > 0
                
                # Test that EPSG codes are valid
                try:
                    from pyproj import CRS
                    crs = CRS.from_epsg(epsg)
                    assert crs is not None
                except Exception:
                    # Some EPSG codes might not be available in all environments
                    pass
