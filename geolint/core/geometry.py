"""
Geometry repair and processing functions.

Handles geometry validation, fixing, and optimization operations.
"""

from typing import Dict, Tuple

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import Point, Polygon, LineString, MultiPoint, MultiPolygon, MultiLineString


def fix_geometries(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Fix invalid geometries using shapely.make_valid.
    
    Args:
        gdf: GeoDataFrame with potentially invalid geometries
        
    Returns:
        Tuple of (fixed_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'geometries_fixed': 0, 'geometries_removed': 0}
    
    fixed_gdf = gdf.copy()
    
    # Identify invalid geometries
    invalid_mask = ~fixed_gdf.geometry.is_valid
    invalid_count = int(invalid_mask.sum())
    
    # Fix invalid geometries
    if invalid_count > 0:
        fixed_gdf.loc[invalid_mask, 'geometry'] = fixed_gdf.loc[invalid_mask, 'geometry'].apply(
            lambda geom: make_valid(geom) if geom is not None else geom
        )
    
    # Check if any geometries became empty after fixing
    empty_after_fix = fixed_gdf.geometry.is_empty
    empty_count = int(empty_after_fix.sum())
    
    report = {
        'geometries_fixed': invalid_count,
        'geometries_removed': empty_count,
        'total_processed': len(fixed_gdf)
    }
    
    return fixed_gdf, report


def remove_empty_geometries(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Remove empty geometries from a GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame to process
        
    Returns:
        Tuple of (cleaned_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'geometries_removed': 0, 'remaining_count': 0}
    
    # Identify empty geometries
    empty_mask = gdf.geometry.is_empty
    empty_count = int(empty_mask.sum())
    
    # Remove empty geometries
    cleaned_gdf = gdf[~empty_mask].copy()
    
    report = {
        'geometries_removed': empty_count,
        'remaining_count': len(cleaned_gdf)
    }
    
    return cleaned_gdf, report


def explode_multipart(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Explode multipart geometries into singlepart geometries.
    
    Args:
        gdf: GeoDataFrame to process
        
    Returns:
        Tuple of (exploded_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'multipart_count': 0, 'exploded_count': 0, 'result_count': 0}
    
    # Identify multipart geometries
    multipart_mask = gdf.geom_type.str.startswith('Multi')
    multipart_count = int(multipart_mask.sum())
    
    if multipart_count == 0:
        return gdf, {'multipart_count': 0, 'exploded_count': 0, 'result_count': len(gdf)}
    
    # Explode multipart geometries
    exploded_gdf = gdf.explode(index_parts=True).reset_index(drop=True)
    
    report = {
        'multipart_count': multipart_count,
        'exploded_count': len(exploded_gdf) - len(gdf),
        'result_count': len(exploded_gdf)
    }
    
    return exploded_gdf, report


def simplify_geometries(gdf: gpd.GeoDataFrame, tolerance: float = 0.001) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Simplify geometries using Douglas-Peucker algorithm.
    
    Args:
        gdf: GeoDataFrame to process
        tolerance: Simplification tolerance (in CRS units)
        
    Returns:
        Tuple of (simplified_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'geometries_simplified': 0, 'original_vertices': 0, 'simplified_vertices': 0}
    
    simplified_gdf = gdf.copy()
    
    # Count original vertices
    original_vertices = sum(
        len(geom.exterior.coords) if hasattr(geom, 'exterior') else len(geom.coords)
        for geom in gdf.geometry if geom is not None
    )
    
    # Simplify geometries
    simplified_gdf['geometry'] = simplified_gdf['geometry'].apply(
        lambda geom: geom.simplify(tolerance) if geom is not None else geom
    )
    
    # Count simplified vertices
    simplified_vertices = sum(
        len(geom.exterior.coords) if hasattr(geom, 'exterior') else len(geom.coords)
        for geom in simplified_gdf.geometry if geom is not None
    )
    
    report = {
        'geometries_simplified': len(gdf),
        'original_vertices': original_vertices,
        'simplified_vertices': simplified_vertices,
        'vertices_reduced': original_vertices - simplified_vertices
    }
    
    return simplified_gdf, report


def validate_geometry_types(gdf: gpd.GeoDataFrame) -> Dict[str, int]:
    """
    Get detailed geometry type statistics.
    
    Args:
        gdf: GeoDataFrame to analyze
        
    Returns:
        Dictionary with geometry type counts
    """
    if gdf.empty:
        return {}
    
    type_counts = gdf.geom_type.value_counts().to_dict()
    
    # Add summary statistics
    type_counts['total_features'] = len(gdf)
    type_counts['unique_types'] = len(type_counts) - 1  # Subtract total_features
    
    return type_counts


def get_geometry_bounds(gdf: gpd.GeoDataFrame) -> Dict[str, float]:
    """
    Get detailed bounds information.
    
    Args:
        gdf: GeoDataFrame to analyze
        
    Returns:
        Dictionary with bounds information
    """
    if gdf.empty:
        return {
            'minx': 0, 'miny': 0, 'maxx': 0, 'maxy': 0,
            'width': 0, 'height': 0, 'area': 0
        }
    
    bounds = gdf.total_bounds
    minx, miny, maxx, maxy = bounds
    
    width = maxx - minx
    height = maxy - miny
    area = width * height
    
    return {
        'minx': minx,
        'miny': miny,
        'maxx': maxx,
        'maxy': maxy,
        'width': width,
        'height': height,
        'area': area
    }


def process_geometries(
    gdf: gpd.GeoDataFrame,
    fix_invalid: bool = True,
    remove_empty: bool = True,
    explode_multipart: bool = False,
    simplify: bool = False,
    simplify_tolerance: float = 0.001
) -> Tuple[gpd.GeoDataFrame, Dict[str, any]]:
    """
    Comprehensive geometry processing pipeline.
    
    Args:
        gdf: GeoDataFrame to process
        fix_invalid: Whether to fix invalid geometries
        remove_empty: Whether to remove empty geometries
        explode_multipart: Whether to explode multipart geometries
        simplify: Whether to simplify geometries
        simplify_tolerance: Simplification tolerance
        
    Returns:
        Tuple of (processed_geodataframe, comprehensive_report)
    """
    if gdf.empty:
        return gdf, {'operations': [], 'final_count': 0}
    
    processed_gdf = gdf.copy()
    operations = []
    total_removed = 0
    
    # Step 1: Fix invalid geometries
    if fix_invalid:
        processed_gdf, fix_report = fix_geometries(processed_gdf)
        operations.append({
            'operation': 'fix_invalid',
            'geometries_fixed': fix_report['geometries_fixed'],
            'geometries_removed': fix_report['geometries_removed']
        })
        total_removed += fix_report['geometries_removed']
    
    # Step 2: Remove empty geometries
    if remove_empty:
        processed_gdf, empty_report = remove_empty_geometries(processed_gdf)
        operations.append({
            'operation': 'remove_empty',
            'geometries_removed': empty_report['geometries_removed']
        })
        total_removed += empty_report['geometries_removed']
    
    # Step 3: Explode multipart geometries
    if explode_multipart:
        processed_gdf, explode_report = explode_multipart(processed_gdf)
        operations.append({
            'operation': 'explode_multipart',
            'multipart_count': explode_report['multipart_count'],
            'exploded_count': explode_report['exploded_count']
        })
    
    # Step 4: Simplify geometries
    if simplify:
        processed_gdf, simplify_report = simplify_geometries(processed_gdf, simplify_tolerance)
        operations.append({
            'operation': 'simplify',
            'geometries_simplified': simplify_report['geometries_simplified'],
            'vertices_reduced': simplify_report['vertices_reduced']
        })
    
    # Final statistics
    final_report = {
        'operations': operations,
        'original_count': len(gdf),
        'final_count': len(processed_gdf),
        'total_removed': total_removed,
        'geometry_types': validate_geometry_types(processed_gdf),
        'bounds': get_geometry_bounds(processed_gdf)
    }
    
    return processed_gdf, final_report
