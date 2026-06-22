"""
Spec conformance profiles for GeoLint.

A profile is a declarative list of checks against a target specification
(GeoJSON RFC 7946, GeoPackage, GeoParquet). Each check declares whether it
operates on the in-memory GeoDataFrame ('gdf') or the on-disk file ('path').
Path checks degrade to a 'skip' result when only an in-memory dataset exists.

Every check returns a normalized result:
    {check_id, title, severity, status, message, violation_count, sample}
with status in {'pass', 'fail', 'skip', 'error'}.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Tuple

import geopandas as gpd
import numpy as np

from geolint.core.checks import (
    _MAX_SAMPLE,
    _geom_has_duplicate_vertices,
    check_coordinate_range,
    check_winding_order,
)


@dataclass(frozen=True)
class CheckSpec:
    id: str
    title: str
    target: str               # 'gdf' or 'path'
    func: Callable
    severity: str = 'error'    # 'error' or 'warning'
    applies_when: Optional[Callable] = None


@dataclass(frozen=True)
class Profile:
    name: str
    title: str
    checks: Tuple[CheckSpec, ...] = field(default_factory=tuple)


def _result(spec: CheckSpec, status: str, message: str,
            violation_count: int = 0, sample=None) -> dict:
    return {
        'check_id': spec.id,
        'title': spec.title,
        'severity': spec.severity,
        'status': status,
        'message': message,
        'violation_count': violation_count,
        'sample': sample or [],
    }


# --------------------------------------------------------------------------- #
# RFC 7946 (GeoJSON) checks - all operate on the GeoDataFrame
# --------------------------------------------------------------------------- #

_RFC_ALLOWED_TYPES = {
    'Point', 'MultiPoint', 'LineString', 'MultiLineString',
    'Polygon', 'MultiPolygon', 'GeometryCollection',
}


def _rfc_crs(gdf, spec):
    crs = gdf.crs
    if crs is None:
        return _result(spec, 'pass', 'no CRS set; RFC 7946 default WGS84 assumed')
    epsg = crs.to_epsg()
    if epsg == 4326:
        return _result(spec, 'pass', 'CRS is WGS84 (EPSG:4326)')
    return _result(spec, 'fail', f'CRS must be WGS84; found EPSG:{epsg}', 1)


def _rfc_winding(gdf, spec):
    r = check_winding_order(gdf)
    if not r.get('applicable', False):
        return _result(spec, 'skip', 'no polygons')
    n = r.get('non_compliant_count', 0)
    if n > 0:
        return _result(spec, 'fail', f'{n} polygons violate the right-hand rule',
                       n, r.get('sample_indices'))
    return _result(spec, 'pass', 'polygon winding order is RFC 7946 compliant')


def _rfc_coord_range(gdf, spec):
    r = check_coordinate_range(gdf)
    if not r.get('applicable', False):
        return _result(spec, 'skip', 'not a geographic CRS')
    n = r.get('out_of_range_count', 0)
    if n > 0:
        return _result(spec, 'fail', f'{n} features outside lon/lat range',
                       n, r.get('sample_indices'))
    return _result(spec, 'pass', 'coordinates within lon/lat range')


def _rfc_geometry_types(gdf, spec):
    if gdf.empty:
        return _result(spec, 'skip', 'empty dataset')
    types = gdf.geom_type
    bad_mask = ~types.isin(_RFC_ALLOWED_TYPES) & types.notna()
    bad = [int(i) for i in np.where(bad_mask.to_numpy())[0]]
    if bad:
        return _result(spec, 'fail', f'{len(bad)} features with unsupported geometry type',
                       len(bad), bad[:_MAX_SAMPLE])
    return _result(spec, 'pass', 'all geometry types are RFC 7946 supported')


def _rfc_duplicate_coords(gdf, spec):
    if gdf.empty:
        return _result(spec, 'skip', 'empty dataset')
    flagged = []
    for pos, geom in enumerate(gdf.geometry):
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ('LineString', 'MultiLineString', 'Polygon', 'MultiPolygon') \
                and _geom_has_duplicate_vertices(geom):
            flagged.append(pos)
    if flagged:
        return _result(spec, 'fail', f'{len(flagged)} features with duplicate consecutive vertices',
                       len(flagged), flagged[:_MAX_SAMPLE])
    return _result(spec, 'pass', 'no duplicate consecutive vertices')


def _rfc_antimeridian(gdf, spec):
    if gdf.crs is None or not gdf.crs.is_geographic:
        return _result(spec, 'skip', 'not a geographic CRS')
    if gdf.empty:
        return _result(spec, 'skip', 'empty dataset')
    bounds = gdf.bounds
    wide = (bounds['maxx'] - bounds['minx']) > 180
    idx = [int(i) for i in np.where(wide.to_numpy())[0]]
    if idx:
        return _result(spec, 'fail', f'{len(idx)} features span >180 deg (antimeridian)',
                       len(idx), idx[:_MAX_SAMPLE])
    return _result(spec, 'pass', 'no antimeridian-spanning features')


# --------------------------------------------------------------------------- #
# GeoPackage checks - operate on the on-disk SQLite container
# --------------------------------------------------------------------------- #

def _is_gpkg(path):
    return Path(path).suffix.lower() == '.gpkg'


def _gpkg_connect(path):
    import sqlite3
    p = Path(path)
    try:
        return sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True)
    except Exception:
        return sqlite3.connect(str(p))


def _table_exists(con, name):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _gpkg_application_id(path, spec):
    con = _gpkg_connect(path)
    try:
        app_id = con.execute('PRAGMA application_id').fetchone()[0]
    finally:
        con.close()
    valid = {0x47504B47, 0x47503130, 0x47503131}  # 'GPKG', 'GP10', 'GP11'
    if app_id in valid:
        return _result(spec, 'pass', 'valid GeoPackage application_id')
    return _result(spec, 'fail', f'unexpected application_id: {app_id}', 1)


def _gpkg_contents(path, spec):
    con = _gpkg_connect(path)
    try:
        if not _table_exists(con, 'gpkg_contents'):
            return _result(spec, 'fail', 'gpkg_contents table missing', 1)
        n = con.execute('SELECT count(*) FROM gpkg_contents').fetchone()[0]
        return _result(spec, 'pass', f'gpkg_contents present with {n} entries')
    finally:
        con.close()


def _gpkg_srs(path, spec):
    con = _gpkg_connect(path)
    try:
        if not _table_exists(con, 'gpkg_spatial_ref_sys'):
            return _result(spec, 'fail', 'gpkg_spatial_ref_sys table missing', 1)
        n = con.execute('SELECT count(*) FROM gpkg_spatial_ref_sys').fetchone()[0]
        if n == 0:
            return _result(spec, 'fail', 'gpkg_spatial_ref_sys is empty', 1)
        return _result(spec, 'pass', f'{n} spatial reference systems defined')
    finally:
        con.close()


_GPKG_GEOM_TYPES = {
    'GEOMETRY', 'POINT', 'LINESTRING', 'POLYGON', 'MULTIPOINT',
    'MULTILINESTRING', 'MULTIPOLYGON', 'GEOMETRYCOLLECTION', 'CIRCULARSTRING',
    'COMPOUNDCURVE', 'CURVEPOLYGON', 'MULTICURVE', 'MULTISURFACE', 'CURVE', 'SURFACE',
}


def _gpkg_geometry_columns(path, spec):
    con = _gpkg_connect(path)
    try:
        if not _table_exists(con, 'gpkg_geometry_columns'):
            return _result(spec, 'fail', 'gpkg_geometry_columns table missing', 1)
        rows = con.execute(
            'SELECT table_name, geometry_type_name FROM gpkg_geometry_columns'
        ).fetchall()
        bad = [r[0] for r in rows if str(r[1]).upper() not in _GPKG_GEOM_TYPES]
        if bad:
            return _result(spec, 'fail', f'invalid geometry_type_name in: {bad}',
                           len(bad), bad[:_MAX_SAMPLE])
        return _result(spec, 'pass', f'{len(rows)} geometry column(s) with valid types')
    finally:
        con.close()


def _gpkg_rtree(path, spec):
    con = _gpkg_connect(path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'rtree\\_%' ESCAPE '\\'"
        ).fetchall()
        if rows:
            return _result(spec, 'pass', f'{len(rows)} rtree index object(s) present')
        return _result(spec, 'fail', 'no rtree spatial index found', 1)
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# GeoParquet checks - operate on the on-disk Parquet file metadata
# --------------------------------------------------------------------------- #

_MISSING = object()
_GPQ_ENCODINGS = {
    'WKB', 'point', 'linestring', 'polygon',
    'multipoint', 'multilinestring', 'multipolygon',
}


def _is_parquet(path):
    return Path(path).suffix.lower() in ('.parquet', '.pq')


def _read_geo_meta(path):
    import pyarrow.parquet as pq
    schema = pq.read_schema(path)
    meta = schema.metadata or {}
    raw = meta.get(b'geo')
    if raw is None:
        return None
    return json.loads(raw)


def _gpq_metadata(path, spec):
    try:
        geo = _read_geo_meta(path)
    except Exception as e:  # noqa: BLE001
        return _result(spec, 'error', f'cannot read parquet metadata: {e}')
    if geo is None:
        return _result(spec, 'fail', "no 'geo' file metadata (not GeoParquet)", 1)
    return _result(spec, 'pass', 'geo file metadata present')


def _gpq_version(path, spec):
    geo = _read_geo_meta(path)
    if geo is None:
        return _result(spec, 'skip', 'no geo metadata')
    v = geo.get('version')
    if not v:
        return _result(spec, 'fail', 'geo metadata missing version', 1)
    return _result(spec, 'pass', f'GeoParquet version {v}')


def _gpq_primary_column(path, spec):
    geo = _read_geo_meta(path)
    if geo is None:
        return _result(spec, 'skip', 'no geo metadata')
    pc = geo.get('primary_column')
    cols = geo.get('columns', {})
    if not pc or pc not in cols:
        return _result(spec, 'fail', f'primary_column invalid: {pc}', 1)
    return _result(spec, 'pass', f'primary_column = {pc}')


def _gpq_encoding(path, spec):
    geo = _read_geo_meta(path)
    if geo is None:
        return _result(spec, 'skip', 'no geo metadata')
    bad = [c for c, m in geo.get('columns', {}).items()
           if m.get('encoding') not in _GPQ_ENCODINGS]
    if bad:
        return _result(spec, 'fail', f'invalid/missing encoding for columns: {bad}',
                       len(bad), bad[:_MAX_SAMPLE])
    return _result(spec, 'pass', 'all geometry columns have valid encoding')


def _gpq_crs(path, spec):
    geo = _read_geo_meta(path)
    if geo is None:
        return _result(spec, 'skip', 'no geo metadata')
    from pyproj import CRS
    bad = []
    for c, m in geo.get('columns', {}).items():
        crs = m.get('crs', _MISSING)
        if crs is _MISSING or crs is None:
            continue  # absent/null => OGC:CRS84, valid
        try:
            CRS.from_json_dict(crs) if isinstance(crs, dict) else CRS.from_user_input(crs)
        except Exception:  # noqa: BLE001
            bad.append(c)
    if bad:
        return _result(spec, 'fail', f'invalid CRS metadata for columns: {bad}',
                       len(bad), bad[:_MAX_SAMPLE])
    return _result(spec, 'pass', 'CRS metadata is valid')


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

PROFILE_REGISTRY = {}


def register_profile(profile: Profile) -> None:
    PROFILE_REGISTRY[profile.name] = profile


register_profile(Profile('rfc7946', 'GeoJSON (RFC 7946)', (
    CheckSpec('rfc7946.crs', 'CRS is WGS84', 'gdf', _rfc_crs),
    CheckSpec('rfc7946.winding', 'Right-hand rule winding', 'gdf', _rfc_winding),
    CheckSpec('rfc7946.coord_range', 'Coordinates within lon/lat range', 'gdf', _rfc_coord_range),
    CheckSpec('rfc7946.geometry_types', 'Supported geometry types', 'gdf', _rfc_geometry_types),
    CheckSpec('rfc7946.duplicate_coords', 'No duplicate vertices', 'gdf',
              _rfc_duplicate_coords, severity='warning'),
    CheckSpec('rfc7946.antimeridian', 'No antimeridian-spanning features', 'gdf',
              _rfc_antimeridian, severity='warning'),
)))

register_profile(Profile('geopackage', 'OGC GeoPackage', (
    CheckSpec('gpkg.application_id', 'Valid GeoPackage container', 'path',
              _gpkg_application_id, applies_when=_is_gpkg),
    CheckSpec('gpkg.contents', 'gpkg_contents table present', 'path',
              _gpkg_contents, applies_when=_is_gpkg),
    CheckSpec('gpkg.srs', 'Spatial reference systems defined', 'path',
              _gpkg_srs, applies_when=_is_gpkg),
    CheckSpec('gpkg.geometry_columns', 'Valid geometry_type_name', 'path',
              _gpkg_geometry_columns, applies_when=_is_gpkg),
    CheckSpec('gpkg.rtree_index', 'R-tree spatial index present', 'path',
              _gpkg_rtree, severity='warning', applies_when=_is_gpkg),
)))

register_profile(Profile('geoparquet', 'GeoParquet 1.1', (
    CheckSpec('geoparquet.geo_metadata', "'geo' file metadata present", 'path',
              _gpq_metadata, applies_when=_is_parquet),
    CheckSpec('geoparquet.version', 'GeoParquet version declared', 'path',
              _gpq_version, applies_when=_is_parquet),
    CheckSpec('geoparquet.primary_column', 'Valid primary_column', 'path',
              _gpq_primary_column, applies_when=_is_parquet),
    CheckSpec('geoparquet.encoding', 'Valid column encodings', 'path',
              _gpq_encoding, applies_when=_is_parquet),
    CheckSpec('geoparquet.crs', 'Valid CRS metadata', 'path',
              _gpq_crs, severity='warning', applies_when=_is_parquet),
)))

PROFILE_NAMES = tuple(PROFILE_REGISTRY)


def list_profiles() -> list:
    """Return [{name, title, check_count}] for all registered profiles."""
    return [
        {'name': p.name, 'title': p.title, 'check_count': len(p.checks)}
        for p in PROFILE_REGISTRY.values()
    ]


def _run_spec(spec: CheckSpec, path, get_gdf) -> dict:
    if spec.target == 'path':
        if path is None:
            return _result(spec, 'skip', 'requires a file on disk')
        target = path
    else:
        try:
            target = get_gdf()
        except Exception as e:  # noqa: BLE001
            return _result(spec, 'error', f'failed to load dataset: {e}')
        if target is None:
            return _result(spec, 'skip', 'no dataset available')

    if spec.applies_when is not None:
        try:
            if not spec.applies_when(target):
                return _result(spec, 'skip', 'not applicable to this source')
        except Exception:  # noqa: BLE001
            return _result(spec, 'skip', 'not applicable to this source')

    try:
        return spec.func(target, spec)
    except Exception as e:  # noqa: BLE001 - per-check isolation
        return _result(spec, 'error', str(e))


def run_profile(source, profile_name: str, *, gdf: Optional[gpd.GeoDataFrame] = None) -> dict:
    """
    Run a conformance profile against a file path or GeoDataFrame.

    Args:
        source: A file path (str/Path) or a GeoDataFrame.
        profile_name: Registered profile name (see PROFILE_NAMES).
        gdf: Optional pre-loaded GeoDataFrame (avoids a re-read when source is a
            path and a gdf-target check needs the data).

    Returns:
        {profile, title, conformant, summary, checks} or {profile, error,
        available} for an unknown profile name.
    """
    profile = PROFILE_REGISTRY.get(profile_name)
    if profile is None:
        return {
            'profile': profile_name,
            'error': 'unknown profile',
            'available': list(PROFILE_REGISTRY),
        }

    path = Path(source) if isinstance(source, (str, Path)) else None
    if gdf is None and isinstance(source, gpd.GeoDataFrame):
        gdf = source

    state = {'gdf': gdf}

    def _get_gdf():
        if state['gdf'] is None and path is not None:
            from geolint.core.validation import load_dataset
            state['gdf'] = load_dataset(path)
        return state['gdf']

    results = {}
    summary = {'pass': 0, 'fail': 0, 'skip': 0, 'error': 0}
    for spec in profile.checks:
        res = _run_spec(spec, path, _get_gdf)
        results[spec.id] = res
        summary[res['status']] = summary.get(res['status'], 0) + 1

    conformant = not any(
        r['status'] == 'fail' and r['severity'] == 'error'
        for r in results.values()
    )
    return {
        'profile': profile.name,
        'title': profile.title,
        'conformant': conformant,
        'summary': summary,
        'checks': results,
    }
