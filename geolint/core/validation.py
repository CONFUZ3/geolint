"""
Validation engine for geospatial datasets.

Handles dataset loading, file integrity checks, and geometry validation.
"""

import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Tuple, Union

import geopandas as gpd
import pandas as pd

from geolint.core.checks import run_checks


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
    suffix = path.suffix.lower()
    if suffix == '.zip':
        return _load_shapefile_zip(path)
    elif suffix in ['.gpkg', '.geojson']:
        return gpd.read_file(path)
    elif suffix == '.kml':
        gdf = gpd.read_file(path, driver="KML")
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        return gdf
    elif suffix == '.parquet':
        return gpd.read_parquet(path)
    elif suffix == '.csv':
        return _load_csv(path)
    else:
        # Try to read as any supported format
        try:
            return gpd.read_file(path)
        except Exception as e:
            raise ValueError(f"Unsupported file format: {path.suffix}. Error: {e}")


def _load_csv(csv_path: Path) -> gpd.GeoDataFrame:
    """
    Load a CSV file as point geometries.

    Auto-detects longitude/latitude columns by case-insensitive name match,
    builds point geometry and wraps in an EPSG:4326 GeoDataFrame.
    """
    df = pd.read_csv(csv_path)

    lon_candidates = ['lon', 'lng', 'long', 'longitude', 'x']
    lat_candidates = ['lat', 'latitude', 'y']

    lower_cols = {str(c).lower(): c for c in df.columns}
    lon_col = next((lower_cols[c] for c in lon_candidates if c in lower_cols), None)
    lat_col = next((lower_cols[c] for c in lat_candidates if c in lower_cols), None)

    if lon_col is None or lat_col is None:
        raise ValueError("No latitude/longitude columns found in CSV")

    geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def _load_shapefile_zip(zip_path: Path) -> gpd.GeoDataFrame:
    """
    Load a shapefile from a zip archive.
    
    Extracts to temporary directory, loads the shapefile, then cleans up.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Extract zip file
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)
        except zipfile.BadZipFile as e:
            raise ValueError(f"Corrupt or invalid zip file: {e}")
        
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
        - missing_files: list of missing required extensions (e.g. ['.shx', '.dbf'])
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
        - null_count: int (geometries that are None)
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
            'null_count': 0,
            'mixed_types': False,
            'geometry_types': [],
            'multipart_count': 0,
            'invalid_indices': []
        }

    # Safe handling of None geometries (GeoPandas/Shapely can raise on None)
    null_mask = gdf.geometry.isna()
    valid_mask = gdf.geometry.apply(lambda g: g.is_valid if g is not None else False)
    empty_mask = gdf.geometry.apply(lambda g: g.is_empty if g is not None else True)

    # Basic counts
    total_features = len(gdf)
    null_count = int(null_mask.sum())
    valid_count = int(valid_mask.sum())
    invalid_count = total_features - valid_count

    # Empty geometries (include None as empty for count)
    empty_count = int(empty_mask.sum())

    # Geometry types (skip None)
    geom_types_series = gdf.geometry.apply(lambda g: getattr(g, 'geom_type', None) if g is not None else None)
    geometry_types = geom_types_series.dropna().unique().tolist()
    mixed_types = len(geometry_types) > 1

    # Multipart geometries
    multipart_mask = geom_types_series.apply(lambda t: str(t).startswith('Multi') if t else False)
    multipart_count = int(multipart_mask.sum())

    # Invalid geometry indices (invalid or null)
    invalid_indices = gdf[~valid_mask].index.tolist()
    
    return {
        'total_features': total_features,
        'valid_count': valid_count,
        'invalid_count': invalid_count,
        'empty_count': empty_count,
        'null_count': null_count,
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
        'checks': {},
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

        # Run extended checks (topology, attributes, coordinates)
        checks = run_checks(gdf)
        report['checks'] = checks

        def _sub(*keys):
            """Defensively walk nested check dicts; return {} on any miss/error."""
            node = checks
            for key in keys:
                if not isinstance(node, dict):
                    return {}
                node = node.get(key, {})
            return node if isinstance(node, dict) else {}

        dup_geom = _sub('topology', 'duplicate_geometries')
        if dup_geom.get('duplicate_count', 0) > 0:
            report['warnings'].append(f"Found {dup_geom['duplicate_count']} duplicate geometries")

        overlaps = _sub('topology', 'overlapping_polygons')
        if not overlaps.get('skipped', False) and overlaps.get('overlap_pair_count', 0) > 0:
            report['warnings'].append(f"Found {overlaps['overlap_pair_count']} overlapping polygon pairs")

        id_uniq = _sub('attributes', 'id_uniqueness')
        if id_uniq.get('duplicate_count', 0) > 0:
            report['warnings'].append(
                f"Found {id_uniq['duplicate_count']} duplicate ID values in column '{id_uniq.get('id_column')}'"
            )

        winding = _sub('coordinates', 'winding_order')
        if winding.get('non_compliant_count', 0) > 0:
            report['warnings'].append(
                f"Found {winding['non_compliant_count']} polygons with non-RFC7946 winding order"
            )

        coord_range = _sub('coordinates', 'coordinate_range')
        if coord_range.get('applicable', False) and coord_range.get('out_of_range_count', 0) > 0:
            report['warnings'].append(
                f"Found {coord_range['out_of_range_count']} features with out-of-range coordinates"
            )

        shp_fields = _sub('attributes', 'shapefile_field_names')
        if (shp_fields.get('long_names') or shp_fields.get('truncation_collisions')
                or shp_fields.get('non_ascii_names')):
            report['warnings'].append("Shapefile-unsafe attribute field names detected")

        # Add warnings based on validation results
        if geom_validation['invalid_count'] > 0:
            report['warnings'].append(f"Found {geom_validation['invalid_count']} invalid geometries")
        
        if geom_validation['empty_count'] > 0:
            report['warnings'].append(f"Found {geom_validation['empty_count']} empty geometries")

        if geom_validation.get('null_count', 0) > 0:
            report['warnings'].append(f"Found {geom_validation['null_count']} null geometries")
        
        if geom_validation['mixed_types']:
            report['warnings'].append(f"Mixed geometry types detected: {geom_validation['geometry_types']}")
        
        if gdf.crs is None:
            report['warnings'].append("No CRS information found")
        
        # Overall status
        has_issues = (
            geom_validation['invalid_count'] > 0 or
            geom_validation['empty_count'] > 0 or
            geom_validation.get('null_count', 0) > 0 or
            gdf.crs is None
        )
        report['validation']['has_issues'] = has_issues
        report['validation']['status'] = 'issues_found' if has_issues else 'clean'
        
    except (FileNotFoundError, ValueError, OSError) as e:
        report['validation']['loaded_successfully'] = False
        report['errors'].append(f"Failed to load dataset: {str(e)}")
        report['validation']['status'] = 'error'
        gdf = gpd.GeoDataFrame()  # Return empty GeoDataFrame on error
    # Let unexpected exceptions (e.g. AttributeError, TypeError) propagate

    return report, gdf
