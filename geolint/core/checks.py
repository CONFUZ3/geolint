"""
Quality checks for geospatial datasets.

Provides topology, attribute, and coordinate checks that operate on a
GeoDataFrame and return plain JSON-serializable dictionaries.
"""

from collections import Counter

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import STRtree
from shapely.geometry import Point, Polygon

# Maximum number of entries kept in any sample list returned to callers.
_MAX_SAMPLE = 20

# Polygon feature count above which the overlap check is skipped unless forced.
_OVERLAP_FEATURE_CAP = 20000

# Polygon feature count above which the coverage-gap check is skipped unless forced.
_COVERAGE_FEATURE_CAP = 20000

# Line feature count above which network checks are skipped unless forced.
_LINE_FEATURE_CAP = 50000


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


def _iter_polygon_parts(geom):
    """Yield each Polygon contained in a Polygon/MultiPolygon/GeometryCollection."""
    if geom is None or geom.is_empty:
        return
    gt = geom.geom_type
    if gt == 'Polygon':
        yield geom
    elif gt in ('MultiPolygon', 'GeometryCollection'):
        for part in geom.geoms:
            yield from _iter_polygon_parts(part)


def _iter_line_parts(geom):
    """Yield each LineString in a LineString/MultiLineString; ignore other types."""
    if geom is None or geom.is_empty:
        return
    gt = geom.geom_type
    if gt == 'LineString':
        yield geom
    elif gt == 'MultiLineString':
        for part in geom.geoms:
            if part is not None and not part.is_empty:
                yield part


def _part_endpoints(part):
    """
    Return the open endpoints of a single LineString part.

    Yields [('start', (x, y)), ('end', (x, y))] for an open line; returns []
    for closed rings (start == end) and degenerate parts, since those have no
    dangling endpoint.
    """
    coords = list(part.coords)
    if len(coords) < 2:
        return []
    start = (coords[0][0], coords[0][1])
    end = (coords[-1][0], coords[-1][1])
    if start == end:
        return []
    return [('start', start), ('end', end)]


def _line_positions(gdf: gpd.GeoDataFrame):
    """Positional indices of valid LineString/MultiLineString features."""
    valid_mask = _valid_geom_mask(gdf)
    type_mask = gdf.geometry.apply(
        lambda g: g is not None and g.geom_type in ('LineString', 'MultiLineString')
    )
    return np.where((valid_mask & type_mask).to_numpy())[0]


def _polygon_positions(gdf: gpd.GeoDataFrame):
    """Positional indices of valid Polygon/MultiPolygon features."""
    valid_mask = _valid_geom_mask(gdf)
    type_mask = gdf.geometry.apply(
        lambda g: g is not None and g.geom_type in ('Polygon', 'MultiPolygon')
    )
    return np.where((valid_mask & type_mask).to_numpy())[0]


def check_coverage_gaps(
    gdf: gpd.GeoDataFrame, *, area_tol: float = 0.0, force: bool = False
) -> dict:
    """
    Detect enclosed gaps (slivers/holes) between adjacent polygons in a coverage.

    The gaps are the interior rings of the unioned coverage. This deliberately
    avoids the envelope-difference approach, which would report the frame between
    the bounding box and a non-rectangular coverage as one giant false gap.

    Args:
        gdf: GeoDataFrame to check (treated as a single coverage layer)
        area_tol: Gaps with area <= this are ignored
        force: If True, run even when polygon count exceeds the cap

    Returns:
        Dictionary with results:
        - applicable: bool (False when there are no polygons)
        - skipped: bool (True when capped out and not forced)
        - gap_count: int
        - gap_area_total: float (source CRS units)
        - largest_gap_area: float
        - crs_is_geographic: bool (areas are degrees, not meaningful, when True)
        - sample_gaps: list of {area, centroid:[x,y], bbox:[minx,miny,maxx,maxy]}
    """
    zero = {
        'applicable': False,
        'skipped': False,
        'gap_count': 0,
        'gap_area_total': 0.0,
        'largest_gap_area': 0.0,
        'crs_is_geographic': False,
        'sample_gaps': [],
    }
    if gdf.empty:
        return zero

    gdf = gdf.reset_index(drop=True)
    positions = _polygon_positions(gdf)
    if len(positions) == 0:
        return zero

    crs_is_geographic = bool(gdf.crs is not None and gdf.crs.is_geographic)

    if len(positions) > _COVERAGE_FEATURE_CAP and not force:
        return {
            'applicable': True,
            'skipped': True,
            'gap_count': 0,
            'gap_area_total': 0.0,
            'largest_gap_area': 0.0,
            'crs_is_geographic': crs_is_geographic,
            'sample_gaps': [],
        }

    geoms = gdf.geometry.to_numpy()[positions]
    coverage = shapely.union_all(geoms)

    gaps = []
    for poly in _iter_polygon_parts(coverage):
        for ring in poly.interiors:
            gap = Polygon(ring)
            area = gap.area
            if area > area_tol:
                gaps.append((area, gap))

    gaps.sort(key=lambda t: t[0], reverse=True)
    gap_area_total = float(sum(area for area, _ in gaps))
    largest = float(gaps[0][0]) if gaps else 0.0

    sample_gaps = []
    for area, gap in gaps[:_MAX_SAMPLE]:
        c = gap.centroid
        minx, miny, maxx, maxy = gap.bounds
        sample_gaps.append({
            'area': float(area),
            'centroid': [float(c.x), float(c.y)],
            'bbox': [float(minx), float(miny), float(maxx), float(maxy)],
        })

    return {
        'applicable': True,
        'skipped': False,
        'gap_count': len(gaps),
        'gap_area_total': gap_area_total,
        'largest_gap_area': largest,
        'crs_is_geographic': crs_is_geographic,
        'sample_gaps': sample_gaps,
    }


def _endpoint_connected_mask(records, tolerance):
    """
    Given endpoint records [(feature_pos, end_label, (x, y)), ...], return a list
    of bools marking endpoints that coincide with at least one OTHER endpoint.

    tolerance == 0: exact coincidence via rounded-coordinate degree counting.
    tolerance > 0: STRtree proximity query within the tolerance distance.
    """
    n = len(records)
    if tolerance and tolerance > 0:
        pts = [Point(c) for (_, _, c) in records]
        tree = STRtree(pts)
        connected = [False] * n
        for i, pt in enumerate(pts):
            for j in tree.query(pt.buffer(tolerance), predicate='intersects'):
                if int(j) != i:
                    connected[i] = True
                    break
        return connected

    ndig = 10
    keys = [(round(c[0], ndig), round(c[1], ndig)) for (_, _, c) in records]
    counts = Counter(keys)
    return [counts[k] > 1 for k in keys]


def check_line_dangles(
    gdf: gpd.GeoDataFrame, *, tolerance: float = 0.0, force: bool = False
) -> dict:
    """
    Detect dangling line endpoints (endpoints that connect to no other line).

    Closed rings contribute no endpoints. With tolerance 0 (default) connection
    means exact coincidence; with tolerance > 0 it means within that distance.

    Args:
        gdf: GeoDataFrame to check
        tolerance: Snap distance for considering two endpoints connected
        force: If True, run even when line count exceeds the cap

    Returns:
        Dictionary with results:
        - applicable: bool (False when there are no lines)
        - skipped: bool (True when capped out and not forced)
        - tolerance: float
        - dangle_count: int
        - sample_endpoints: list of {feature_index, end, coord:[x,y]}
    """
    zero = {
        'applicable': False,
        'skipped': False,
        'tolerance': float(tolerance),
        'dangle_count': 0,
        'sample_endpoints': [],
    }
    if gdf.empty:
        return zero

    gdf = gdf.reset_index(drop=True)
    positions = _line_positions(gdf)
    if len(positions) == 0:
        return zero

    if len(positions) > _LINE_FEATURE_CAP and not force:
        return {
            'applicable': True,
            'skipped': True,
            'tolerance': float(tolerance),
            'dangle_count': 0,
            'sample_endpoints': [],
        }

    geoms = gdf.geometry.to_numpy()
    records = []
    for pos in positions:
        for part in _iter_line_parts(geoms[pos]):
            for end_label, coord in _part_endpoints(part):
                records.append((int(pos), end_label, coord))

    if not records:
        return {
            'applicable': True,
            'skipped': False,
            'tolerance': float(tolerance),
            'dangle_count': 0,
            'sample_endpoints': [],
        }

    connected = _endpoint_connected_mask(records, tolerance)
    dangles = [rec for rec, conn in zip(records, connected) if not conn]
    sample = [
        {'feature_index': fpos, 'end': end_label, 'coord': [float(c[0]), float(c[1])]}
        for (fpos, end_label, c) in dangles[:_MAX_SAMPLE]
    ]

    return {
        'applicable': True,
        'skipped': False,
        'tolerance': float(tolerance),
        'dangle_count': len(dangles),
        'sample_endpoints': sample,
    }


def check_line_self_intersections(gdf: gpd.GeoDataFrame) -> dict:
    """
    Detect lines that cross or overlap themselves.

    A self-crossing LineString is still OGC-"valid", so this fills the gap left
    by is_valid: ``is_simple`` is False for self-crossing lines, and a doubled-
    back segment is detected by comparing the line length to its dissolved length.

    Args:
        gdf: GeoDataFrame to check

    Returns:
        Dictionary with results:
        - applicable: bool (False when there are no lines)
        - self_intersecting_count: int (lines that cross/touch themselves)
        - self_overlapping_count: int (lines with a segment doubling back)
        - sample_indices: list of positional indices (0-based, capped)
    """
    zero = {
        'applicable': False,
        'self_intersecting_count': 0,
        'self_overlapping_count': 0,
        'sample_indices': [],
    }
    if gdf.empty:
        return zero

    gdf = gdf.reset_index(drop=True)
    positions = _line_positions(gdf)
    if len(positions) == 0:
        return zero

    geoms = gdf.geometry.to_numpy()
    self_intersecting = 0
    self_overlapping = 0
    flagged = []
    for pos in positions:
        geom = geoms[pos]
        is_si = not geom.is_simple
        is_so = False
        try:
            if geom.length - shapely.unary_union(geom).length > 1e-9:
                is_so = True
        except Exception:  # noqa: BLE001 - dissolve failure is not fatal
            is_so = False
        if is_si:
            self_intersecting += 1
        if is_so:
            self_overlapping += 1
        if is_si or is_so:
            flagged.append(int(pos))

    return {
        'applicable': True,
        'self_intersecting_count': self_intersecting,
        'self_overlapping_count': self_overlapping,
        'sample_indices': [int(p) for p in flagged[:_MAX_SAMPLE]],
    }


def check_pseudo_nodes(gdf: gpd.GeoDataFrame, *, force: bool = False) -> dict:
    """
    Detect pseudo-nodes: nodes where exactly two line parts meet end-to-end.

    Advisory only - a legitimately attributed network may want these preserved.

    Args:
        gdf: GeoDataFrame to check
        force: If True, run even when line count exceeds the cap

    Returns:
        Dictionary with results:
        - applicable: bool (False when there are no lines)
        - skipped: bool (True when capped out and not forced)
        - pseudo_node_count: int
        - sample_nodes: list of {coord:[x,y], feature_indices:[...]}
    """
    zero = {
        'applicable': False,
        'skipped': False,
        'pseudo_node_count': 0,
        'sample_nodes': [],
    }
    if gdf.empty:
        return zero

    gdf = gdf.reset_index(drop=True)
    positions = _line_positions(gdf)
    if len(positions) == 0:
        return zero

    if len(positions) > _LINE_FEATURE_CAP and not force:
        return {
            'applicable': True,
            'skipped': True,
            'pseudo_node_count': 0,
            'sample_nodes': [],
        }

    geoms = gdf.geometry.to_numpy()
    ndig = 10
    node_map = {}
    for pos in positions:
        for part in _iter_line_parts(geoms[pos]):
            for _, coord in _part_endpoints(part):
                key = (round(coord[0], ndig), round(coord[1], ndig))
                node_map.setdefault(key, []).append(int(pos))

    pseudo = [(k, v) for k, v in node_map.items() if len(v) == 2]
    sample_nodes = [
        {'coord': [float(k[0]), float(k[1])], 'feature_indices': sorted(set(v))}
        for k, v in pseudo[:_MAX_SAMPLE]
    ]

    return {
        'applicable': True,
        'skipped': False,
        'pseudo_node_count': len(pseudo),
        'sample_nodes': sample_nodes,
    }


def check_cross_layer_overlap(
    layer_a: gpd.GeoDataFrame,
    layer_b: gpd.GeoDataFrame,
    *,
    name_a: str = "A",
    name_b: str = "B",
    force: bool = False,
) -> dict:
    """
    Detect polygons in layer_a whose interior overlaps any polygon in layer_b.

    This generalizes ``check_overlapping_polygons`` to two layers. Boundary-only
    touches (zero shared area) are excluded.

    Returns:
        Dictionary with results:
        - applicable: bool (False if either layer has no usable polygons)
        - skipped: bool (True when capped out and not forced)
        - layer_a / layer_b: str
        - overlap_pair_count: int
        - features_involved_a / features_involved_b: int
        - sample_pairs: list of {a_index, b_index} (capped)
    """
    zero = {
        'applicable': False,
        'skipped': False,
        'layer_a': name_a,
        'layer_b': name_b,
        'overlap_pair_count': 0,
        'features_involved_a': 0,
        'features_involved_b': 0,
        'sample_pairs': [],
    }
    if layer_a.empty or layer_b.empty:
        return zero

    a = layer_a.reset_index(drop=True)
    b = layer_b.reset_index(drop=True)
    pos_a = _polygon_positions(a)
    pos_b = _polygon_positions(b)
    if len(pos_a) == 0 or len(pos_b) == 0:
        return zero

    if (len(pos_a) > _OVERLAP_FEATURE_CAP or len(pos_b) > _OVERLAP_FEATURE_CAP) and not force:
        return {**zero, 'applicable': True, 'skipped': True}

    geoms_a = a.geometry.to_numpy()[pos_a]
    geoms_b = b.geometry.to_numpy()[pos_b]
    tree = STRtree(geoms_b)
    pairs = tree.query(geoms_a, predicate='intersects')  # (2, N): [a_local, b_local]

    overlap_pairs = []
    involved_a = set()
    involved_b = set()
    for a_local, b_local in zip(pairs[0], pairs[1]):
        ga = geoms_a[a_local]
        gb = geoms_b[b_local]
        if ga.intersection(gb).area > 0:
            ia = int(pos_a[a_local])
            ib = int(pos_b[b_local])
            overlap_pairs.append({'a_index': ia, 'b_index': ib})
            involved_a.add(ia)
            involved_b.add(ib)

    return {
        'applicable': True,
        'skipped': False,
        'layer_a': name_a,
        'layer_b': name_b,
        'overlap_pair_count': len(overlap_pairs),
        'features_involved_a': len(involved_a),
        'features_involved_b': len(involved_b),
        'sample_pairs': overlap_pairs[:_MAX_SAMPLE],
    }


def check_must_be_covered_by(
    layer_a: gpd.GeoDataFrame,
    layer_b: gpd.GeoDataFrame,
    *,
    name_a: str = "A",
    name_b: str = "B",
    predicate: str = "covered_by",
    force: bool = False,
) -> dict:
    """
    Flag features of layer_a not fully contained by layer_b's coverage.

    Uses ``covered_by`` by default (shared boundaries allowed); ``within`` is
    available but will flag features that merely touch the coverage edge.

    Returns:
        Dictionary with results:
        - applicable: bool
        - skipped: bool
        - layer_a / layer_b: str
        - predicate: str
        - uncovered_count: int
        - uncovered_area_total: float (sum of uncovered remainder areas)
        - sample_indices: list of layer_a positional indices (capped)
    """
    zero = {
        'applicable': False,
        'skipped': False,
        'layer_a': name_a,
        'layer_b': name_b,
        'predicate': predicate,
        'uncovered_count': 0,
        'uncovered_area_total': 0.0,
        'sample_indices': [],
    }
    if layer_a.empty or layer_b.empty:
        return zero

    a = layer_a.reset_index(drop=True)
    b = layer_b.reset_index(drop=True)
    valid_a = _valid_geom_mask(a)
    pos_a = np.where(valid_a.to_numpy())[0]
    pos_b = _polygon_positions(b)
    if len(pos_a) == 0 or len(pos_b) == 0:
        return zero

    if (len(pos_a) > _COVERAGE_FEATURE_CAP or len(pos_b) > _COVERAGE_FEATURE_CAP) and not force:
        return {**zero, 'applicable': True, 'skipped': True}

    geoms_a = a.geometry.to_numpy()[pos_a]
    coverage_b = shapely.union_all(b.geometry.to_numpy()[pos_b])

    if predicate == "within":
        covered = shapely.within(geoms_a, coverage_b)
    else:
        covered = shapely.covered_by(geoms_a, coverage_b)
    covered = np.asarray(covered, dtype=bool)

    uncovered_local = np.where(~covered)[0]
    uncovered_positions = [int(pos_a[i]) for i in uncovered_local]

    uncovered_area_total = 0.0
    for i in uncovered_local:
        g = geoms_a[i]
        if g.geom_type in ('Polygon', 'MultiPolygon'):
            try:
                uncovered_area_total += float(g.difference(coverage_b).area)
            except Exception:  # noqa: BLE001 - remainder area is best-effort
                pass

    return {
        'applicable': True,
        'skipped': False,
        'layer_a': name_a,
        'layer_b': name_b,
        'predicate': predicate,
        'uncovered_count': len(uncovered_positions),
        'uncovered_area_total': float(uncovered_area_total),
        'sample_indices': uncovered_positions[:_MAX_SAMPLE],
    }


def run_multilayer_checks(
    layers,
    *,
    coverage_layers=None,
    must_not_overlap=None,
    must_be_covered_by=None,
    force: bool = False,
) -> dict:
    """
    Run inter-layer and coverage checks across a mapping of layers.

    Each rule is isolated so one failure never aborts the others. Rules that
    reference an unknown layer return an ``{'error': ...}`` entry.

    Args:
        layers: Mapping of layer name -> GeoDataFrame.
        coverage_layers: Layer names to gap-check. Defaults to every layer that
            contains polygons.
        must_not_overlap: Iterable of (name_a, name_b) overlap rules.
        must_be_covered_by: Iterable of (name_a, name_b) coverage rules.
        force: Force checks past the feature caps.

    Returns:
        Dictionary with 'coverage_gaps', 'must_not_overlap', 'must_be_covered_by'.
    """
    def _safe(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - report per-rule, do not abort
            return {'error': str(e)}

    if coverage_layers is None:
        coverage_layers = [
            name for name, gdf in layers.items()
            if len(_polygon_positions(gdf)) > 0
        ]

    coverage_results = {}
    for name in coverage_layers:
        if name not in layers:
            coverage_results[name] = {'error': f'layer not found: {name}'}
        else:
            coverage_results[name] = _safe(check_coverage_gaps, layers[name], force=force)

    overlap_results = []
    for a, b in (must_not_overlap or []):
        if a not in layers or b not in layers:
            missing = a if a not in layers else b
            overlap_results.append(
                {'layer_a': a, 'layer_b': b, 'error': f'layer not found: {missing}'}
            )
        elif a == b:
            res = _safe(check_overlapping_polygons, layers[a], force=force)
            overlap_results.append({**res, 'layer_a': a, 'layer_b': b})
        else:
            overlap_results.append(
                _safe(check_cross_layer_overlap, layers[a], layers[b],
                      name_a=a, name_b=b, force=force)
            )

    covered_results = []
    for a, b in (must_be_covered_by or []):
        if a not in layers or b not in layers:
            missing = a if a not in layers else b
            covered_results.append(
                {'layer_a': a, 'layer_b': b, 'error': f'layer not found: {missing}'}
            )
        else:
            covered_results.append(
                _safe(check_must_be_covered_by, layers[a], layers[b],
                      name_a=a, name_b=b, force=force)
            )

    return {
        'coverage_gaps': coverage_results,
        'must_not_overlap': overlap_results,
        'must_be_covered_by': covered_results,
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
            'coverage_gaps': _safe(check_coverage_gaps, gdf, force=force_overlap),
            'lines': {
                'dangles': _safe(check_line_dangles, gdf, force=force_overlap),
                'self_intersections': _safe(check_line_self_intersections, gdf),
                'pseudo_nodes': _safe(check_pseudo_nodes, gdf, force=force_overlap),
            },
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
