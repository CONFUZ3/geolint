"""
Tests for the batch module.
"""

import pytest
import geopandas as gpd
from shapely.geometry import Point

from geolint.core.batch import BatchProcessor


class TestBatchProcessor:
    """Test BatchProcessor functionality."""
    
    def test_batch_processor_initialization(self):
        """Test BatchProcessor initialization."""
        processor = BatchProcessor()
        
        assert processor.datasets == []
        assert processor.validation_reports == []
        assert processor.processing_reports == []
    
    def test_add_dataset(self, sample_point_gdf):
        """Test adding dataset to processor."""
        processor = BatchProcessor()
        index = processor.add_dataset(sample_point_gdf, "test_dataset")
        
        assert index == 0
        assert len(processor.datasets) == 1
        assert processor.datasets[0]['name'] == "test_dataset"
        assert processor.datasets[0]['index'] == 0
        assert len(processor.datasets[0]['gdf']) == len(sample_point_gdf)
    
    def test_add_dataset_from_file(self, sample_geopackage):
        """Test adding dataset from file."""
        processor = BatchProcessor()
        index, report = processor.add_dataset_from_file(sample_geopackage, "test_file")
        
        assert index == 0
        assert isinstance(report, dict)
        assert len(processor.datasets) == 1
        assert processor.datasets[0]['name'] == "test_file"
    
    def test_validate_batch(self, sample_point_gdf):
        """Test batch validation."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        result = processor.validate_batch()
        
        assert result['total_datasets'] == 2
        assert result['validated'] == 2
        assert len(result['results']) == 2
        assert 'crs_analysis' in result
        
        for dataset_result in result['results']:
            assert 'name' in dataset_result
            assert 'index' in dataset_result
            assert 'feature_count' in dataset_result
            assert 'has_crs' in dataset_result
            assert 'geometry_issues' in dataset_result
    
    def test_validate_batch_empty(self):
        """Test batch validation with no datasets."""
        processor = BatchProcessor()
        result = processor.validate_batch()
        
        assert result['total_datasets'] == 0
        assert result['validated'] == 0
        assert result['results'] == []
    
    def test_unify_crs_manual(self, sample_point_gdf):
        """Test CRS unification with manual strategy."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        result = processor.unify_crs("EPSG:3857", "manual")
        
        assert result['target_crs'] == "EPSG:3857"
        assert result['strategy'] == "manual"
        assert result['unified'] == 2
        assert result['failed'] == 0
        assert len(result['results']) == 2
    
    def test_unify_crs_auto_detect(self, sample_point_gdf):
        """Test CRS unification with auto-detect strategy."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        result = processor.unify_crs("EPSG:3857", "auto_detect")
        
        assert result['strategy'] == "auto_detect"
        assert result['unified'] == 2
        assert result['failed'] == 0
    
    def test_unify_crs_use_most_common(self, sample_point_gdf):
        """Test CRS unification with use most common strategy."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        result = processor.unify_crs("EPSG:3857", "use_most_common")
        
        assert result['strategy'] == "use_most_common"
        assert result['unified'] == 2
        assert result['failed'] == 0
    
    def test_fix_geometries_batch(self, sample_point_gdf):
        """Test batch geometry fixing."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        result = processor.fix_geometries_batch(
            fix_invalid=True,
            remove_empty=True,
            explode_multipart=False,
            simplify=False
        )
        
        assert result['processed'] == 2
        assert result['total_datasets'] == 2
        assert len(result['results']) == 2
        
        for dataset_result in result['results']:
            assert dataset_result['success'] is True
            assert 'original_count' in dataset_result
            assert 'final_count' in dataset_result
    
    def test_merge_datasets(self, sample_point_gdf):
        """Test dataset merging."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        merged_gdf, report = processor.merge_datasets()
        
        assert isinstance(merged_gdf, gpd.GeoDataFrame)
        assert len(merged_gdf) == len(sample_point_gdf) * 2
        assert report['merged_datasets'] == 2
        assert report['total_features'] == len(merged_gdf)
        assert report['strategy'] == "union"
        assert report['source_tracking'] is True
        
        # Check source tracking
        if 'source_dataset' in merged_gdf.columns:
            assert merged_gdf['source_dataset'].nunique() == 2
    
    def test_merge_datasets_empty(self):
        """Test merging empty dataset list."""
        processor = BatchProcessor()
        merged_gdf, report = processor.merge_datasets()
        
        assert isinstance(merged_gdf, gpd.GeoDataFrame)
        assert len(merged_gdf) == 0
        assert report['merged_datasets'] == 0
        assert report['total_features'] == 0
    
    def test_process_batch_complete(self, sample_point_gdf):
        """Test complete batch processing pipeline."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        # Track progress
        progress_calls = []
        def progress_callback(current, message):
            progress_calls.append((current, message))
        
        result = processor.process_batch(
            unify_crs=True,
            target_crs="EPSG:3857",
            crs_strategy="manual",
            fix_geometries=True,
            merge_datasets=True,
            progress_callback=progress_callback
        )
        
        assert result['success'] is True
        assert result['total_datasets'] == 2
        assert len(result['processing_steps']) > 0
        assert result['final_dataset'] is not None
        
        # Check progress was called
        assert len(progress_calls) > 0
    
    def test_process_batch_failure(self, sample_no_crs_gdf):
        """Test batch processing with failure scenarios."""
        processor = BatchProcessor()
        processor.add_dataset(sample_no_crs_gdf, "dataset1")
        
        result = processor.process_batch(
            unify_crs=True,
            target_crs="EPSG:3857",
            crs_strategy="manual",
            fix_geometries=True,
            merge_datasets=False
        )
        
        # Should still succeed but with warnings
        assert result['success'] is True
        assert result['total_datasets'] == 1
    
    def test_get_dataset_summary(self, sample_point_gdf):
        """Test getting dataset summary."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        summaries = processor.get_dataset_summary()
        
        assert len(summaries) == 2
        
        for summary in summaries:
            assert 'name' in summary
            assert 'index' in summary
            assert 'feature_count' in summary
            assert 'has_crs' in summary
            assert 'crs_epsg' in summary
            assert 'crs_name' in summary
            assert 'geometry_types' in summary
            assert 'invalid_geometries' in summary
            assert 'empty_geometries' in summary
    
    def test_clear(self, sample_point_gdf):
        """Test clearing processor."""
        processor = BatchProcessor()
        processor.add_dataset(sample_point_gdf, "dataset1")
        
        assert len(processor.datasets) == 1
        
        processor.clear()
        
        assert len(processor.datasets) == 0
        assert len(processor.validation_reports) == 0
        assert len(processor.processing_reports) == 0


class TestBatchProcessorIntegration:
    """Test BatchProcessor integration scenarios."""
    
    def test_full_workflow(self, sample_point_gdf):
        """Test complete workflow from add to process."""
        processor = BatchProcessor()
        
        # Add datasets
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        
        # Validate
        validation_result = processor.validate_batch()
        assert validation_result['total_datasets'] == 2
        
        # Unify CRS
        crs_result = processor.unify_crs("EPSG:3857", "manual")
        assert crs_result['unified'] == 2
        
        # Fix geometries
        geom_result = processor.fix_geometries_batch(fix_invalid=True)
        assert geom_result['processed'] == 2
        
        # Merge datasets
        merged_gdf, merge_report = processor.merge_datasets()
        assert len(merged_gdf) == len(sample_point_gdf) * 2
        
        # Get summary
        summaries = processor.get_dataset_summary()
        assert len(summaries) == 2
    
    def test_error_handling(self):
        """Test error handling in batch processing."""
        processor = BatchProcessor()
        
        # Test with empty processor
        result = processor.validate_batch()
        assert result['total_datasets'] == 0
        
        result = processor.unify_crs("EPSG:3857", "manual")
        assert result['unified'] == 0
        
        result = processor.fix_geometries_batch()
        assert result['processed'] == 0
        
        merged_gdf, report = processor.merge_datasets()
        assert len(merged_gdf) == 0
