"""
Findings: flatten check results into severity-tagged findings.

This is the layer that turns raw check dictionaries into a linter verdict. Each
finding carries a severity (from config) and a stable fingerprint so a baseline
file can suppress known issues for incremental adoption.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from geolint.core.config import Config, default_config

_SEVERITY_ORDER = {'error': 3, 'warning': 2, 'info': 1, 'off': 0}


def _finding(check_id, severity, message, count, fingerprint, locations=None):
    return {
        'check_id': check_id,
        'severity': severity,
        'message': message,
        'count': int(count),
        'fingerprint': fingerprint,
        'locations': locations or [],
    }


def _sub(node, *keys):
    for key in keys:
        if not isinstance(node, dict):
            return {}
        node = node.get(key, {})
    return node if isinstance(node, dict) else {}


def collect_findings(report: Dict, config: Optional[Config] = None) -> List[Dict]:
    """
    Build the list of severity-tagged findings from a validation report.

    Args:
        report: A validation report (with geometry_validation, checks, and
            optionally conformance / contract).
        config: Severity configuration (defaults applied when None).

    Returns:
        List of finding dicts, excluding any whose configured severity is 'off'.
    """
    if config is None:
        config = default_config()

    findings: List[Dict] = []

    def add(check_id, message, count, *, locations=None, fingerprint=None, severity=None):
        if not count:
            return
        sev = severity or config.severity(check_id)
        if sev == 'off':
            return
        findings.append(_finding(check_id, sev, message, count, fingerprint or check_id, locations))

    gv = report.get('geometry_validation', {}) or {}
    add('invalid_geometries', f"{gv.get('invalid_count', 0)} invalid geometries",
        gv.get('invalid_count', 0), locations=gv.get('invalid_indices'))
    add('empty_geometries', f"{gv.get('empty_count', 0)} empty geometries", gv.get('empty_count', 0))
    add('null_geometries', f"{gv.get('null_count', 0)} null geometries", gv.get('null_count', 0))
    if gv.get('mixed_types'):
        add('mixed_types', f"mixed geometry types: {gv.get('geometry_types')}", 1)
    if report.get('validation', {}).get('crs_present') is False:
        add('crs_missing', "no CRS information found", 1)

    topo = _sub(report, 'checks', 'topology')
    add('duplicate_geometries',
        f"{_sub(topo, 'duplicate_geometries').get('duplicate_count', 0)} duplicate geometries",
        _sub(topo, 'duplicate_geometries').get('duplicate_count', 0),
        locations=_sub(topo, 'duplicate_geometries').get('sample_indices'))

    ov = _sub(topo, 'overlapping_polygons')
    if not ov.get('skipped', False):
        add('overlapping_polygons', f"{ov.get('overlap_pair_count', 0)} overlapping polygon pairs",
            ov.get('overlap_pair_count', 0))

    sl = _sub(topo, 'slivers')
    sliver_count = (sl.get('zero_area_polygons', 0) or 0) + (sl.get('zero_length_lines', 0) or 0)
    add('slivers', f"{sliver_count} sliver/zero-size geometries", sliver_count,
        locations=sl.get('sample_indices'))

    add('duplicate_vertices',
        f"{_sub(topo, 'duplicate_vertices').get('features_with_duplicate_vertices', 0)} features with duplicate vertices",
        _sub(topo, 'duplicate_vertices').get('features_with_duplicate_vertices', 0),
        locations=_sub(topo, 'duplicate_vertices').get('sample_indices'))

    cg = _sub(topo, 'coverage_gaps')
    if not cg.get('skipped', False):
        add('coverage_gaps', f"{cg.get('gap_count', 0)} coverage gaps", cg.get('gap_count', 0))

    dn = _sub(topo, 'lines', 'dangles')
    if not dn.get('skipped', False):
        add('line_dangles', f"{dn.get('dangle_count', 0)} dangling line endpoints",
            dn.get('dangle_count', 0))
    si = _sub(topo, 'lines', 'self_intersections')
    add('self_intersections', f"{si.get('self_intersecting_count', 0)} self-intersecting lines",
        si.get('self_intersecting_count', 0), locations=si.get('sample_indices'))
    pn = _sub(topo, 'lines', 'pseudo_nodes')
    add('pseudo_nodes', f"{pn.get('pseudo_node_count', 0)} pseudo-nodes", pn.get('pseudo_node_count', 0))

    attr = _sub(report, 'checks', 'attributes')
    iu = _sub(attr, 'id_uniqueness')
    add('id_uniqueness', f"{iu.get('duplicate_count', 0)} duplicate id values in '{iu.get('id_column')}'",
        iu.get('duplicate_count', 0), locations=iu.get('sample_indices'))
    fully_null = len(_sub(attr, 'null_attributes').get('fully_null_columns') or [])
    add('null_attributes', f"{fully_null} fully-null columns", fully_null)
    sfn = _sub(attr, 'shapefile_field_names')
    unsafe = (len(sfn.get('long_names') or []) + len(sfn.get('truncation_collisions') or [])
              + len(sfn.get('non_ascii_names') or []))
    add('shapefile_field_names', f"{unsafe} shapefile-unsafe field names", unsafe)

    coord = _sub(report, 'checks', 'coordinates')
    add('winding_order',
        f"{_sub(coord, 'winding_order').get('non_compliant_count', 0)} polygons with non-RFC7946 winding",
        _sub(coord, 'winding_order').get('non_compliant_count', 0),
        locations=_sub(coord, 'winding_order').get('sample_indices'))
    cr = _sub(coord, 'coordinate_range')
    if cr.get('applicable', False):
        add('coordinate_range', f"{cr.get('out_of_range_count', 0)} out-of-range coordinates",
            cr.get('out_of_range_count', 0), locations=cr.get('sample_indices'))

    # Data contract violations
    if config.severity('contract') != 'off':
        for v in report.get('contract', []) or []:
            cid = f"contract.{v.get('rule')}.{v.get('column') or '-'}"
            add(cid, v.get('message', 'contract violation'), v.get('count', 1) or 1,
                locations=v.get('sample'), fingerprint=cid,
                severity=config.severity('contract'))

    # Conformance profile failures (use the profile's own per-check severity).
    if config.severity('conformance') != 'off':
        conf = report.get('conformance', {}) or {}
        for res in (conf.get('checks', {}) or {}).values():
            if res.get('status') == 'fail':
                cid = f"conformance.{res.get('check_id')}"
                add(cid, f"{res.get('title')}: {res.get('message')}", res.get('violation_count', 1) or 1,
                    locations=res.get('sample'), fingerprint=cid, severity=res.get('severity', 'error'))

    return findings


def summarize(findings: List[Dict]) -> Dict[str, int]:
    """Count findings by severity."""
    summary = {'error': 0, 'warning': 0, 'info': 0, 'total': 0}
    for f in findings:
        sev = f.get('severity', 'warning')
        if sev in summary:
            summary[sev] += 1
        summary['total'] += 1
    return summary


def exit_code(findings: List[Dict], *, strict: bool = False) -> int:
    """
    Return 1 when the findings should fail a build, else 0.

    With ``strict``, warnings count as failures too.
    """
    threshold = 'warning' if strict else 'error'
    cutoff = _SEVERITY_ORDER[threshold]
    for f in findings:
        if _SEVERITY_ORDER.get(f.get('severity', 'warning'), 0) >= cutoff:
            return 1
    return 0


def load_baseline(path) -> set:
    """Load a set of suppressed fingerprints from a baseline JSON file."""
    path = Path(path)
    if not path.exists():
        return set()
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(data.get('fingerprints', []))


def write_baseline(path, findings: List[Dict]) -> None:
    """Write the current findings' fingerprints to a baseline JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fingerprints = sorted({f['fingerprint'] for f in findings})
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'fingerprints': fingerprints}, f, indent=2)


def apply_baseline(findings: List[Dict], baseline: set) -> Tuple[List[Dict], int]:
    """
    Drop findings whose fingerprint is in the baseline.

    Returns (kept_findings, suppressed_count).
    """
    if not baseline:
        return findings, 0
    kept = [f for f in findings if f['fingerprint'] not in baseline]
    return kept, len(findings) - len(kept)
