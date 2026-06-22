"""
Tests for Phase 2: config-as-code, data contracts, and severity-tagged findings.
"""

import json

import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon, box

from geolint.core.config import (
    Config,
    default_config,
    discover_config_path,
    load_config,
)
from geolint.core.contracts import check_schema_contract
from geolint.core.findings import (
    apply_baseline,
    collect_findings,
    exit_code,
    load_baseline,
    summarize,
    write_baseline,
)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

class TestConfig:
    def test_defaults(self):
        cfg = default_config()
        assert cfg.severity('invalid_geometries') == 'error'
        assert cfg.severity('pseudo_nodes') == 'info'
        assert cfg.severity('unknown_check') == 'warning'  # fallback
        assert cfg.source is None

    def test_load_toml(self, tmp_path):
        path = tmp_path / "geolint.toml"
        path.write_text(
            '[severity]\n'
            'overlapping_polygons = "error"\n'
            'pseudo_nodes = "off"\n\n'
            '[thresholds]\n'
            'gap_area_tol = 0.5\n\n'
            '[contract]\n'
            'required_columns = ["id"]\n',
            encoding='utf-8',
        )
        cfg = load_config(path)
        assert cfg.severity('overlapping_polygons') == 'error'
        assert cfg.severity('pseudo_nodes') == 'off'
        assert cfg.threshold('gap_area_tol', 0.0) == 0.5
        assert cfg.contract['required_columns'] == ['id']
        assert cfg.source == str(path)

    def test_discover(self, tmp_path):
        (tmp_path / "geolint.toml").write_text('[severity]\n', encoding='utf-8')
        assert discover_config_path(tmp_path) is not None

    def test_invalid_severity_raises(self, tmp_path):
        path = tmp_path / "geolint.toml"
        path.write_text('[severity]\nduplicate_geometries = "nope"\n', encoding='utf-8')
        with pytest.raises(ValueError):
            load_config(path)


# --------------------------------------------------------------------------- #
# Data contracts
# --------------------------------------------------------------------------- #

def _contract_gdf():
    return gpd.GeoDataFrame(
        {'id': [1, 2, 3], 'pop': [10, 20, 30], 'cat': ['a', 'b', 'a']},
        geometry=[box(0, 0, 1, 1), box(1, 1, 2, 2), box(2, 2, 3, 3)],
        crs='EPSG:4326',
    )


class TestContracts:
    def test_clean_contract(self):
        contract = {
            'required_columns': ['id', 'pop'],
            'geometry_type': 'Polygon',
            'crs': 'EPSG:4326',
        }
        assert check_schema_contract(_contract_gdf(), contract) == []

    def test_missing_required_column(self):
        v = check_schema_contract(_contract_gdf(), {'required_columns': ['missing']})
        assert any(x['rule'] == 'required_column' for x in v)

    def test_geometry_type_mismatch(self):
        v = check_schema_contract(_contract_gdf(), {'geometry_type': 'Point'})
        assert any(x['rule'] == 'geometry_type' and x['count'] == 3 for x in v)

    def test_geometry_type_sample_is_positional_with_null(self):
        # A leading null geometry must not offset the reported positional index.
        gdf = gpd.GeoDataFrame(
            {'id': [1, 2, 3]},
            geometry=[None, Point(0, 0), Polygon([(0, 0), (1, 0), (1, 1)])],
            crs='EPSG:4326',
        )
        geom = [x for x in check_schema_contract(gdf, {'geometry_type': 'Polygon'})
                if x['rule'] == 'geometry_type'][0]
        assert geom['count'] == 1        # only the Point; null is not a type violation
        assert geom['sample'] == [1]     # positional index of the Point, not 0

    def test_crs_mismatch(self):
        v = check_schema_contract(_contract_gdf(), {'crs': 'EPSG:3857'})
        assert any(x['rule'] == 'crs' for x in v)

    def test_bounds_outside(self):
        v = check_schema_contract(_contract_gdf(), {'bounds': {'maxx': 2.0}})
        assert any(x['rule'] == 'bounds' for x in v)

    def test_column_rules(self):
        contract = {'columns': [
            {'name': 'pop', 'min': 0, 'max': 25},   # 30 is out of range
            {'name': 'cat', 'unique': True},         # 'a' repeats
            {'name': 'cat', 'enum': ['a', 'b']},     # all allowed
        ]}
        v = check_schema_contract(_contract_gdf(), contract)
        rules = {x['rule'] for x in v}
        assert 'range' in rules
        assert 'unique' in rules
        assert 'enum' not in rules

    def test_regex(self):
        gdf = gpd.GeoDataFrame(
            {'code': ['AB12', 'XYZ', 'CD34']},
            geometry=[Point(0, 0), Point(1, 1), Point(2, 2)], crs='EPSG:4326',
        )
        v = check_schema_contract(gdf, {'columns': [{'name': 'code', 'regex': r'[A-Z]{2}\d{2}'}]})
        assert any(x['rule'] == 'regex' and x['count'] == 1 for x in v)


# --------------------------------------------------------------------------- #
# Findings + severity + baseline
# --------------------------------------------------------------------------- #

def _report_with(**counts):
    return {
        'validation': {'crs_present': True},
        'geometry_validation': {
            'invalid_count': counts.get('invalid', 0),
            'empty_count': 0, 'null_count': 0, 'mixed_types': False, 'invalid_indices': [],
        },
        'checks': {
            'topology': {
                'duplicate_geometries': {'duplicate_count': counts.get('dups', 0), 'sample_indices': []},
            },
            'attributes': {}, 'coordinates': {},
        },
    }


class TestFindings:
    def test_collect_and_severity(self):
        findings = collect_findings(_report_with(invalid=2, dups=3), default_config())
        by_id = {f['check_id']: f for f in findings}
        assert by_id['invalid_geometries']['severity'] == 'error'
        assert by_id['duplicate_geometries']['severity'] == 'warning'

    def test_severity_off_suppresses(self):
        cfg = Config(severities={'duplicate_geometries': 'off'})
        findings = collect_findings(_report_with(dups=3), cfg)
        assert all(f['check_id'] != 'duplicate_geometries' for f in findings)

    def test_summarize_and_exit_code(self):
        findings = collect_findings(_report_with(invalid=1, dups=1), default_config())
        summary = summarize(findings)
        assert summary['error'] == 1 and summary['warning'] == 1
        assert exit_code(findings) == 1            # error present
        # Only-warning findings: clean of errors but strict fails.
        warn_only = collect_findings(_report_with(dups=1), default_config())
        assert exit_code(warn_only) == 0
        assert exit_code(warn_only, strict=True) == 1

    def test_contract_findings(self):
        report = _report_with()
        report['contract'] = [{'rule': 'required_column', 'column': 'id', 'message': 'missing', 'count': 1}]
        findings = collect_findings(report, default_config())
        assert any(f['check_id'].startswith('contract.') and f['severity'] == 'error' for f in findings)

    def test_baseline_roundtrip(self, tmp_path):
        findings = collect_findings(_report_with(invalid=2, dups=3), default_config())
        bpath = tmp_path / "baseline.json"
        write_baseline(bpath, findings)
        loaded = load_baseline(bpath)
        kept, suppressed = apply_baseline(findings, loaded)
        assert kept == []
        assert suppressed == len(findings)
