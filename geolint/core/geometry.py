"""
Geometry repair and processing functions.

Handles geometry validation, fixing, and optimization operations.
"""

from typing import Any, Dict, Tuple

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import Point, Polygon, LineString, MultiPoint, MultiPolygon, MultiLineString
from shapely.geometry.polygon import orient


def fix_geometries(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Fix invalid geometries using shapely.make_valid.
    
    Args:
        gdf: GeoDataFrame with potentially invalid geometries
        
    Returns:
        Tuple of (fixed_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'geometries_fixed': 0, 'geometries_removed': 0, 'total_processed': 0}
    
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


def _count_vertices(geom) -> int:
    """Count the coordinate vertices of any geometry type (incl. multipart)."""
    if geom is None or geom.is_empty:
        return 0
    geom_type = geom.geom_type
    if geom_type.startswith('Multi') or geom_type == 'GeometryCollection':
        return sum(_count_vertices(part) for part in geom.geoms)
    if geom_type == 'Polygon':
        return len(geom.exterior.coords) + sum(len(r.coords) for r in geom.interiors)
    return len(geom.coords)


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
    original_vertices = sum(_count_vertices(geom) for geom in gdf.geometry)
    
    # Simplify geometries
    simplified_gdf['geometry'] = simplified_gdf['geometry'].apply(
        lambda geom: geom.simplify(tolerance) if geom is not None else geom
    )
    
    # Count simplified vertices
    simplified_vertices = sum(_count_vertices(geom) for geom in simplified_gdf.geometry)
    
    report = {
        'geometries_simplified': len(gdf),
        'original_vertices': original_vertices,
        'simplified_vertices': simplified_vertices,
        'vertices_reduced': original_vertices - simplified_vertices
    }
    
    return simplified_gdf, report


def normalize_winding(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Normalize polygon winding order to the RFC 7946 right-hand rule.

    Applies shapely.geometry.polygon.orient(geom, sign=1.0) to each Polygon
    and MultiPolygon so that exterior rings are counter-clockwise (CCW) and
    interior rings (holes) are clockwise (CW). Non-polygon geometries are
    left untouched.

    Args:
        gdf: GeoDataFrame to process

    Returns:
        Tuple of (reoriented_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'polygons_reoriented': 0}

    reoriented_gdf = gdf.copy()
    reoriented_count = 0

    def _orient(geom):
        nonlocal reoriented_count
        if geom is None or geom.is_empty:
            return geom
        if isinstance(geom, (Polygon, MultiPolygon)):
            oriented = orient(geom, sign=1.0)
            if oriented.wkb != geom.wkb:
                reoriented_count += 1
            return oriented
        return geom

    reoriented_gdf['geometry'] = reoriented_gdf['geometry'].apply(_orient)

    report = {
        'polygons_reoriented': reoriented_count
    }

    return reoriented_gdf, report


def remove_duplicate_geometries(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Remove duplicate geometries from a GeoDataFrame.

    Geometries are keyed on their normalized WKB representation. Calling
    normalize() canonicalizes vertex order before comparison, so this catches
    geometrically-equal duplicates even when their vertices are stored in a
    different order. Rows whose key duplicates an earlier row (keep="first")
    are dropped.

    Args:
        gdf: GeoDataFrame to process

    Returns:
        Tuple of (deduplicated_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'geometries_removed': 0, 'remaining_count': 0}

    # Canonicalize vertex order, then key on WKB so geometrically-equal
    # geometries collapse to the same key regardless of vertex ordering.
    keys = gdf.geometry.normalize().to_wkb()
    duplicate_mask = keys.duplicated(keep='first')
    duplicate_count = int(duplicate_mask.sum())

    deduplicated_gdf = gdf[~duplicate_mask].copy()

    report = {
        'geometries_removed': duplicate_count,
        'remaining_count': len(deduplicated_gdf)
    }

    return deduplicated_gdf, report


def remove_duplicate_vertices(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    Remove duplicate and collinear vertices from geometries.

    For each non-Point geometry, geom.simplify(0) is applied. A zero tolerance
    removes consecutive duplicate vertices as well as vertices that are exactly
    collinear with their neighbours, without otherwise changing the geometry's
    shape. Point geometries are left untouched.

    Args:
        gdf: GeoDataFrame to process

    Returns:
        Tuple of (cleaned_geodataframe, report_dict)
    """
    if gdf.empty:
        return gdf, {'geometries_cleaned': 0}

    cleaned_gdf = gdf.copy()
    cleaned_count = 0

    def _clean(geom):
        nonlocal cleaned_count
        if geom is None or geom.is_empty:
            return geom
        if isinstance(geom, Point):
            return geom
        cleaned = geom.simplify(0)
        if cleaned.wkb != geom.wkb:
            cleaned_count += 1
        return cleaned

    cleaned_gdf['geometry'] = cleaned_gdf['geometry'].apply(_clean)

    report = {
        'geometries_cleaned': cleaned_count
    }

    return cleaned_gdf, report


def validate_geometry_types(gdf: gpd.GeoDataFrame) -> Dict[str, int]:
    """
    Get detailed geometry type statistics.
    
    Args:
        gdf: GeoDataFrame to analyze
        
    Returns:
        Dictionary with geometry type counts
    """
    if gdf.empty:
        return {'total_features': 0, 'unique_types': 0}

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
    remove_duplicates: bool = False,
    clean_vertices: bool = False,
    normalize_winding_order: bool = False,
    do_explode_multipart: bool = False,
    simplify: bool = False,
    simplify_tolerance: float = 0.001
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Comprehensive geometry processing pipeline.

    Args:
        gdf: GeoDataFrame to process
        fix_invalid: Whether to fix invalid geometries
        remove_empty: Whether to remove empty geometries
        remove_duplicates: Whether to remove duplicate geometries
        clean_vertices: Whether to remove duplicate/collinear vertices
        normalize_winding_order: Whether to normalize polygon winding order
        do_explode_multipart: Whether to explode multipart geometries
        simplify: Whether to simplify geometries
        simplify_tolerance: Simplification tolerance

    Returns:
        Tuple of (processed_geodataframe, comprehensive_report)
    """
    if gdf.empty:
        return gdf, {
            'operations': [],
            'original_count': 0,
            'final_count': 0,
            'total_removed': 0,
            'geometry_types': {},
            'bounds': get_geometry_bounds(gdf)
        }

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

    # Step 3: Remove duplicate geometries
    if remove_duplicates:
        processed_gdf, duplicates_report = remove_duplicate_geometries(processed_gdf)
        operations.append({
            'operation': 'remove_duplicates',
            'geometries_removed': duplicates_report['geometries_removed'],
            'remaining_count': duplicates_report['remaining_count']
        })
        total_removed += duplicates_report['geometries_removed']

    # Step 4: Clean duplicate/collinear vertices
    if clean_vertices:
        processed_gdf, clean_report = remove_duplicate_vertices(processed_gdf)
        operations.append({
            'operation': 'clean_vertices',
            'geometries_cleaned': clean_report['geometries_cleaned']
        })

    # Step 5: Normalize polygon winding order
    if normalize_winding_order:
        processed_gdf, winding_report = normalize_winding(processed_gdf)
        operations.append({
            'operation': 'normalize_winding_order',
            'polygons_reoriented': winding_report['polygons_reoriented']
        })

    # Step 6: Explode multipart geometries
    if do_explode_multipart:
        processed_gdf, explode_report = explode_multipart(processed_gdf)
        operations.append({
            'operation': 'explode_multipart',
            'multipart_count': explode_report['multipart_count'],
            'exploded_count': explode_report['exploded_count']
        })
    
    # Step 7: Simplify geometries
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
