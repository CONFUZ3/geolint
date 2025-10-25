"""
Validation engine for geospatial datasets.

Handles dataset loading, file integrity checks, and geometry validation.
"""

import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Tuple, Union

import fiona
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, LineString


def load_dataset(path: Union[str, Path]) -> gpd.GeoDataFrame:
    """
    Load a geospatial dataset from various formats.
    
    Supports:
    - GeoPackage (.gpkg)
    - GeoJSON (.geojson)
    - Shapefile (.zip containing .shp/.shx/.dbf/.prj)
    
    Args:
        path: Path to the dataset file
        
    Returns:
        GeoDataFrame containing the loaded data
        
    Raises:
        ValueError: If file format is not supported
        FileNotFoundError: If file does not exist
    """
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Handle different file formats
    if path.suffix.lower() == '.zip':
        return _load_shapefile_zip(path)
    elif path.suffix.lower() in ['.gpkg', '.geojson']:
        return gpd.read_file(path)
    else:
        # Try to read as any supported format
        try:
            return gpd.read_file(path)
        except Exception as e:
            raise ValueError(f"Unsupported file format: {path.suffix}. Error: {e}")


def _load_shapefile_zip(zip_path: Path) -> gpd.GeoDataFrame:
    """
    Load a shapefile from a zip archive.
    
    Extracts to temporary directory, loads the shapefile, then cleans up.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Extract zip file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_path)
        
        # Find the .shp file
        shp_files = list(temp_path.glob("*.shp"))
        if not shp_files:
            raise ValueError("No .shp file found in zip archive")
        
        # Load the shapefile
        return gpd.read_file(shp_files[0])


def check_shapefile_bundle(zip_path: Path) -> Dict[str, Union[bool, str]]:
    """
    Check if a zip file contains a complete shapefile bundle.
    
    Args:
        zip_path: Path to the zip file
        
    Returns:
        Dictionary with bundle information:
        - has_shp: bool
        - has_shx: bool  
        - has_dbf: bool
        - has_prj: bool
        - is_complete: bool
        - missing_files: list of missing files
    """
    result = {
        'has_shp': False,
        'has_shx': False,
        'has_dbf': False,
        'has_prj': False,
        'is_complete': False,
        'missing_files': []
    }
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Check for required files
            result['has_shp'] = any(f.endswith('.shp') for f in file_list)
            result['has_shx'] = any(f.endswith('.shx') for f in file_list)
            result['has_dbf'] = any(f.endswith('.dbf') for f in file_list)
            result['has_prj'] = any(f.endswith('.prj') for f in file_list)
            
            # Determine if complete
            required_files = ['.shp', '.shx', '.dbf']
            missing = [ext for ext in required_files 
                      if not any(f.endswith(ext) for f in file_list)]
            
            result['missing_files'] = missing
            result['is_complete'] = len(missing) == 0
            
    except Exception as e:
        result['error'] = str(e)
    
    return result


def validate_geometries(gdf: gpd.GeoDataFrame) -> Dict[str, Union[int, bool, list]]:
    """
    Validate geometries in a GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame to validate
        
    Returns:
        Dictionary with validation results:
        - total_features: int
        - valid_count: int
        - invalid_count: int
        - empty_count: int
        - mixed_types: bool
        - geometry_types: list of unique geometry types
        - multipart_count: int
        - invalid_indices: list of indices with invalid geometries
    """
    if gdf.empty:
        return {
            'total_features': 0,
            'valid_count': 0,
            'invalid_count': 0,
            'empty_count': 0,
            'mixed_types': False,
            'geometry_types': [],
            'multipart_count': 0,
            'invalid_indices': []
        }
    
    # Basic counts
    total_features = len(gdf)
    valid_mask = gdf.geometry.is_valid
    valid_count = int(valid_mask.sum())
    invalid_count = total_features - valid_count
    
    # Empty geometries
    empty_mask = gdf.geometry.is_empty
    empty_count = int(empty_mask.sum())
    
    # Geometry types
    geometry_types = gdf.geom_type.unique().tolist()
    mixed_types = len(geometry_types) > 1
    
    # Multipart geometries
    multipart_mask = gdf.geom_type.str.startswith('Multi')
    multipart_count = int(multipart_mask.sum())
    
    # Invalid geometry indices
    invalid_indices = gdf[~valid_mask].index.tolist()
    
    return {
        'total_features': total_features,
        'valid_count': valid_count,
        'invalid_count': invalid_count,
        'empty_count': empty_count,
        'mixed_types': mixed_types,
        'geometry_types': geometry_types,
        'multipart_count': multipart_count,
        'invalid_indices': invalid_indices
    }


def run_validation(path: Union[str, Path]) -> Tuple[Dict, gpd.GeoDataFrame]:
    """
    Run comprehensive validation on a geospatial dataset.
    
    Args:
        path: Path to the dataset
        
    Returns:
        Tuple of (validation_report, loaded_geodataframe)
    """
    path = Path(path)
    
    # Initialize report
    report = {
        'file_path': str(path),
        'file_name': path.name,
        'file_size': path.stat().st_size if path.exists() else 0,
        'timestamp': pd.Timestamp.now().isoformat(),
        'validation': {},
        'shapefile_bundle': {},
        'geometry_validation': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        # Load dataset
        gdf = load_dataset(path)
        report['validation']['loaded_successfully'] = True
        report['validation']['feature_count'] = len(gdf)
        report['validation']['column_count'] = len(gdf.columns)
        report['validation']['crs_present'] = gdf.crs is not None
        
        # Check shapefile bundle if it's a zip file
        if path.suffix.lower() == '.zip':
            bundle_info = check_shapefile_bundle(path)
            report['shapefile_bundle'] = bundle_info
            
            if not bundle_info.get('is_complete', True):
                report['warnings'].append(f"Shapefile bundle incomplete. Missing: {bundle_info.get('missing_files', [])}")
            
            if not bundle_info.get('has_prj', False):
                report['warnings'].append("No .prj file found - CRS information may be missing")
        
        # Validate geometries
        geom_validation = validate_geometries(gdf)
        report['geometry_validation'] = geom_validation
        
        # Add warnings based on validation results
        if geom_validation['invalid_count'] > 0:
            report['warnings'].append(f"Found {geom_validation['invalid_count']} invalid geometries")
        
        if geom_validation['empty_count'] > 0:
            report['warnings'].append(f"Found {geom_validation['empty_count']} empty geometries")
        
        if geom_validation['mixed_types']:
            report['warnings'].append(f"Mixed geometry types detected: {geom_validation['geometry_types']}")
        
        if gdf.crs is None:
            report['warnings'].append("No CRS information found")
        
        # Overall status
        has_issues = (
            geom_validation['invalid_count'] > 0 or
            geom_validation['empty_count'] > 0 or
            gdf.crs is None
        )
        report['validation']['has_issues'] = has_issues
        report['validation']['status'] = 'issues_found' if has_issues else 'clean'
        
    except Exception as e:
        report['validation']['loaded_successfully'] = False
        report['errors'].append(f"Failed to load dataset: {str(e)}")
        report['validation']['status'] = 'error'
        gdf = gpd.GeoDataFrame()  # Return empty GeoDataFrame on error
    
    return report, gdf
