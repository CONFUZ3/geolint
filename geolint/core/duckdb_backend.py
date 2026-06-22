"""
Optional DuckDB-spatial backend for large datasets.

DuckDB can compute summary statistics over a (possibly huge, possibly remote)
GeoParquet file via streaming SQL, without materialising a GeoDataFrame in
memory. This is an opt-in fast path; everything degrades gracefully when the
``duckdb`` package is not installed.
"""

from typing import Dict, Optional


def duckdb_available() -> bool:
    """True when the optional ``duckdb`` dependency is importable."""
    try:
        import duckdb  # noqa: F401
        return True
    except Exception:
        return False


def _require_duckdb():
    try:
        import duckdb
        return duckdb
    except Exception as e:  # pragma: no cover - exercised only without duckdb
        raise RuntimeError(
            "the DuckDB backend requires the 'duckdb' package "
            "(pip install 'geolint[duckdb]')"
        ) from e


def _connect(duckdb):
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
    except Exception:  # spatial may be unavailable; counting still works
        pass
    return con


def quick_stats(path, *, geometry_column: str = "geometry") -> Dict:
    """
    Compute feature count (and best-effort bbox) for a Parquet file via DuckDB.

    Args:
        path: Local path or remote URL readable by DuckDB's read_parquet.
        geometry_column: Name of the geometry column for the bbox attempt.

    Returns:
        {'feature_count': int, 'bbox': [minx,miny,maxx,maxy] | None, 'engine': 'duckdb'}
    """
    duckdb = _require_duckdb()
    con = _connect(duckdb)
    src = str(path).replace("'", "''")
    try:
        count = con.execute(f"SELECT count(*) FROM read_parquet('{src}')").fetchone()[0]
        bbox: Optional[list] = None
        try:
            row = con.execute(
                f"SELECT min(ST_XMin(g)), min(ST_YMin(g)), max(ST_XMax(g)), max(ST_YMax(g)) "
                f"FROM (SELECT ST_GeomFromWKB({geometry_column}) AS g "
                f"FROM read_parquet('{src}'))"
            ).fetchone()
            if row is not None and row[0] is not None:
                bbox = [float(v) for v in row]
        except Exception:
            bbox = None
        return {'feature_count': int(count), 'bbox': bbox, 'engine': 'duckdb'}
    finally:
        con.close()


def can_handle(path) -> bool:
    """True when DuckDB is available and the path looks like a Parquet file."""
    # Strip any URL query string (presigned S3/HTTP URLs always carry one)
    # before checking the extension.
    head = str(path).split('?', 1)[0].lower()
    return duckdb_available() and head.endswith(('.parquet', '.pq'))
