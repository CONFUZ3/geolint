"""
Coordinate transformation and reprojection functions.

Handles CRS reprojection, bounds tracking, and transformation previews.
"""

from typing import Dict, List, Tuple, Union

import geopandas as gpd
import numpy as np
from pyproj import CRS, Transformer


def reproject_dataset(
    gdf: gpd.GeoDataFrame, 
    target_crs: Union[str, int, CRS] = "EPSG:4326"
) -> Tuple[gpd.GeoDataFrame, Dict[str, Union[str, List[float], float]]]:
    """
    Reproject a GeoDataFrame to a target CRS.
    
    Args:
        gdf: GeoDataFrame to reproject
        target_crs: Target CRS (EPSG code, CRS string, or CRS object)
        
    Returns:
        Tuple of (reprojected_geodataframe, transformation_report)
        
    Raises:
        ValueError: If original CRS is missing or transformation fails
    """
    if gdf.empty:
        return gdf, {'error': 'Empty dataset', 'transformed': False}
    
    # Check if original CRS exists
    if gdf.crs is None:
        raise ValueError("Cannot reproject dataset without original CRS information")
    
    # Convert target CRS to CRS object if needed
    if isinstance(target_crs, (str, int)):
        target_crs = CRS.from_user_input(target_crs)
    
    # Get original bounds
    original_bounds = list(gdf.total_bounds)
    original_crs_info = {
        'crs': gdf.crs.to_string(),
        'epsg': gdf.crs.to_epsg(),
        'is_geographic': gdf.crs.is_geographic,
        'is_projected': gdf.crs.is_projected
    }
    
    try:
        # Perform reprojection
        reprojected_gdf = gdf.to_crs(target_crs)
        
        # Get new bounds
        new_bounds = list(reprojected_gdf.total_bounds)
        
        # Calculate area change
        original_area = _calculate_bounds_area(original_bounds)
        new_area = _calculate_bounds_area(new_bounds)
        area_ratio = new_area / original_area if original_area > 0 else 1.0
        
        # Create transformation report
        report = {
            'transformed': True,
            'original_crs': original_crs_info,
            'target_crs': {
                'crs': target_crs.to_string(),
                'epsg': target_crs.to_epsg(),
                'is_geographic': target_crs.is_geographic,
                'is_projected': target_crs.is_projected
            },
            'bounds_original': original_bounds,
            'bounds_target': new_bounds,
            'area_original': original_area,
            'area_target': new_area,
            'area_ratio': area_ratio,
            'feature_count': len(reprojected_gdf)
        }
        
        return reprojected_gdf, report
        
    except Exception as e:
        return gdf, {
            'transformed': False,
            'error': str(e),
            'original_crs': original_crs_info,
            'target_crs': target_crs.to_string() if hasattr(target_crs, 'to_string') else str(target_crs)
        }


def get_transform_preview(
    gdf: gpd.GeoDataFrame, 
    target_crs: Union[str, int, CRS] = "EPSG:4326"
) -> Dict[str, Union[str, List[float], bool]]:
    """
    Get a preview of transformation without actually transforming the data.
    
    Args:
        gdf: GeoDataFrame to analyze
        target_crs: Target CRS for preview
        
    Returns:
        Dictionary with transformation preview information
    """
    if gdf.empty:
        return {'error': 'Empty dataset', 'preview_available': False}
    
    if gdf.crs is None:
        return {'error': 'No CRS information available', 'preview_available': False}
    
    try:
        # Convert target CRS
        if isinstance(target_crs, (str, int)):
            target_crs = CRS.from_user_input(target_crs)
        
        # Get original bounds
        original_bounds = list(gdf.total_bounds)
        
        # Create transformer
        transformer = Transformer.from_crs(gdf.crs, target_crs, always_xy=True)
        
        # Transform bounds corners
        corners = [
            (original_bounds[0], original_bounds[1]),  # minx, miny
            (original_bounds[2], original_bounds[3]),  # maxx, maxy
            (original_bounds[0], original_bounds[3]),  # minx, maxy
            (original_bounds[2], original_bounds[1])   # maxx, miny
        ]
        
        transformed_corners = [transformer.transform(x, y) for x, y in corners]
        
        # Calculate new bounds
        x_coords = [pt[0] for pt in transformed_corners]
        y_coords = [pt[1] for pt in transformed_corners]
        
        new_bounds = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
        
        # Calculate area change
        original_area = _calculate_bounds_area(original_bounds)
        new_area = _calculate_bounds_area(new_bounds)
        area_ratio = new_area / original_area if original_area > 0 else 1.0
        
        return {
            'preview_available': True,
            'original_bounds': original_bounds,
            'target_bounds': new_bounds,
            'original_area': original_area,
            'target_area': new_area,
            'area_ratio': area_ratio,
            'original_crs': gdf.crs.to_string(),
            'target_crs': target_crs.to_string(),
            'transformation_type': _get_transformation_type(gdf.crs, target_crs)
        }
        
    except Exception as e:
        return {
            'preview_available': False,
            'error': str(e),
            'original_crs': gdf.crs.to_string() if gdf.crs else None
        }


def _calculate_bounds_area(bounds: List[float]) -> float:
    """Calculate area of a bounding box."""
    if len(bounds) != 4:
        return 0.0
    
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    return width * height


def _get_transformation_type(original_crs: CRS, target_crs: CRS) -> str:
    """Determine the type of transformation."""
    if original_crs.is_geographic and target_crs.is_geographic:
        return "geographic_to_geographic"
    elif original_crs.is_geographic and target_crs.is_projected:
        return "geographic_to_projected"
    elif original_crs.is_projected and target_crs.is_geographic:
        return "projected_to_geographic"
    elif original_crs.is_projected and target_crs.is_projected:
        return "projected_to_projected"
    else:
        return "unknown"


def batch_reproject(
    datasets: List[gpd.GeoDataFrame], 
    target_crs: Union[str, int, CRS] = "EPSG:4326"
) -> Tuple[List[gpd.GeoDataFrame], Dict[str, Union[int, List[Dict]]]]:
    """
    Reproject multiple datasets to the same target CRS.
    
    Args:
        datasets: List of GeoDataFrames to reproject
        target_crs: Target CRS for all datasets
        
    Returns:
        Tuple of (reprojected_datasets, batch_report)
    """
    if not datasets:
        return [], {'total_datasets': 0, 'successful': 0, 'failed': 0, 'results': []}
    
    reprojected_datasets = []
    results = []
    successful = 0
    failed = 0
    
    for i, gdf in enumerate(datasets):
        try:
            reprojected_gdf, report = reproject_dataset(gdf, target_crs)
            reprojected_datasets.append(reprojected_gdf)
            results.append({
                'dataset_index': i,
                'success': True,
                'feature_count': len(reprojected_gdf),
                'report': report
            })
            successful += 1
            
        except Exception as e:
            reprojected_datasets.append(gdf)  # Keep original on failure
            results.append({
                'dataset_index': i,
                'success': False,
                'error': str(e),
                'feature_count': len(gdf)
            })
            failed += 1
    
    batch_report = {
        'total_datasets': len(datasets),
        'successful': successful,
        'failed': failed,
        'target_crs': str(target_crs),
        'results': results
    }
    
    return reprojected_datasets, batch_report


def detect_common_crs(datasets: List[gpd.GeoDataFrame]) -> Dict[str, Union[str, int, List[Dict]]]:
    """
    Detect the most common CRS among multiple datasets.
    
    Args:
        datasets: List of GeoDataFrames to analyze
        
    Returns:
        Dictionary with common CRS information
    """
    if not datasets:
        return {'common_crs': None, 'confidence': 0.0, 'crs_counts': []}
    
    # Count CRS occurrences
    crs_counts = {}
    crs_details = {}
    
    for gdf in datasets:
        if gdf.crs is not None:
            crs_str = gdf.crs.to_string()
            crs_counts[crs_str] = crs_counts.get(crs_str, 0) + 1
            crs_details[crs_str] = {
                'epsg': gdf.crs.to_epsg(),
                'name': gdf.crs.name,
                'is_geographic': gdf.crs.is_geographic,
                'is_projected': gdf.crs.is_projected
            }
    
    if not crs_counts:
        return {'common_crs': None, 'confidence': 0.0, 'crs_counts': []}
    
    # Find most common CRS
    most_common_crs = max(crs_counts, key=crs_counts.get)
    total_datasets = len(datasets)
    confidence = crs_counts[most_common_crs] / total_datasets
    
    # Create CRS counts list
    crs_counts_list = [
        {
            'crs': crs,
            'count': count,
            'percentage': (count / total_datasets) * 100,
            'details': crs_details[crs]
        }
        for crs, count in sorted(crs_counts.items(), key=lambda x: x[1], reverse=True)
    ]
    
    return {
        'common_crs': most_common_crs,
        'confidence': confidence,
        'total_datasets': total_datasets,
        'crs_counts': crs_counts_list
    }


def validate_crs_compatibility(
    gdf: gpd.GeoDataFrame, 
    target_crs: Union[str, int, CRS]
) -> Dict[str, Union[bool, str, List[str]]]:
    """
    Validate if a dataset can be transformed to a target CRS.
    
    Args:
        gdf: GeoDataFrame to validate
        target_crs: Target CRS to check compatibility
        
    Returns:
        Dictionary with compatibility information
    """
    if gdf.empty:
        return {'compatible': False, 'reason': 'Empty dataset', 'warnings': []}
    
    if gdf.crs is None:
        return {'compatible': False, 'reason': 'No source CRS', 'warnings': []}
    
    warnings = []
    
    try:
        # Convert target CRS
        if isinstance(target_crs, (str, int)):
            target_crs = CRS.from_user_input(target_crs)
        
        # Check if CRS are the same
        if gdf.crs == target_crs:
            return {'compatible': True, 'reason': 'Same CRS', 'warnings': []}
        
        # Check for potential issues
        if gdf.crs.is_geographic and target_crs.is_geographic:
            warnings.append("Both CRS are geographic - transformation may be unnecessary")
        
        if gdf.crs.is_projected and target_crs.is_projected:
            # Check if both are UTM zones
            if (hasattr(gdf.crs, 'to_epsg') and hasattr(target_crs, 'to_epsg')):
                src_epsg = gdf.crs.to_epsg()
                tgt_epsg = target_crs.to_epsg()
                if (32601 <= src_epsg <= 32660 or 32701 <= src_epsg <= 32760) and \
                   (32601 <= tgt_epsg <= 32660 or 32701 <= tgt_epsg <= 32760):
                    warnings.append("Both CRS are UTM zones - check if zones are appropriate")
        
        # Test transformation with bounds
        try:
            _ = gdf.total_bounds
            transformer = Transformer.from_crs(gdf.crs, target_crs, always_xy=True)
            # Test with center point
            center_lon = (gdf.total_bounds[0] + gdf.total_bounds[2]) / 2
            center_lat = (gdf.total_bounds[1] + gdf.total_bounds[3]) / 2
            _ = transformer.transform(center_lon, center_lat)
            
        except Exception as e:
            return {'compatible': False, 'reason': f'Transformation test failed: {str(e)}', 'warnings': warnings}
        
        return {'compatible': True, 'reason': 'Compatible', 'warnings': warnings}
        
    except Exception as e:
        return {'compatible': False, 'reason': f'CRS validation failed: {str(e)}', 'warnings': []}
