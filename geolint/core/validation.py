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


_REMOTE_SCHEMES = ('s3://', 'gs://', 'http://', 'https://', '/vsi')


def is_remote(path) -> bool:
    """True when ``path`` is a remote URL / GDAL virtual path rather than local."""
    return str(path).startswith(_REMOTE_SCHEMES)


def to_vsi_path(url: str) -> str:
    """
    Translate a remote URL into a GDAL /vsi path for vector formats.

    s3://b/k -> /vsis3/b/k, gs://b/k -> /vsigs/b/k, http(s):// -> /vsicurl/...,
    and existing /vsi... paths are returned unchanged.
    """
    if url.startswith('/vsi'):
        return url
    if url.startswith('s3://'):
        return '/vsis3/' + url[len('s3://'):]
    if url.startswith('gs://'):
        return '/vsigs/' + url[len('gs://'):]
    if url.startswith(('http://', 'https://')):
        return '/vsicurl/' + url
    return url


def _load_remote(url: str) -> gpd.GeoDataFrame:
    """Load a dataset from a remote URL (best effort, no local existence check)."""
    head = url.split('?', 1)[0].lower()
    if head.endswith(('.parquet', '.pq')):
        # pyarrow/fsspec handle s3:// and https:// for Parquet.
        return gpd.read_parquet(url)
    return gpd.read_file(to_vsi_path(url))


def load_dataset(path: Union[str, Path]) -> gpd.GeoDataFrame:
    """
    Load a geospatial dataset from various formats.

    Supports:
    - GeoPackage (.gpkg)
    - GeoJSON (.geojson)
    - Shapefile (.zip containing .shp/.shx/.dbf/.prj)
    - Remote URLs (s3://, gs://, http(s)://) via GDAL /vsi or pyarrow

    Args:
        path: Path or URL to the dataset

    Returns:
        GeoDataFrame containing the loaded data

    Raises:
        ValueError: If file format is not supported
        FileNotFoundError: If a local file does not exist
    """
    if is_remote(path):
        return _load_remote(str(path))

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


def _populate_report(report: Dict, gdf: gpd.GeoDataFrame, config=None) -> Dict:
    """
    Populate a report dict with geometry validation, checks, warnings and status
    for an already-loaded GeoDataFrame. Used by both single-file validation and
    per-layer multi-layer validation so the logic stays in one place.

    When ``config`` is given, its thresholds are threaded into run_checks.
    """
    # Validate geometries
    geom_validation = validate_geometries(gdf)
    report['geometry_validation'] = geom_validation

    # Run extended checks (topology, attributes, coordinates)
    if config is not None:
        checks = run_checks(
            gdf,
            gap_area_tol=config.threshold('gap_area_tol', 0.0),
            dangle_tolerance=config.threshold('dangle_tolerance', 0.0),
            sliver_area_tol=config.threshold('sliver_area_tol', 1e-12),
            sliver_length_tol=config.threshold('sliver_length_tol', 1e-12),
        )
    else:
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

    coverage_gaps = _sub('topology', 'coverage_gaps')
    if not coverage_gaps.get('skipped', False) and coverage_gaps.get('gap_count', 0) > 0:
        report['warnings'].append(f"Found {coverage_gaps['gap_count']} coverage gaps")

    dangles = _sub('topology', 'lines', 'dangles')
    if not dangles.get('skipped', False) and dangles.get('dangle_count', 0) > 0:
        report['warnings'].append(f"Found {dangles['dangle_count']} dangling line endpoints")

    self_int = _sub('topology', 'lines', 'self_intersections')
    if self_int.get('self_intersecting_count', 0) > 0:
        report['warnings'].append(
            f"Found {self_int['self_intersecting_count']} self-intersecting lines"
        )

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
    return report


def _empty_report(name: str) -> Dict:
    """Build the empty report skeleton used by both validation entry points."""
    return {
        'file_path': name,
        'file_name': name,
        'file_size': 0,
        'timestamp': pd.Timestamp.now().isoformat(),
        'validation': {},
        'shapefile_bundle': {},
        'geometry_validation': {},
        'checks': {},
        'warnings': [],
        'errors': [],
    }


def list_layers(path: Union[str, Path]) -> list:
    """
    List the layer names available in a dataset.

    Multi-layer container formats (GeoPackage, SQLite, FileGDB) are enumerated;
    single-layer formats return a one-element list of the file stem.
    """
    path = Path(path)
    if path.suffix.lower() in ('.gpkg', '.sqlite', '.gdb'):
        try:
            import pyogrio
            return [str(row[0]) for row in pyogrio.list_layers(path)]
        except Exception:
            try:
                import fiona
                return list(fiona.listlayers(str(path)))
            except Exception:
                pass
    return [path.stem]


def load_layers(inputs, *, layers=None) -> Dict[str, gpd.GeoDataFrame]:
    """
    Load one or more layers into an ordered name -> GeoDataFrame mapping.

    - A single multi-layer GeoPackage: enumerate all layers (or the subset in
      ``layers``), keyed by layer name.
    - Multiple file paths (or a single non-GPKG file): each loaded via
      ``load_dataset`` and keyed by file stem (collisions disambiguated by '#N').

    Args:
        inputs: A path, or a sequence of paths.
        layers: Optional subset of layer names to load (GeoPackage only).

    Returns:
        Dict mapping layer/file name to GeoDataFrame (insertion-ordered).
    """
    if isinstance(inputs, (str, Path)):
        inputs = [inputs]
    inputs = [Path(p) for p in inputs]

    result: Dict[str, gpd.GeoDataFrame] = {}

    # Single multi-layer container: enumerate layers.
    if len(inputs) == 1 and inputs[0].suffix.lower() in ('.gpkg', '.sqlite', '.gdb'):
        path = inputs[0]
        available = list_layers(path)
        chosen = layers if layers is not None else available
        for name in chosen:
            if name not in available:
                raise ValueError(f"Layer not found in {path.name}: {name}")
            result[str(name)] = gpd.read_file(path, layer=name)
        return result

    # One or more files: key by stem with collision disambiguation.
    for p in inputs:
        key = p.stem
        if key in result:
            i = 2
            while f"{key}#{i}" in result:
                i += 1
            key = f"{key}#{i}"
        result[key] = load_dataset(p)
    return result


def run_multilayer_validation(
    inputs,
    *,
    layers=None,
    crs_policy: str = 'error',
    target_crs=None,
    coverage_layers=None,
    must_not_overlap=None,
    must_be_covered_by=None,
    force: bool = False,
) -> Tuple[Dict, Dict[str, gpd.GeoDataFrame]]:
    """
    Load multiple layers, validate each individually, align their CRS, and run
    inter-layer / coverage checks.

    Returns:
        Tuple of (multilayer_report, aligned_layer_mapping).
    """
    # Imported here to avoid any import-order coupling at module load.
    from geolint.core.checks import run_multilayer_checks
    from geolint.core.crs import get_crs_info
    from geolint.core.report import generate_multilayer_report, generate_report
    from geolint.core.transform import align_layers_crs

    layer_map = load_layers(inputs, layers=layers)

    per_layer_reports: Dict[str, Dict] = {}
    for name, gdf in layer_map.items():
        sub = _empty_report(name)
        sub['validation']['loaded_successfully'] = True
        sub['validation']['feature_count'] = len(gdf)
        sub['validation']['column_count'] = len(gdf.columns)
        sub['validation']['crs_present'] = gdf.crs is not None
        _populate_report(sub, gdf)
        crs_info = get_crs_info(gdf) if (not gdf.empty and gdf.crs is not None) else None
        per_layer_reports[name] = generate_report(sub, crs_info=crs_info)

    aligned, crs_alignment = align_layers_crs(
        layer_map, policy=crs_policy, target_crs=target_crs
    )

    if crs_alignment.get('aligned'):
        inter_results = run_multilayer_checks(
            aligned,
            coverage_layers=coverage_layers,
            must_not_overlap=must_not_overlap,
            must_be_covered_by=must_be_covered_by,
            force=force,
        )
    else:
        inter_results = {}

    report = generate_multilayer_report(per_layer_reports, inter_results, crs_alignment)
    return report, aligned


def run_validation(path: Union[str, Path], *, profile: str = None,
                   config=None) -> Tuple[Dict, gpd.GeoDataFrame]:
    """
    Run comprehensive validation on a geospatial dataset.

    Args:
        path: Path to the dataset
        profile: Optional conformance profile to run (e.g. 'rfc7946',
            'geopackage', 'geoparquet'). When set, results are stored under the
            'conformance' key and failing error-severity checks add warnings.
        config: Optional geolint Config. When given, its thresholds drive the
            checks, its contract is validated, and severity-tagged findings are
            stored under 'findings' / 'findings_summary'.

    Returns:
        Tuple of (validation_report, loaded_geodataframe)
    """
    # Remote URLs must stay as raw strings - wrapping them in Path mangles the
    # scheme on Windows (s3:// -> s3:/). Keep a Path only for local inputs.
    remote = is_remote(path)
    raw = str(path)
    path_obj = None if remote else Path(path)
    source = raw if remote else path_obj
    suffix = (raw.split('?', 1)[0].lower().rsplit('.', 1)[-1]
              if remote else path_obj.suffix.lower().lstrip('.'))

    # Initialize report
    report = {
        'file_path': raw,
        'file_name': raw.rstrip('/').rsplit('/', 1)[-1] if remote else path_obj.name,
        'file_size': (path_obj.stat().st_size if (path_obj and path_obj.exists()) else 0),
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
        gdf = load_dataset(source)
        report['validation']['loaded_successfully'] = True
        report['validation']['feature_count'] = len(gdf)
        report['validation']['column_count'] = len(gdf.columns)
        report['validation']['crs_present'] = gdf.crs is not None

        # Check shapefile bundle if it's a local zip file
        if not remote and suffix == 'zip':
            bundle_info = check_shapefile_bundle(path_obj)
            report['shapefile_bundle'] = bundle_info

            if not bundle_info.get('is_complete', True):
                report['warnings'].append(f"Shapefile bundle incomplete. Missing: {bundle_info.get('missing_files', [])}")

            if not bundle_info.get('has_prj', False):
                report['warnings'].append("No .prj file found - CRS information may be missing")

        # Validate geometries, run checks, build warnings and status.
        _populate_report(report, gdf, config)

        # Optional spec conformance profile.
        if profile:
            from geolint.core.profiles import run_profile
            conformance = run_profile(source, profile, gdf=gdf)
            report['conformance'] = conformance
            for res in conformance.get('checks', {}).values():
                if res.get('status') == 'fail' and res.get('severity') == 'error':
                    report['warnings'].append(
                        f"[{conformance.get('profile')}] {res.get('title')}: {res.get('message')}"
                    )

        # Optional data contract + severity-tagged findings.
        if config is not None:
            if config.contract:
                from geolint.core.contracts import check_schema_contract
                report['contract'] = check_schema_contract(gdf, config.contract)
            from geolint.core.findings import collect_findings, summarize
            findings = collect_findings(report, config)
            report['findings'] = findings
            report['findings_summary'] = summarize(findings)

    except (FileNotFoundError, ValueError, OSError) as e:
        report['validation']['loaded_successfully'] = False
        report['errors'].append(f"Failed to load dataset: {str(e)}")
        report['validation']['status'] = 'error'
        gdf = gpd.GeoDataFrame()  # Return empty GeoDataFrame on error
    # Let unexpected exceptions (e.g. AttributeError, TypeError) propagate

    return report, gdf
