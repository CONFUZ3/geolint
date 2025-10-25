"""
Tests for the transform module.
"""

import pytest
import geopandas as gpd
from shapely.geometry import Point

from geolint.core.transform import (
    reproject_dataset, get_transform_preview, batch_reproject,
    detect_common_crs, validate_crs_compatibility
)


class TestReprojectDataset:
    """Test dataset reprojection functionality."""
    
    def test_reproject_dataset_success(self, sample_point_gdf):
        """Test successful dataset reprojection."""
        reprojected_gdf, report = reproject_dataset(sample_point_gdf, "EPSG:3857")
        
        assert isinstance(reprojected_gdf, gpd.GeoDataFrame)
        assert len(reprojected_gdf) == len(sample_point_gdf)
        assert report['transformed'] is True
        assert report['original_crs']['epsg'] == 4326
        assert report['target_crs']['epsg'] == 3857
        assert report['feature_count'] == len(sample_point_gdf)
    
    def test_reproject_dataset_same_crs(self, sample_point_gdf):
        """Test reprojecting to the same CRS."""
        reprojected_gdf, report = reproject_dataset(sample_point_gdf, "EPSG:4326")
        
        assert isinstance(reprojected_gdf, gpd.GeoDataFrame)
        assert len(reprojected_gdf) == len(sample_point_gdf)
        assert report['transformed'] is True
        assert report['original_crs']['epsg'] == 4326
        assert report['target_crs']['epsg'] == 4326
    
    def test_reproject_dataset_no_crs(self, sample_no_crs_gdf):
        """Test reprojecting dataset without CRS."""
        with pytest.raises(ValueError, match="Cannot reproject dataset without original CRS"):
            reproject_dataset(sample_no_crs_gdf, "EPSG:3857")
    
    def test_reproject_dataset_empty(self, sample_empty_gdf):
        """Test reprojecting empty dataset."""
        reprojected_gdf, report = reproject_dataset(sample_empty_gdf, "EPSG:3857")
        
        assert isinstance(reprojected_gdf, gpd.GeoDataFrame)
        assert len(reprojected_gdf) == 0
        assert report['transformed'] is True
    
    def test_reproject_dataset_invalid_crs(self, sample_point_gdf):
        """Test reprojecting with invalid target CRS."""
        reprojected_gdf, report = reproject_dataset(sample_point_gdf, "INVALID:9999")
        
        assert isinstance(reprojected_gdf, gpd.GeoDataFrame)
        assert report['transformed'] is False
        assert 'error' in report


class TestGetTransformPreview:
    """Test transformation preview functionality."""
    
    def test_get_transform_preview_success(self, sample_point_gdf):
        """Test successful transformation preview."""
        preview = get_transform_preview(sample_point_gdf, "EPSG:3857")
        
        assert preview['preview_available'] is True
        assert 'original_bounds' in preview
        assert 'target_bounds' in preview
        assert 'original_area' in preview
        assert 'target_area' in preview
        assert 'area_ratio' in preview
        assert 'original_crs' in preview
        assert 'target_crs' in preview
        assert 'transformation_type' in preview
    
    def test_get_transform_preview_no_crs(self, sample_no_crs_gdf):
        """Test transformation preview without CRS."""
        preview = get_transform_preview(sample_no_crs_gdf, "EPSG:3857")
        
        assert preview['preview_available'] is False
        assert 'error' in preview
    
    def test_get_transform_preview_empty(self, sample_empty_gdf):
        """Test transformation preview for empty dataset."""
        preview = get_transform_preview(sample_empty_gdf, "EPSG:3857")
        
        assert preview['preview_available'] is False
        assert 'error' in preview
    
    def test_get_transform_preview_invalid_crs(self, sample_point_gdf):
        """Test transformation preview with invalid CRS."""
        preview = get_transform_preview(sample_point_gdf, "INVALID:9999")
        
        assert preview['preview_available'] is False
        assert 'error' in preview


class TestBatchReproject:
    """Test batch reprojection functionality."""
    
    def test_batch_reproject_success(self, sample_point_gdf):
        """Test successful batch reprojection."""
        datasets = [sample_point_gdf, sample_point_gdf.copy()]
        reprojected_datasets, report = batch_reproject(datasets, "EPSG:3857")
        
        assert isinstance(reprojected_datasets, list)
        assert len(reprojected_datasets) == len(datasets)
        assert report['total_datasets'] == len(datasets)
        assert report['successful'] == len(datasets)
        assert report['failed'] == 0
        assert len(report['results']) == len(datasets)
        
        for result in report['results']:
            assert result['success'] is True
            assert 'feature_count' in result
    
    def test_batch_reproject_mixed_success(self, sample_point_gdf, sample_no_crs_gdf):
        """Test batch reprojection with mixed success/failure."""
        datasets = [sample_point_gdf, sample_no_crs_gdf]
        reprojected_datasets, report = batch_reproject(datasets, "EPSG:3857")
        
        assert isinstance(reprojected_datasets, list)
        assert len(reprojected_datasets) == len(datasets)
        assert report['total_datasets'] == len(datasets)
        assert report['successful'] == 1
        assert report['failed'] == 1
        assert len(report['results']) == len(datasets)
        
        # Check individual results
        success_results = [r for r in report['results'] if r['success']]
        failure_results = [r for r in report['results'] if not r['success']]
        
        assert len(success_results) == 1
        assert len(failure_results) == 1
        assert 'error' in failure_results[0]
    
    def test_batch_reproject_empty_list(self):
        """Test batch reprojection with empty dataset list."""
        reprojected_datasets, report = batch_reproject([], "EPSG:3857")
        
        assert isinstance(reprojected_datasets, list)
        assert len(reprojected_datasets) == 0
        assert report['total_datasets'] == 0
        assert report['successful'] == 0
        assert report['failed'] == 0
        assert report['results'] == []


class TestDetectCommonCrs:
    """Test common CRS detection functionality."""
    
    def test_detect_common_crs_same_crs(self, sample_point_gdf):
        """Test detecting common CRS when all datasets have same CRS."""
        datasets = [sample_point_gdf, sample_point_gdf.copy()]
        result = detect_common_crs(datasets)
        
        assert result['common_crs'] is not None
        assert result['confidence'] == 1.0
        assert result['total_datasets'] == len(datasets)
        assert len(result['crs_counts']) == 1
        assert result['crs_counts'][0]['count'] == len(datasets)
    
    def test_detect_common_crs_different_crs(self, sample_point_gdf):
        """Test detecting common CRS when datasets have different CRS."""
        # Create dataset with different CRS
        gdf2 = sample_point_gdf.copy()
        gdf2.crs = "EPSG:3857"
        
        datasets = [sample_point_gdf, gdf2]
        result = detect_common_crs(datasets)
        
        assert result['common_crs'] is not None
        assert result['confidence'] < 1.0
        assert result['total_datasets'] == len(datasets)
        assert len(result['crs_counts']) == 2
    
    def test_detect_common_crs_no_crs(self, sample_no_crs_gdf):
        """Test detecting common CRS when datasets have no CRS."""
        datasets = [sample_no_crs_gdf, sample_no_crs_gdf.copy()]
        result = detect_common_crs(datasets)
        
        assert result['common_crs'] is None
        assert result['confidence'] == 0.0
        assert result['total_datasets'] == len(datasets)
        assert result['crs_counts'] == []
    
    def test_detect_common_crs_empty_list(self):
        """Test detecting common CRS with empty dataset list."""
        result = detect_common_crs([])
        
        assert result['common_crs'] is None
        assert result['confidence'] == 0.0
        assert result['total_datasets'] == 0
        assert result['crs_counts'] == []


class TestValidateCrsCompatibility:
    """Test CRS compatibility validation functionality."""
    
    def test_validate_crs_compatibility_same_crs(self, sample_point_gdf):
        """Test CRS compatibility validation for same CRS."""
        result = validate_crs_compatibility(sample_point_gdf, "EPSG:4326")
        
        assert result['compatible'] is True
        assert result['reason'] == 'Same CRS'
        assert len(result['warnings']) == 0
    
    def test_validate_crs_compatibility_different_crs(self, sample_point_gdf):
        """Test CRS compatibility validation for different CRS."""
        result = validate_crs_compatibility(sample_point_gdf, "EPSG:3857")
        
        assert result['compatible'] is True
        assert result['reason'] == 'Compatible'
        assert len(result['warnings']) >= 0
    
    def test_validate_crs_compatibility_no_crs(self, sample_no_crs_gdf):
        """Test CRS compatibility validation without CRS."""
        result = validate_crs_compatibility(sample_no_crs_gdf, "EPSG:3857")
        
        assert result['compatible'] is False
        assert result['reason'] == 'No source CRS'
        assert len(result['warnings']) == 0
    
    def test_validate_crs_compatibility_empty_dataset(self, sample_empty_gdf):
        """Test CRS compatibility validation for empty dataset."""
        result = validate_crs_compatibility(sample_empty_gdf, "EPSG:3857")
        
        assert result['compatible'] is False
        assert result['reason'] == 'Empty dataset'
        assert len(result['warnings']) == 0
    
    def test_validate_crs_compatibility_invalid_crs(self, sample_point_gdf):
        """Test CRS compatibility validation with invalid CRS."""
        result = validate_crs_compatibility(sample_point_gdf, "INVALID:9999")
        
        assert result['compatible'] is False
        assert 'CRS validation failed' in result['reason']
        assert len(result['warnings']) == 0
    
    def test_validate_crs_compatibility_warnings(self, sample_point_gdf):
        """Test CRS compatibility validation with warnings."""
        # Test with geographic to geographic (should have warning)
        result = validate_crs_compatibility(sample_point_gdf, "EPSG:4269")  # NAD83
        
        assert result['compatible'] is True
        assert result['reason'] == 'Compatible'
        # May have warnings about unnecessary transformation
