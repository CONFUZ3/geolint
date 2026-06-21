"""
Quality checks for geospatial datasets.

Provides topology, attribute, and coordinate checks that operate on a
GeoDataFrame and return plain JSON-serializable dictionaries.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import STRtree

# Maximum number of entries kept in any sample list returned to callers.
_MAX_SAMPLE = 20

# Polygon feature count above which the overlap check is skipped unless forced.
_OVERLAP_FEATURE_CAP = 20000


def _valid_geom_mask(gdf: gpd.GeoDataFrame) -> pd.Series:
    """
    Build a boolean mask of geometries that are neither None nor empty.

    Args:
        gdf: GeoDataFrame (already positionally indexed)

    Returns:
        Boolean Series aligned with gdf marking usable geometries
    """
    return gdf.geometry.apply(lambda g: g is not None and not g.is_empty)


def check_duplicate_geometries(gdf: gpd.GeoDataFrame) -> dict:
    """
    Detect features whose geometry duplicates another feature's geometry.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with duplicate results:
        - duplicate_count: int (features that duplicate an EARLIER feature)
        - duplicate_groups: int (distinct geometries occurring more than once)
        - sample_indices: list of positional indices (0-based, capped)
    """
    if gdf.empty:
        return {'duplicate_count': 0, 'duplicate_groups': 0, 'sample_indices': []}

    gdf = gdf.reset_index(drop=True)
    valid_mask = _valid_geom_mask(gdf)
    positions = np.where(valid_mask.to_numpy())[0]
    if len(positions) == 0:
        return {'duplicate_count': 0, 'duplicate_groups': 0, 'sample_indices': []}

    geoms = gdf.geometry.to_numpy()[positions]
    tree = STRtree(geoms)
    pairs = tree.query(geoms, predicate='intersects')  # shape (2, N): [input, tree]

    # Map local (filtered) positions back to original positional indices.
    # group_of[p] = smallest position that p is equal to (its representative)
    group_of = {}
    duplicate_positions = set()
    for input_i, tree_j in zip(pairs[0], pairs[1]):
        if input_i <= tree_j:
            continue  # only consider j < i so the later feature is the duplicate
        i_pos = int(positions[input_i])
        j_pos = int(positions[tree_j])
        if geoms[input_i].equals(geoms[tree_j]):
            duplicate_positions.add(i_pos)
            # representative is the earliest equal geometry seen
            rep = group_of.get(j_pos, j_pos)
            group_of[i_pos] = rep

    duplicate_groups = len(set(group_of.values()))
    sample_indices = sorted(duplicate_positions)[:_MAX_SAMPLE]

    return {
        'duplicate_count': len(duplicate_positions),
        'duplicate_groups': duplicate_groups,
        'sample_indices': [int(p) for p in sample_indices],
    }


def check_overlapping_polygons(gdf: gpd.GeoDataFrame, force: bool = False) -> dict:
    """
    Detect pairs of polygons that share interior area (true overlap).

    Touching polygons that share only a boundary (zero area) are excluded.

    Args:
        gdf: GeoDataFrame to check
        force: If True, run even when polygon count exceeds the cap

    Returns:
        Dictionary with overlap results:
        - applicable: bool (False when there are no polygons)
        - skipped: bool (True when capped out and not forced)
        - overlap_pair_count: int
        - features_involved: int (distinct polygons in any overlapping pair)
        - sample_pairs: list of [i, j] positional index pairs (capped)
    """
    zero = {
        'applicable': False,
        'skipped': False,
        'overlap_pair_count': 0,
        'features_involved': 0,
        'sample_pairs': [],
    }
    if gdf.empty:
        return zero

    gdf = gdf.reset_index(drop=True)
    valid_mask = _valid_geom_mask(gdf)
    type_mask = gdf.geometry.apply(
        lambda g: g is not None and g.geom_type in ('Polygon', 'MultiPolygon')
    )
    keep = valid_mask & type_mask
    positions = np.where(keep.to_numpy())[0]
    if len(positions) == 0:
        return zero  # applicable False

    if len(positions) > _OVERLAP_FEATURE_CAP and not force:
        return {
            'applicable': True,
            'skipped': True,
            'overlap_pair_count': 0,
            'features_involved': 0,
            'sample_pairs': [],
        }

    geoms = gdf.geometry.to_numpy()[positions]
    tree = STRtree(geoms)
    pairs = tree.query(geoms, predicate='intersects')

    overlap_pairs = []
    involved = set()
    for input_i, tree_j in zip(pairs[0], pairs[1]):
        if input_i <= tree_j:
            continue
        a = geoms[tree_j]
        b = geoms[input_i]
        if a.intersection(b).area > 0:
            i_pos = int(positions[tree_j])
            j_pos = int(positions[input_i])
            lo, hi = (i_pos, j_pos) if i_pos < j_pos else (j_pos, i_pos)
            overlap_pairs.append([lo, hi])
            involved.add(lo)
            involved.add(hi)

    overlap_pairs.sort()
    sample_pairs = [[int(a), int(b)] for a, b in overlap_pairs[:_MAX_SAMPLE]]

    return {
        'applicable': True,
        'skipped': False,
        'overlap_pair_count': len(overlap_pairs),
        'features_involved': len(involved),
        'sample_pairs': sample_pairs,
    }


def check_sliver_and_zero_geometries(
    gdf: gpd.GeoDataFrame, area_tol: float = 1e-12, length_tol: float = 1e-12
) -> dict:
    """
    Detect zero-area polygons and zero-length lines.

    Points are never counted. Multipart geometries are evaluated by their
    total area/length via the vectorized GeoPandas accessors.

    Args:
        gdf: GeoDataFrame to check
        area_tol: Polygons with area <= this are flagged
        length_tol: Lines with length <= this are flagged

    Returns:
        Dictionary with results:
        - zero_area_polygons: int
        - zero_length_lines: int
        - sample_indices: list of positional indices (0-based, capped)
    """
    if gdf.empty:
        return {'zero_area_polygons': 0, 'zero_length_lines': 0, 'sample_indices': []}

    gdf = gdf.reset_index(drop=True)
    valid_mask = _valid_geom_mask(gdf)
    geom_types = gdf.geometry.apply(
        lambda g: g.geom_type if g is not None else None
    )

    poly_mask = valid_mask & geom_types.isin(['Polygon', 'MultiPolygon'])
    line_mask = valid_mask & geom_types.isin(['LineString', 'MultiLineString'])

    areas = gdf.geometry.area
    lengths = gdf.geometry.length

    zero_area_mask = poly_mask & (areas <= area_tol)
    zero_length_mask = line_mask & (lengths <= length_tol)

    zero_area_polygons = int(zero_area_mask.sum())
    zero_length_lines = int(zero_length_mask.sum())

    flagged = np.where((zero_area_mask | zero_length_mask).to_numpy())[0]
    sample_indices = [int(p) for p in flagged[:_MAX_SAMPLE]]

    return {
        'zero_area_polygons': zero_area_polygons,
        'zero_length_lines': zero_length_lines,
        'sample_indices': sample_indices,
    }


def _ring_has_consecutive_duplicates(coords) -> bool:
    """
    Return True if a coordinate sequence has consecutive duplicate vertices.

    A closed ring's last coordinate equals its first by definition; np.diff
    only compares adjacent array elements, so closed rings are not flagged.
    """
    arr = np.asarray(coords)
    if arr.shape[0] < 2:
        return False
    return bool(np.any(np.all(np.diff(arr, axis=0) == 0, axis=1)))


def _geom_has_duplicate_vertices(geom) -> bool:
    """Check a single line/polygon geometry for consecutive duplicate vertices."""
    geom_type = geom.geom_type
    if geom_type == 'LineString':
        return _ring_has_consecutive_duplicates(geom.coords)
    if geom_type == 'MultiLineString':
        return any(_ring_has_consecutive_duplicates(part.coords) for part in geom.geoms)
    if geom_type == 'Polygon':
        if _ring_has_consecutive_duplicates(geom.exterior.coords):
            return True
        return any(_ring_has_consecutive_duplicates(r.coords) for r in geom.interiors)
    if geom_type == 'MultiPolygon':
        return any(_geom_has_duplicate_vertices(part) for part in geom.geoms)
    return False


def check_duplicate_vertices(gdf: gpd.GeoDataFrame) -> dict:
    """
    Detect line/polygon features that contain consecutive duplicate vertices.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with results:
        - features_with_duplicate_vertices: int
        - sample_indices: list of positional indices (0-based, capped)
    """
    if gdf.empty:
        return {'features_with_duplicate_vertices': 0, 'sample_indices': []}

    gdf = gdf.reset_index(drop=True)
    flagged = []
    for pos, geom in enumerate(gdf.geometry):
        if geom is None or geom.is_empty:
            continue
        if _geom_has_duplicate_vertices(geom):
            flagged.append(pos)

    return {
        'features_with_duplicate_vertices': len(flagged),
        'sample_indices': [int(p) for p in flagged[:_MAX_SAMPLE]],
    }


def check_id_uniqueness(gdf: gpd.GeoDataFrame, id_column: str = None) -> dict:
    """
    Check uniqueness of an identifier column.

    When id_column is not given, the first present (case-insensitive) of
    ('id', 'fid', 'gid', 'objectid', 'uid') among non-geometry columns is used.

    Args:
        gdf: GeoDataFrame to check
        id_column: Explicit identifier column name, or None to auto-detect

    Returns:
        Dictionary with results:
        - id_column: str or None (the column actually used)
        - duplicate_count: int
        - sample_values: list of duplicated id values (capped)
        - sample_indices: list of positional indices (0-based, capped)
    """
    if gdf.empty:
        return {
            'id_column': id_column,
            'duplicate_count': 0,
            'sample_values': [],
            'sample_indices': [],
        }

    gdf = gdf.reset_index(drop=True)
    geom_col = gdf.geometry.name
    attr_cols = [c for c in gdf.columns if c != geom_col]

    chosen = None
    if id_column is not None:
        if id_column in attr_cols:
            chosen = id_column
    else:
        lower_map = {str(c).lower(): c for c in attr_cols}
        for candidate in ('id', 'fid', 'gid', 'objectid', 'uid'):
            if candidate in lower_map:
                chosen = lower_map[candidate]
                break

    if chosen is None:
        return {
            'id_column': None,
            'duplicate_count': 0,
            'sample_values': [],
            'sample_indices': [],
        }

    series = gdf[chosen]
    dup_mask = series.duplicated(keep=False)
    positions = np.where(dup_mask.to_numpy())[0]

    sample_values = []
    for v in series[dup_mask].drop_duplicates().tolist()[:_MAX_SAMPLE]:
        sample_values.append(v.item() if hasattr(v, 'item') else v)

    return {
        'id_column': chosen,
        'duplicate_count': int(dup_mask.sum()),
        'sample_values': sample_values,
        'sample_indices': [int(p) for p in positions[:_MAX_SAMPLE]],
    }


def check_null_attributes(gdf: gpd.GeoDataFrame) -> dict:
    """
    Count null values per non-geometry attribute column.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with results:
        - null_counts: dict of column -> null count (only columns with >0 nulls)
        - fully_null_columns: list of columns that are entirely null
        - total_columns: int (number of non-geometry columns)
    """
    if gdf.empty:
        return {'null_counts': {}, 'fully_null_columns': [], 'total_columns': 0}

    geom_col = gdf.geometry.name
    attr_cols = [c for c in gdf.columns if c != geom_col]
    total = len(gdf)

    null_counts = {}
    fully_null_columns = []
    for col in attr_cols:
        n = int(gdf[col].isna().sum())
        if n > 0:
            null_counts[str(col)] = n
        if n == total:
            fully_null_columns.append(str(col))

    return {
        'null_counts': null_counts,
        'fully_null_columns': fully_null_columns,
        'total_columns': len(attr_cols),
    }


def check_shapefile_field_names(gdf: gpd.GeoDataFrame) -> dict:
    """
    Check non-geometry column names against shapefile DBF field constraints.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with results:
        - long_names: list of names longer than 10 characters
        - truncation_collisions: list of groups (lists) of 2+ names that collide
          when truncated to 10 characters (case-insensitive)
        - non_ascii_names: list of names containing non-ASCII characters
    """
    if gdf.empty:
        return {'long_names': [], 'truncation_collisions': [], 'non_ascii_names': []}

    geom_col = gdf.geometry.name
    attr_cols = [str(c) for c in gdf.columns if c != geom_col]

    long_names = [c for c in attr_cols if len(c) > 10]

    non_ascii_names = [c for c in attr_cols if not c.isascii()]

    # Group names by their 10-char, lowercased truncation (DBF is case-insensitive).
    groups = {}
    for c in attr_cols:
        key = c[:10].lower()
        groups.setdefault(key, []).append(c)
    truncation_collisions = [names for names in groups.values() if len(names) >= 2]

    return {
        'long_names': long_names,
        'truncation_collisions': truncation_collisions,
        'non_ascii_names': non_ascii_names,
    }


def _polygon_winding_violation(geom) -> bool:
    """Return True if a Polygon/MultiPolygon violates RFC 7946 winding order."""
    if geom.geom_type == 'MultiPolygon':
        return any(_polygon_winding_violation(part) for part in geom.geoms)
    if geom.geom_type != 'Polygon':
        return False
    if geom.exterior.is_ccw is not True:
        return True
    for ring in geom.interiors:
        if ring.is_ccw is not False:
            return True
    return False


def check_winding_order(gdf: gpd.GeoDataFrame) -> dict:
    """
    Check polygon ring winding order against RFC 7946.

    Exterior rings must be counter-clockwise and interior rings clockwise.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with results:
        - applicable: bool (False when there are no polygons)
        - non_compliant_count: int
        - sample_indices: list of positional indices (0-based, capped)
    """
    if gdf.empty:
        return {'applicable': False, 'non_compliant_count': 0, 'sample_indices': []}

    gdf = gdf.reset_index(drop=True)
    valid_mask = _valid_geom_mask(gdf)
    type_mask = gdf.geometry.apply(
        lambda g: g is not None and g.geom_type in ('Polygon', 'MultiPolygon')
    )
    keep = valid_mask & type_mask
    if not bool(keep.any()):
        return {'applicable': False, 'non_compliant_count': 0, 'sample_indices': []}

    flagged = []
    for pos in np.where(keep.to_numpy())[0]:
        geom = gdf.geometry.iloc[pos]
        if _polygon_winding_violation(geom):
            flagged.append(int(pos))

    return {
        'applicable': True,
        'non_compliant_count': len(flagged),
        'sample_indices': [int(p) for p in flagged[:_MAX_SAMPLE]],
    }


def check_coordinate_range(gdf: gpd.GeoDataFrame) -> dict:
    """
    Check that coordinates fall within geographic lon/lat bounds.

    Only applicable to geographic CRS. Flags rows whose bounding box exceeds
    [-180, 180] longitude or [-90, 90] latitude.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with results:
        - applicable: bool (False when CRS is missing or not geographic)
        - out_of_range_count: int
        - sample_indices: list of positional indices (0-based, capped)
    """
    if gdf.empty:
        return {'applicable': False, 'out_of_range_count': 0, 'sample_indices': []}

    if gdf.crs is None or not gdf.crs.is_geographic:
        return {'applicable': False, 'out_of_range_count': 0, 'sample_indices': []}

    gdf = gdf.reset_index(drop=True)
    bounds = gdf.bounds  # columns: minx, miny, maxx, maxy
    out_mask = (
        (bounds['maxx'] > 180)
        | (bounds['minx'] < -180)
        | (bounds['maxy'] > 90)
        | (bounds['miny'] < -90)
    )
    # NaN bounds (None/empty geometries) compare False, so they are not flagged.
    positions = np.where(out_mask.to_numpy())[0]

    return {
        'applicable': True,
        'out_of_range_count': int(out_mask.sum()),
        'sample_indices': [int(p) for p in positions[:_MAX_SAMPLE]],
    }


def run_checks(gdf: gpd.GeoDataFrame, *, id_column: str = None,
               force_overlap: bool = False) -> dict:
    """
    Run all quality checks and group results by category.

    Each individual check is wrapped so a failure in one does not abort the
    others; a failing check stores {"error": str} under its key.

    Args:
        gdf: GeoDataFrame to check
        id_column: Explicit identifier column for the id uniqueness check
        force_overlap: Force the overlap check past the feature cap

    Returns:
        Dictionary grouped into 'topology', 'attributes', and 'coordinates'.
    """
    def _safe(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - report per-check, do not abort
            return {'error': str(e)}

    return {
        'topology': {
            'duplicate_geometries': _safe(check_duplicate_geometries, gdf),
            'overlapping_polygons': _safe(
                check_overlapping_polygons, gdf, force=force_overlap
            ),
            'slivers': _safe(check_sliver_and_zero_geometries, gdf),
            'duplicate_vertices': _safe(check_duplicate_vertices, gdf),
        },
        'attributes': {
            'id_uniqueness': _safe(check_id_uniqueness, gdf, id_column=id_column),
            'null_attributes': _safe(check_null_attributes, gdf),
            'shapefile_field_names': _safe(check_shapefile_field_names, gdf),
        },
        'coordinates': {
            'winding_order': _safe(check_winding_order, gdf),
            'coordinate_range': _safe(check_coordinate_range, gdf),
        },
    }
