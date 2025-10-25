"""
Integration tests for GeoLint end-to-end workflows.
"""

import pytest
import geopandas as gpd
import tempfile
from pathlib import Path
import zipfile

from geolint.core import (
    run_validation, get_crs_info, infer_crs, fix_geometries,
    reproject_dataset, generate_report, BatchProcessor
)


class TestSingleFileWorkflow:
    """Test complete single file processing workflow."""
    
    def test_single_file_workflow_clean_data(self, sample_point_gdf):
        """Test workflow with clean data."""
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
            gpkg_path = Path(tmp_file.name)
        
        try:
            sample_point_gdf.to_file(gpkg_path, driver='GPKG')
            
            # Step 1: Validation
            validation_report, gdf = run_validation(gpkg_path)
            assert validation_report['validation']['loaded_successfully'] is True
            assert validation_report['validation']['status'] == 'clean'
            
            # Step 2: CRS info
            crs_info = get_crs_info(gdf)
            assert crs_info['crs'] is not None
            assert crs_info['epsg'] == 4326
            
            # Step 3: CRS inference (should return empty for existing CRS)
            suggestions = infer_crs(gdf)
            assert suggestions == []
            
            # Step 4: Geometry processing (should not change clean data)
            processed_gdf, geom_report = fix_geometries(gdf)
            assert len(processed_gdf) == len(gdf)
            assert geom_report['geometries_fixed'] == 0
            
            # Step 5: Reprojection
            reprojected_gdf, transform_report = reproject_dataset(processed_gdf, "EPSG:3857")
            assert len(reprojected_gdf) == len(processed_gdf)
            assert transform_report['transformed'] is True
            
            # Step 6: Generate final report
            final_report = generate_report(
                validation_report,
                crs_info=crs_info,
                geometry_report=geom_report,
                transform_report=transform_report
            )
            
            assert final_report['health_score'] >= 80  # Should be high for clean data
            assert final_report['processing_summary']['status'] == 'completed'
            
        finally:
            gpkg_path.unlink(missing_ok=True)
    
    def test_single_file_workflow_issues_data(self, sample_invalid_gdf):
        """Test workflow with data that has issues."""
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
            gpkg_path = Path(tmp_file.name)
        
        try:
            sample_invalid_gdf.to_file(gpkg_path, driver='GPKG')
            
            # Step 1: Validation
            validation_report, gdf = run_validation(gpkg_path)
            assert validation_report['validation']['loaded_successfully'] is True
            assert validation_report['validation']['has_issues'] is True
            
            # Step 2: CRS info
            crs_info = get_crs_info(gdf)
            assert crs_info['crs'] is not None
            
            # Step 3: Geometry processing (should fix issues)
            processed_gdf, geom_report = fix_geometries(gdf)
            assert geom_report['geometries_fixed'] > 0 or geom_report['geometries_removed'] > 0
            
            # Step 4: Reprojection
            reprojected_gdf, transform_report = reproject_dataset(processed_gdf, "EPSG:3857")
            assert transform_report['transformed'] is True
            
            # Step 5: Generate final report
            final_report = generate_report(
                validation_report,
                crs_info=crs_info,
                geometry_report=geom_report,
                transform_report=transform_report
            )
            
            assert final_report['health_score'] < 100  # Should be lower due to issues
            assert final_report['processing_summary']['status'] == 'completed'
            
        finally:
            gpkg_path.unlink(missing_ok=True)
    
    def test_single_file_workflow_no_crs(self, sample_no_crs_gdf):
        """Test workflow with data without CRS."""
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
            gpkg_path = Path(tmp_file.name)
        
        try:
            sample_no_crs_gdf.to_file(gpkg_path, driver='GPKG')
            
            # Step 1: Validation
            validation_report, gdf = run_validation(gpkg_path)
            assert validation_report['validation']['loaded_successfully'] is True
            assert 'No CRS information found' in validation_report['warnings']
            
            # Step 2: CRS info (should be None)
            crs_info = get_crs_info(gdf)
            assert crs_info['crs'] is None
            
            # Step 3: CRS inference (should return suggestions)
            suggestions = infer_crs(gdf)
            assert len(suggestions) > 0
            assert all('confidence' in s for s in suggestions)
            
            # Step 4: Geometry processing
            processed_gdf, geom_report = fix_geometries(gdf)
            assert len(processed_gdf) == len(gdf)
            
            # Step 5: Cannot reproject without CRS
            with pytest.raises(ValueError, match="Cannot reproject dataset without original CRS"):
                reproject_dataset(processed_gdf, "EPSG:3857")
            
            # Step 6: Generate report without transformation
            final_report = generate_report(
                validation_report,
                crs_info=crs_info,
                geometry_report=geom_report
            )
            
            assert final_report['health_score'] < 100  # Should be lower due to missing CRS
            assert 'crs_info' in final_report
            assert final_report['crs_info']['crs'] is None
            
        finally:
            gpkg_path.unlink(missing_ok=True)


class TestBatchWorkflow:
    """Test complete batch processing workflow."""
    
    def test_batch_workflow_success(self, sample_point_gdf):
        """Test successful batch processing workflow."""
        processor = BatchProcessor()
        
        # Add multiple datasets
        processor.add_dataset(sample_point_gdf, "dataset1")
        processor.add_dataset(sample_point_gdf.copy(), "dataset2")
        processor.add_dataset(sample_point_gdf.copy(), "dataset3")
        
        # Step 1: Validate batch
        validation_result = processor.validate_batch()
        assert validation_result['total_datasets'] == 3
        assert validation_result['validated'] == 3
        
        # Step 2: Unify CRS
        crs_result = processor.unify_crs("EPSG:3857", "manual")
        assert crs_result['unified'] == 3
        assert crs_result['failed'] == 0
        
        # Step 3: Fix geometries
        geom_result = processor.fix_geometries_batch(fix_invalid=True, remove_empty=True)
        assert geom_result['processed'] == 3
        
        # Step 4: Merge datasets
        merged_gdf, merge_report = processor.merge_datasets()
        assert len(merged_gdf) == len(sample_point_gdf) * 3
        assert merge_report['merged_datasets'] == 3
        assert merge_report['total_features'] == len(merged_gdf)
        
        # Step 5: Get summary
        summaries = processor.get_dataset_summary()
        assert len(summaries) == 3
        
        for summary in summaries:
            assert 'name' in summary
            assert 'feature_count' in summary
            assert 'has_crs' in summary
    
    def test_batch_workflow_mixed_crs(self, sample_point_gdf):
        """Test batch processing with mixed CRS datasets."""
        processor = BatchProcessor()
        
        # Add datasets with different CRS
        gdf1 = sample_point_gdf.copy()
        gdf1.crs = "EPSG:4326"
        
        gdf2 = sample_point_gdf.copy()
        gdf2.crs = "EPSG:3857"
        
        processor.add_dataset(gdf1, "dataset1")
        processor.add_dataset(gdf2, "dataset2")
        
        # Validate batch
        validation_result = processor.validate_batch()
        assert validation_result['total_datasets'] == 2
        
        # Check CRS analysis
        crs_analysis = validation_result['crs_analysis']
        assert crs_analysis['confidence'] < 1.0  # Should be less than 100% due to mixed CRS
        
        # Unify CRS
        crs_result = processor.unify_crs("EPSG:4326", "manual")
        assert crs_result['unified'] == 2
        assert crs_result['failed'] == 0
    
    def test_batch_workflow_empty_processor(self):
        """Test batch processing with empty processor."""
        processor = BatchProcessor()
        
        # All operations should handle empty processor gracefully
        validation_result = processor.validate_batch()
        assert validation_result['total_datasets'] == 0
        
        crs_result = processor.unify_crs("EPSG:4326", "manual")
        assert crs_result['unified'] == 0
        
        geom_result = processor.fix_geometries_batch()
        assert geom_result['processed'] == 0
        
        merged_gdf, merge_report = processor.merge_datasets()
        assert len(merged_gdf) == 0
        assert merge_report['merged_datasets'] == 0


class TestShapefileWorkflow:
    """Test workflow with shapefile zip files."""
    
    def test_shapefile_workflow(self, sample_shapefile_zip):
        """Test complete workflow with shapefile zip."""
        # Step 1: Validation
        validation_report, gdf = run_validation(sample_shapefile_zip)
        assert validation_report['validation']['loaded_successfully'] is True
        assert validation_report['shapefile_bundle']['is_complete'] is True
        
        # Step 2: CRS info
        crs_info = get_crs_info(gdf)
        assert crs_info['crs'] is not None
        
        # Step 3: Geometry processing
        processed_gdf, geom_report = fix_geometries(gdf)
        assert len(processed_gdf) == len(gdf)
        
        # Step 4: Reprojection
        reprojected_gdf, transform_report = reproject_dataset(processed_gdf, "EPSG:3857")
        assert transform_report['transformed'] is True
        
        # Step 5: Generate report
        final_report = generate_report(
            validation_report,
            crs_info=crs_info,
            geometry_report=geom_report,
            transform_report=transform_report
        )
        
        assert final_report['health_score'] >= 0
        assert final_report['processing_summary']['status'] == 'completed'


class TestErrorHandling:
    """Test error handling in workflows."""
    
    def test_workflow_with_invalid_file(self):
        """Test workflow with invalid file."""
        # Create invalid file
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp_file:
            invalid_path = Path(tmp_file.name)
            invalid_path.write_text("This is not a geospatial file")
        
        try:
            # Validation should fail gracefully
            validation_report, gdf = run_validation(invalid_path)
            assert validation_report['validation']['loaded_successfully'] is False
            assert len(validation_report['errors']) > 0
            assert gdf.empty
            
        finally:
            invalid_path.unlink(missing_ok=True)
    
    def test_workflow_with_corrupted_zip(self):
        """Test workflow with corrupted zip file."""
        # Create corrupted zip
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
            corrupted_path = Path(tmp_file.name)
            corrupted_path.write_bytes(b"Not a valid zip file")
        
        try:
            # Validation should fail gracefully
            validation_report, gdf = run_validation(corrupted_path)
            assert validation_report['validation']['loaded_successfully'] is False
            assert len(validation_report['errors']) > 0
            assert gdf.empty
            
        finally:
            corrupted_path.unlink(missing_ok=True)
    
    def test_batch_workflow_with_errors(self, sample_point_gdf, sample_no_crs_gdf):
        """Test batch workflow with some errors."""
        processor = BatchProcessor()
        
        # Add mix of valid and invalid datasets
        processor.add_dataset(sample_point_gdf, "valid_dataset")
        processor.add_dataset(sample_no_crs_gdf, "no_crs_dataset")
        
        # Process batch
        result = processor.process_batch(
            unify_crs=True,
            target_crs="EPSG:3857",
            crs_strategy="manual",
            fix_geometries=True,
            merge_datasets=False
        )
        
        # Should still succeed but with some issues
        assert result['success'] is True
        assert result['total_datasets'] == 2
        assert len(result['processing_steps']) > 0


class TestPerformance:
    """Test performance characteristics."""
    
    def test_large_dataset_handling(self):
        """Test handling of larger datasets."""
        # Create larger dataset
        import numpy as np
        from shapely.geometry import Point
        
        n_points = 1000
        data = {
            'id': range(n_points),
            'geometry': [Point(i, i) for i in range(n_points)]
        }
        large_gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
            gpkg_path = Path(tmp_file.name)
        
        try:
            large_gdf.to_file(gpkg_path, driver='GPKG')
            
            # Test validation
            validation_report, gdf = run_validation(gpkg_path)
            assert validation_report['validation']['loaded_successfully'] is True
            assert validation_report['validation']['feature_count'] == n_points
            
            # Test geometry processing
            processed_gdf, geom_report = fix_geometries(gdf)
            assert len(processed_gdf) == n_points
            
            # Test reprojection
            reprojected_gdf, transform_report = reproject_dataset(processed_gdf, "EPSG:3857")
            assert len(reprojected_gdf) == n_points
            
        finally:
            gpkg_path.unlink(missing_ok=True)
