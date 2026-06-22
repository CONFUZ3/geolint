"""
Export flagged features as a GeoJSON "error layer".

Analysts can open the resulting GeoJSON directly in QGIS to visually triage the
exact features that tripped each check. Feature positions are taken from the
checks' positional ``sample_indices`` (capped samples), so the error layer shows
representative offenders rather than necessarily every one.
"""

import json
from pathlib import Path
from typing import Dict

import geopandas as gpd


def flagged_index_map(gdf: gpd.GeoDataFrame, report: Dict) -> Dict[int, list]:
    """
    Build a mapping of positional feature index -> list of check ids that flagged it.

    The GeoDataFrame is assumed to be in its natural (0..n-1) order; callers
    should pass the same gdf that produced ``report``.
    """
    flagged: Dict[int, set] = {}

    def mark(indices, label):
        for i in indices or []:
            if isinstance(i, int) and 0 <= i < len(gdf):
                flagged.setdefault(i, set()).add(label)

    # Invalid geometries (recomputed positionally to avoid label/position mismatch).
    invalid_positions = [
        pos for pos, geom in enumerate(gdf.geometry)
        if geom is None or not geom.is_valid
    ]
    mark(invalid_positions, 'invalid_geometries')

    checks = report.get('checks', {}) or {}
    topo = checks.get('topology', {}) or {}
    mark((topo.get('duplicate_geometries') or {}).get('sample_indices'), 'duplicate_geometries')
    mark((topo.get('slivers') or {}).get('sample_indices'), 'slivers')
    mark((topo.get('duplicate_vertices') or {}).get('sample_indices'), 'duplicate_vertices')

    for pair in (topo.get('overlapping_polygons') or {}).get('sample_pairs', []) or []:
        mark(list(pair), 'overlapping_polygons')

    lines = topo.get('lines', {}) or {}
    mark((lines.get('self_intersections') or {}).get('sample_indices'), 'self_intersections')
    for ep in (lines.get('dangles') or {}).get('sample_endpoints', []) or []:
        mark([ep.get('feature_index')], 'line_dangles')

    attr = checks.get('attributes', {}) or {}
    mark((attr.get('id_uniqueness') or {}).get('sample_indices'), 'id_uniqueness')

    coord = checks.get('coordinates', {}) or {}
    mark((coord.get('winding_order') or {}).get('sample_indices'), 'winding_order')
    mark((coord.get('coordinate_range') or {}).get('sample_indices'), 'coordinate_range')

    return {i: sorted(labels) for i, labels in flagged.items()}


def write_error_layer(gdf: gpd.GeoDataFrame, report: Dict, output_path) -> Path:
    """
    Write flagged features to a GeoJSON file for visual triage.

    Returns the output Path. When nothing is flagged, an empty FeatureCollection
    is written so downstream tooling always has a valid file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gdf = gdf.reset_index(drop=True)
    index_map = flagged_index_map(gdf, report)

    if not index_map:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({'type': 'FeatureCollection', 'features': []}, f)
        return output_path

    positions = sorted(index_map)
    subset = gdf.iloc[positions].copy()
    subset['geolint_index'] = positions
    subset['geolint_checks'] = [', '.join(index_map[p]) for p in positions]

    # GeoJSON is always WGS84-friendly; keep whatever CRS the data has.
    subset.to_file(output_path, driver='GeoJSON')
    return output_path
