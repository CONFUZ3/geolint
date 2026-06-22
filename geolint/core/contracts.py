"""
Data contract validation (the spatial equivalent of a schema/type check).

A contract declares expectations about a dataset: required columns, dtypes,
expected geometry type / CRS / bounds, and per-column rules (nullability,
uniqueness, ranges, enums, regex). ``check_schema_contract`` returns a list of
structured violations.
"""

import re
from typing import Dict, List

import geopandas as gpd
import numpy as np
import pandas as pd

_MAX_SAMPLE = 20

_DTYPE_KINDS = {
    'integer': ('i', 'u'),
    'int': ('i', 'u'),
    'float': ('f', 'i', 'u'),
    'number': ('f', 'i', 'u'),
    'string': ('O', 'U', 'S'),
    'str': ('O', 'U', 'S'),
    'bool': ('b',),
    'boolean': ('b',),
}


def _violation(rule, column, message, count=0, sample=None):
    return {
        'rule': rule,
        'column': column,
        'message': message,
        'count': int(count),
        'sample': sample or [],
    }


def check_schema_contract(gdf: gpd.GeoDataFrame, contract: Dict) -> List[Dict]:
    """
    Validate a GeoDataFrame against a data contract.

    Args:
        gdf: GeoDataFrame to check.
        contract: Contract spec (see module docstring / README).

    Returns:
        List of violation dicts: {rule, column, message, count, sample}.
        An empty list means the dataset satisfies the contract.
    """
    violations: List[Dict] = []
    if not contract:
        return violations

    geom_col = gdf.geometry.name if not gdf.empty or gdf.columns.size else 'geometry'
    attr_cols = [c for c in gdf.columns if c != geom_col]

    # Required columns
    for col in contract.get('required_columns', []) or []:
        if col not in attr_cols:
            violations.append(_violation('required_column', col, f"missing required column '{col}'", 1))

    # Dtypes
    for col, expected in (contract.get('dtypes') or {}).items():
        if col not in gdf.columns:
            violations.append(_violation('dtype', col, f"column '{col}' missing for dtype check", 1))
            continue
        kinds = _DTYPE_KINDS.get(str(expected).lower())
        if kinds is None:
            violations.append(_violation('dtype', col, f"unknown expected dtype '{expected}'", 1))
            continue
        if gdf[col].dtype.kind not in kinds:
            violations.append(_violation(
                'dtype', col,
                f"column '{col}' has dtype kind '{gdf[col].dtype.kind}', expected {expected}", 1,
            ))

    # Geometry type
    expected_geom = contract.get('geometry_type')
    if expected_geom and not gdf.empty:
        allowed = {expected_geom}
        if expected_geom in ('Polygon', 'LineString', 'Point'):
            allowed.add('Multi' + expected_geom)
        # Operate on the full series (not dropna) so positional indices stay
        # aligned with the rest of the report; null geometries are not a
        # geometry-type violation (they are reported separately).
        types = gdf.geom_type
        bad_mask = types.notna() & ~types.isin(allowed)
        n = int(bad_mask.sum())
        if n > 0:
            violations.append(_violation(
                'geometry_type', None,
                f"{n} features are not {expected_geom}", n,
                [int(i) for i in np.where(bad_mask.to_numpy())[0][:_MAX_SAMPLE]],
            ))

    # CRS
    expected_crs = contract.get('crs')
    if expected_crs is not None:
        if gdf.crs is None:
            violations.append(_violation('crs', None, "dataset has no CRS; expected " + str(expected_crs), 1))
        else:
            try:
                from pyproj import CRS
                if CRS.from_user_input(gdf.crs) != CRS.from_user_input(expected_crs):
                    violations.append(_violation(
                        'crs', None,
                        f"CRS is {gdf.crs.to_string()}, expected {expected_crs}", 1,
                    ))
            except Exception as e:  # noqa: BLE001
                violations.append(_violation('crs', None, f"could not compare CRS: {e}", 1))

    # Bounds: data must lie within the declared extent.
    declared = contract.get('bounds')
    if declared and not gdf.empty:
        minx, miny, maxx, maxy = gdf.total_bounds
        tol = 1e-9
        out = []
        if 'minx' in declared and minx < declared['minx'] - tol:
            out.append(f"minx {minx} < {declared['minx']}")
        if 'miny' in declared and miny < declared['miny'] - tol:
            out.append(f"miny {miny} < {declared['miny']}")
        if 'maxx' in declared and maxx > declared['maxx'] + tol:
            out.append(f"maxx {maxx} > {declared['maxx']}")
        if 'maxy' in declared and maxy > declared['maxy'] + tol:
            out.append(f"maxy {maxy} > {declared['maxy']}")
        if out:
            violations.append(_violation('bounds', None, "data outside declared bounds: " + "; ".join(out), len(out)))

    # Per-column rules
    for spec in contract.get('columns', []) or []:
        col = spec.get('name')
        if col is None:
            continue
        if col not in gdf.columns:
            violations.append(_violation('column', col, f"column '{col}' missing", 1))
            continue
        series = gdf[col]

        if spec.get('not_null'):
            n = int(series.isna().sum())
            if n > 0:
                violations.append(_violation('not_null', col, f"{n} null values in '{col}'", n))

        if spec.get('unique'):
            dup_mask = series.duplicated(keep=False) & series.notna()
            n = int(dup_mask.sum())
            if n > 0:
                violations.append(_violation('unique', col, f"{n} non-unique values in '{col}'", n))

        if 'min' in spec or 'max' in spec:
            numeric = pd.to_numeric(series, errors='coerce')
            mask = pd.Series(False, index=series.index)
            if 'min' in spec:
                mask = mask | (numeric < spec['min'])
            if 'max' in spec:
                mask = mask | (numeric > spec['max'])
            n = int(mask.fillna(False).sum())
            if n > 0:
                violations.append(_violation('range', col, f"{n} values in '{col}' out of [{spec.get('min')}, {spec.get('max')}]", n))

        if spec.get('enum') is not None:
            allowed = set(spec['enum'])
            mask = ~series.isin(allowed) & series.notna()
            n = int(mask.sum())
            if n > 0:
                violations.append(_violation('enum', col, f"{n} values in '{col}' not in allowed set", n))

        if spec.get('regex'):
            pattern = re.compile(spec['regex'])
            non_null = series.dropna().astype(str)
            bad = non_null[~non_null.map(lambda v: bool(pattern.fullmatch(v)))]
            n = int(len(bad))
            if n > 0:
                violations.append(_violation('regex', col, f"{n} values in '{col}' do not match /{spec['regex']}/", n))

    return violations
