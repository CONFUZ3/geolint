"""
Tests for the validation module.
"""

import pytest
import geopandas as gpd
from pathlib import Path
import tempfile
import zipfile

from geolint.core.validation import (
    load_dataset, check_shapefile_bundle, validate_geometries, run_validation
)


class TestLoadDataset:
    """Test dataset loading functionality."""
    
    def test_load_geopackage(self, sample_geopackage):
        """Test loading a GeoPackage file."""
        gdf = load_dataset(sample_geopackage)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert gdf.crs == 'EPSG:4326'
    
    def test_load_geojson(self, sample_geojson):
        """Test loading a GeoJSON file."""
        gdf = load_dataset(sample_geojson)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert gdf.crs == 'EPSG:4326'
    
    def test_load_shapefile_zip(self, sample_shapefile_zip):
        """Test loading a shapefile from zip."""
        gdf = load_dataset(sample_shapefile_zip)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert gdf.crs == 'EPSG:4326'
    
    def test_load_nonexistent_file(self):
        """Test loading a non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_dataset("nonexistent.shp")
    
    def test_load_unsupported_format(self):
        """Test loading an unsupported file format."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_path.write_text("This is not a geospatial file")
        
        with pytest.raises(ValueError):
            load_dataset(tmp_path)
        
        tmp_path.unlink(missing_ok=True)


class TestCheckShapefileBundle:
    """Test shapefile bundle checking functionality."""
    
    def test_complete_shapefile_bundle(self, sample_shapefile_zip):
        """Test checking a complete shapefile bundle."""
        result = check_shapefile_bundle(sample_shapefile_zip)
        
        assert result['has_shp'] is True
        assert result['has_shx'] is True
        assert result['has_dbf'] is True
        assert result['is_complete'] is True
        assert result['missing_files'] == []
    
    def test_incomplete_shapefile_bundle(self):
        """Test checking an incomplete shapefile bundle."""
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
            zip_path = Path(tmp_file.name)
        
        # Create zip with only .shp file
        with tempfile.TemporaryDirectory() as temp_dir:
            shp_path = Path(temp_dir) / 'test.shp'
            shp_path.write_text("dummy shapefile content")
            
            with zipfile.ZipFile(zip_path, 'w') as zip_ref:
                zip_ref.write(shp_path, 'test.shp')
        
        result = check_shapefile_bundle(zip_path)
        
        assert result['has_shp'] is True
        assert result['has_shx'] is False
        assert result['has_dbf'] is False
        assert result['is_complete'] is False
        assert '.shx' in result['missing_files']
        assert '.dbf' in result['missing_files']
        
        # Cleanup
        zip_path.unlink(missing_ok=True)
    
    def test_nonexistent_zip(self):
        """Test checking a non-existent zip file."""
        result = check_shapefile_bundle(Path("nonexistent.zip"))
        assert 'error' in result


class TestValidateGeometries:
    """Test geometry validation functionality."""
    
    def test_validate_valid_geometries(self, sample_point_gdf):
        """Test validating valid geometries."""
        result = validate_geometries(sample_point_gdf)
        
        assert result['total_features'] == 5
        assert result['valid_count'] == 5
        assert result['invalid_count'] == 0
        assert result['empty_count'] == 0
        assert result['mixed_types'] is False
        assert result['geometry_types'] == ['Point']
        assert result['multipart_count'] == 0
        assert result['invalid_indices'] == []
    
    def test_validate_mixed_geometries(self, sample_mixed_gdf):
        """Test validating mixed geometry types."""
        result = validate_geometries(sample_mixed_gdf)
        
        assert result['total_features'] == 4
        assert result['mixed_types'] is True
        assert len(result['geometry_types']) == 3  # Point, LineString, Polygon
    
    def test_validate_invalid_geometries(self, sample_invalid_gdf):
        """Test validating geometries with invalid ones."""
        result = validate_geometries(sample_invalid_gdf)
        
        assert result['total_features'] == 3
        assert result['invalid_count'] > 0
        assert result['empty_count'] > 0
        assert len(result['invalid_indices']) > 0
    
    def test_validate_empty_gdf(self, sample_empty_gdf):
        """Test validating an empty GeoDataFrame."""
        result = validate_geometries(sample_empty_gdf)
        
        assert result['total_features'] == 0
        assert result['valid_count'] == 0
        assert result['invalid_count'] == 0
        assert result['empty_count'] == 0
        assert result['geometry_types'] == []


class TestRunValidation:
    """Test comprehensive validation functionality."""
    
    def test_validate_geopackage(self, sample_geopackage):
        """Test validating a GeoPackage file."""
        report, gdf = run_validation(sample_geopackage)
        
        assert isinstance(report, dict)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert report['validation']['loaded_successfully'] is True
        assert report['validation']['feature_count'] == 3
        assert report['validation']['crs_present'] is True
        assert report['validation']['status'] == 'clean'
        assert len(report['warnings']) == 0
        assert len(report['errors']) == 0
    
    def test_validate_shapefile_zip(self, sample_shapefile_zip):
        """Test validating a shapefile zip."""
        report, gdf = run_validation(sample_shapefile_zip)
        
        assert isinstance(report, dict)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert report['validation']['loaded_successfully'] is True
        assert 'shapefile_bundle' in report
        assert report['shapefile_bundle']['is_complete'] is True
    
    def test_validate_file_without_crs(self, sample_no_crs_gdf):
        """Test validating a file without CRS."""
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
            gpkg_path = Path(tmp_file.name)
        
        sample_no_crs_gdf.to_file(gpkg_path, driver='GPKG')
        
        report, gdf = run_validation(gpkg_path)
        
        assert report['validation']['crs_present'] is False
        assert 'No CRS information found' in report['warnings']
        assert report['validation']['status'] == 'issues_found'
        
        # Cleanup
        gpkg_path.unlink(missing_ok=True)
    
    def test_validate_nonexistent_file(self):
        """Test validating a non-existent file."""
        report, gdf = run_validation(Path("nonexistent.shp"))
        
        assert report['validation']['loaded_successfully'] is False
        assert len(report['errors']) > 0
        assert report['validation']['status'] == 'error'
        assert gdf.empty
    
    def test_validate_with_geometry_issues(self, sample_invalid_gdf):
        """Test validating a file with geometry issues."""
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
            gpkg_path = Path(tmp_file.name)
        
        sample_invalid_gdf.to_file(gpkg_path, driver='GPKG')
        
        report, gdf = run_validation(gpkg_path)
        
        assert report['validation']['has_issues'] is True
        assert report['validation']['status'] == 'issues_found'
        assert len(report['warnings']) > 0
        
        # Cleanup
        gpkg_path.unlink(missing_ok=True)
