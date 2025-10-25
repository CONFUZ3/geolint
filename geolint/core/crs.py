"""
CRS (Coordinate Reference System) detection and inference.

Handles CRS reading, inference, and popular CRS selection.
"""

import math
from typing import Dict, List, Optional, Tuple, Union

import geopandas as gpd
import pyproj
from pyproj import CRS


def get_crs_info(gdf: gpd.GeoDataFrame) -> Dict[str, Union[str, int, bool, None]]:
    """
    Extract CRS information from a GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame to analyze
        
    Returns:
        Dictionary with CRS information:
        - crs: CRS string representation
        - epsg: EPSG code (if available)
        - is_geographic: Whether CRS is geographic
        - is_projected: Whether CRS is projected
        - units: CRS units
        - name: CRS name
    """
    if gdf.crs is None:
        return {
            'crs': None,
            'epsg': None,
            'is_geographic': None,
            'is_projected': None,
            'units': None,
            'name': None
        }
    
    crs = gdf.crs
    epsg = crs.to_epsg()
    
    return {
        'crs': crs.to_string(),
        'epsg': epsg,
        'is_geographic': crs.is_geographic,
        'is_projected': crs.is_projected,
        'units': crs.axis_info[0].unit_name if crs.axis_info else None,
        'name': crs.name
    }


def infer_crs(gdf: gpd.GeoDataFrame, region_hint: Optional[str] = None) -> List[Dict[str, Union[str, int, float]]]:
    """
    Infer the most likely CRS for a dataset based on its bounds.
    
    Uses advanced heuristics including:
    - Bounds analysis
    - Area of use overlap
    - Common CRS likelihood
    - Geographic vs projected appropriateness
    
    Args:
        gdf: GeoDataFrame to analyze
        region_hint: Optional region hint (e.g., "New York", "Europe")
        
    Returns:
        List of CRS suggestions sorted by confidence (highest first)
    """
    if gdf.empty:
        return []
    
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    suggestions = []
    
    # Get all available CRS from pyproj database
    try:
        crs_info_list = pyproj.database.query_crs_info()
        
        for crs_info in crs_info_list:
            try:
                crs = CRS.from_authority(crs_info.auth_name, crs_info.code)
                confidence = _calculate_crs_confidence(
                    crs, bounds, center_lon, center_lat, region_hint
                )
                
                if confidence > 0.1:  # Only include suggestions with >10% confidence
                    suggestions.append({
                        'epsg': crs_info.code,
                        'name': crs_info.name,
                        'confidence': round(confidence, 3),
                        'type': 'geographic' if crs.is_geographic else 'projected',
                        'area_of_use': crs_info.area_name or 'Unknown'
                    })
                    
            except Exception:
                # Skip CRS that can't be created
                continue
                
    except Exception:
        # Fallback to common CRS if database query fails
        suggestions = _get_fallback_crs_suggestions(bounds, center_lon, center_lat)
    
    # Sort by confidence (highest first) and return top 10
    suggestions.sort(key=lambda x: x['confidence'], reverse=True)
    return suggestions[:10]


def _calculate_crs_confidence(
    crs: CRS, 
    bounds: Tuple[float, float, float, float], 
    center_lon: float, 
    center_lat: float,
    region_hint: Optional[str] = None
) -> float:
    """
    Calculate confidence score for a CRS based on various factors.
    """
    confidence = 0.0
    
    # Factor 1: Area of use overlap (40% weight)
    try:
        if hasattr(crs, 'area_of_use') and crs.area_of_use:
            aou = crs.area_of_use
            if (aou.west <= center_lon <= aou.east and 
                aou.south <= center_lat <= aou.north):
                # Calculate overlap percentage
                overlap = _calculate_bounds_overlap(
                    bounds, (aou.west, aou.south, aou.east, aou.north)
                )
                confidence += 0.4 * overlap
    except Exception:
        pass
    
    # Factor 2: Common CRS likelihood (30% weight)
    epsg = crs.to_epsg()
    if epsg:
        common_crs_scores = {
            3857: 0.95,  # Web Mercator (prioritized for web mapping)
            4326: 0.9,   # WGS84
            3395: 0.8,   # World Mercator
            2154: 0.7,   # RGF93 / Lambert-93
            2157: 0.7,   # IRENET95
            2158: 0.7,   # ETRS89 / UTM zone 32N
        }
        
        # UTM zones (32601-32660, 32701-32760)
        if 32601 <= epsg <= 32660 or 32701 <= epsg <= 32760:
            utm_confidence = _calculate_utm_confidence(epsg, center_lon, center_lat)
            confidence += 0.3 * utm_confidence
        elif epsg in common_crs_scores:
            confidence += 0.3 * common_crs_scores[epsg]
    
    # Factor 3: Geographic vs Projected appropriateness (20% weight)
    if crs.is_geographic:
        # Geographic CRS good for global data or small areas
        data_extent = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        if data_extent < 1.0:  # Less than 1 degree
            confidence += 0.2
    else:
        # Projected CRS good for regional data
        data_extent = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        if data_extent > 0.1:  # More than 0.1 degrees
            confidence += 0.2
    
    # Factor 4: Region hint match (10% weight)
    if region_hint and hasattr(crs, 'area_of_use'):
        try:
            aou_name = crs.area_of_use.name.lower()
            if region_hint.lower() in aou_name:
                confidence += 0.1
        except Exception:
            pass
    
    return min(confidence, 1.0)  # Cap at 1.0


def _calculate_bounds_overlap(bounds1: Tuple[float, float, float, float], 
                            bounds2: Tuple[float, float, float, float]) -> float:
    """Calculate overlap percentage between two bounding boxes."""
    # Calculate intersection
    x1 = max(bounds1[0], bounds2[0])
    y1 = max(bounds1[1], bounds2[1])
    x2 = min(bounds1[2], bounds2[2])
    y2 = min(bounds1[3], bounds2[3])
    
    if x1 >= x2 or y1 >= y2:
        return 0.0  # No overlap
    
    intersection_area = (x2 - x1) * (y2 - y1)
    bounds1_area = (bounds1[2] - bounds1[0]) * (bounds1[3] - bounds1[1])
    
    return intersection_area / bounds1_area if bounds1_area > 0 else 0.0


def _calculate_utm_confidence(epsg: int, center_lon: float, center_lat: float) -> float:
    """Calculate confidence for UTM zones based on location."""
    # UTM zone calculation
    utm_zone = ((center_lon + 180) / 6) + 1
    hemisphere = 1 if center_lat >= 0 else 0
    
    # Expected EPSG for this location
    expected_epsg = 32600 + int(utm_zone) if hemisphere == 1 else 32700 + int(utm_zone)
    
    if epsg == expected_epsg:
        return 0.9
    elif abs(epsg - expected_epsg) <= 1:  # Adjacent zones
        return 0.6
    else:
        return 0.3


def _get_fallback_crs_suggestions(bounds: Tuple[float, float, float, float], 
                                center_lon: float, center_lat: float) -> List[Dict]:
    """Fallback CRS suggestions when database query fails."""
    suggestions = []
    
    # Web Mercator (prioritized for web mapping)
    suggestions.append({
        'epsg': 3857,
        'name': 'WGS 84 / Pseudo-Mercator',
        'confidence': 0.8,
        'type': 'projected',
        'area_of_use': 'World'
    })
    
    # WGS84 (good fallback)
    suggestions.append({
        'epsg': 4326,
        'name': 'WGS 84',
        'confidence': 0.7,
        'type': 'geographic',
        'area_of_use': 'World'
    })
    
    # UTM zones
    utm_zone = int((center_lon + 180) / 6) + 1
    hemisphere = 'N' if center_lat >= 0 else 'S'
    utm_epsg = 32600 + utm_zone if hemisphere == 'N' else 32700 + utm_zone
    
    suggestions.append({
        'epsg': utm_epsg,
        'name': f'WGS 84 / UTM zone {utm_zone}{hemisphere}',
        'confidence': 0.8,
        'type': 'projected',
        'area_of_use': f'UTM Zone {utm_zone}{hemisphere}'
    })
    
    return suggestions


def get_popular_crs() -> Dict[str, List[Dict[str, Union[str, int]]]]:
    """
    Get curated list of popular CRS by category.
    
    Returns:
        Dictionary with CRS categories and their CRS lists
    """
    return {
        'global': [
            {'epsg': 3857, 'name': 'Web Mercator', 'description': 'Web mapping standard'},
            {'epsg': 4326, 'name': 'WGS 84', 'description': 'World Geographic'},
            {'epsg': 3395, 'name': 'World Mercator', 'description': 'Traditional world projection'},
        ],
        'europe': [
            {'epsg': 2154, 'name': 'RGF93 / Lambert-93', 'description': 'France'},
            {'epsg': 2157, 'name': 'IRENET95', 'description': 'Ireland'},
            {'epsg': 2158, 'name': 'ETRS89 / UTM zone 32N', 'description': 'Northern Europe'},
            {'epsg': 25832, 'name': 'ETRS89 / UTM zone 32N', 'description': 'Germany'},
        ],
        'north_america': [
            {'epsg': 4269, 'name': 'NAD83', 'description': 'North American Datum 1983'},
            {'epsg': 26910, 'name': 'NAD83 / UTM zone 10N', 'description': 'US West Coast'},
            {'epsg': 26911, 'name': 'NAD83 / UTM zone 11N', 'description': 'US West Coast'},
            {'epsg': 26912, 'name': 'NAD83 / UTM zone 12N', 'description': 'US West Coast'},
        ],
        'utm_zones': [
            {'epsg': 32601, 'name': 'WGS 84 / UTM zone 1N', 'description': 'UTM Zone 1N'},
            {'epsg': 32615, 'name': 'WGS 84 / UTM zone 15N', 'description': 'UTM Zone 15N'},
            {'epsg': 32630, 'name': 'WGS 84 / UTM zone 30N', 'description': 'UTM Zone 30N'},
            {'epsg': 32645, 'name': 'WGS 84 / UTM zone 45N', 'description': 'UTM Zone 45N'},
        ]
    }


def auto_detect_utm_zone(bounds: Tuple[float, float, float, float]) -> Dict[str, Union[int, str]]:
    """
    Auto-detect the most appropriate UTM zone for given bounds.
    
    Args:
        bounds: Bounding box (minx, miny, maxx, maxy)
        
    Returns:
        Dictionary with UTM zone information
    """
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    # Calculate UTM zone
    utm_zone = int((center_lon + 180) / 6) + 1
    hemisphere = 'N' if center_lat >= 0 else 'S'
    
    # Calculate EPSG code
    epsg = 32600 + utm_zone if hemisphere == 'N' else 32700 + utm_zone
    
    return {
        'zone': utm_zone,
        'hemisphere': hemisphere,
        'epsg': epsg,
        'name': f'WGS 84 / UTM zone {utm_zone}{hemisphere}'
    }
