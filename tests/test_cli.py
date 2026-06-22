"""
Black-box tests for the GeoLint CLI (geolint.cli.main).

These tests invoke the CLI via ``python -m geolint.cli.main <subcommand> ...``
through subprocess so they exercise the real argparse wiring and exit codes.

They are written against the documented CLI contract. The CLI may still be in
progress, so some tests can fail until the matching subcommand/option lands.
"""

import sys
import subprocess
import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd=None):
    """Run the GeoLint CLI as a subprocess and return the CompletedProcess."""
    result = subprocess.run(
        [sys.executable, "-m", "geolint.cli.main", *args],
        capture_output=True,
        text=True,
        cwd=cwd or str(REPO_ROOT),
    )
    return result


# --------------------------------------------------------------------------- #
# Helpers to build input files
# --------------------------------------------------------------------------- #

def _make_gpkg(path, gdf):
    """Write a GeoDataFrame to a GeoPackage at ``path`` and return the path."""
    gdf.to_file(path, driver="GPKG")
    return path


def _points_gdf(crs="EPSG:4326"):
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3], "name": ["A", "B", "C"]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
        crs=crs,
    )
    return gdf


def _no_crs_gdf():
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3], "name": ["A", "B", "C"]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
    )
    # Explicitly ensure there is no CRS attached.
    return gdf.set_crs(None, allow_override=True)


@pytest.fixture
def clean_gpkg(tmp_path):
    """A valid, clean GeoPackage in EPSG:4326."""
    return _make_gpkg(tmp_path / "clean.gpkg", _points_gdf())


@pytest.fixture
def no_crs_gpkg(tmp_path):
    """A valid GeoPackage with no CRS assigned."""
    return _make_gpkg(tmp_path / "no_crs.gpkg", _no_crs_gdf())


def _epsg_of(path):
    """Return the EPSG integer of a written geospatial file."""
    gdf = gpd.read_file(path)
    assert gdf.crs is not None, f"expected a CRS on {path}"
    return gdf.crs.to_epsg()


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #

class TestValidate:
    def test_validate_clean_exit_zero(self, clean_gpkg):
        result = run_cli("validate", str(clean_gpkg))
        assert result.returncode == 0, result.stderr or result.stdout

    def test_validate_json_has_health_score(self, clean_gpkg):
        result = run_cli("validate", str(clean_gpkg), "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert "health_score" in data

    def test_validate_nonexistent_exit_one(self, tmp_path):
        missing = tmp_path / "does_not_exist.gpkg"
        result = run_cli("validate", str(missing))
        assert result.returncode == 1

    def test_validate_report_written(self, clean_gpkg, tmp_path):
        report_path = tmp_path / "report.txt"
        result = run_cli("validate", str(clean_gpkg), "--report", str(report_path))
        assert result.returncode == 0, result.stderr or result.stdout
        assert report_path.exists()
        assert report_path.stat().st_size > 0


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #

class TestInfo:
    def test_info_json_keys(self, clean_gpkg):
        result = run_cli("info", str(clean_gpkg), "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        for key in ("feature_count", "crs", "bounds"):
            assert key in data, f"missing key {key!r} in {sorted(data)}"

    def test_info_feature_count(self, clean_gpkg):
        result = run_cli("info", str(clean_gpkg), "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert data["feature_count"] == 3

    def test_info_infer_crs_suggestions(self, no_crs_gpkg):
        result = run_cli("info", str(no_crs_gpkg), "--infer-crs", "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert "crs_suggestions" in data
        assert isinstance(data["crs_suggestions"], list)
        assert len(data["crs_suggestions"]) > 0


# --------------------------------------------------------------------------- #
# fix
# --------------------------------------------------------------------------- #

class TestFix:
    def test_fix_basic_gpkg(self, clean_gpkg, tmp_path):
        out = tmp_path / "out.gpkg"
        result = run_cli("fix", str(clean_gpkg), "-o", str(out))
        assert result.returncode == 0, result.stderr or result.stdout
        assert out.exists()
        assert out.stat().st_size > 0

    def test_fix_format_infer_geojson(self, clean_gpkg, tmp_path):
        out = tmp_path / "out.geojson"
        result = run_cli("fix", str(clean_gpkg), "-o", str(out))
        assert result.returncode == 0, result.stderr or result.stdout
        assert out.exists()
        assert out.stat().st_size > 0

    def test_fix_reproject(self, clean_gpkg, tmp_path):
        out = tmp_path / "out.gpkg"
        result = run_cli(
            "fix", str(clean_gpkg), "-o", str(out), "--target-crs", "EPSG:3857"
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert out.exists()
        assert _epsg_of(out) == 3857

    def test_fix_assign_crs(self, no_crs_gpkg, tmp_path):
        out = tmp_path / "out.gpkg"
        result = run_cli(
            "fix", str(no_crs_gpkg), "-o", str(out), "--assign-crs", "EPSG:4326"
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert out.exists()
        assert _epsg_of(out) == 4326

    def test_fix_json_has_health_score(self, clean_gpkg, tmp_path):
        out = tmp_path / "out.gpkg"
        result = run_cli("fix", str(clean_gpkg), "-o", str(out), "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert "health_score" in data


# --------------------------------------------------------------------------- #
# batch
# --------------------------------------------------------------------------- #

class TestBatch:
    def _two_inputs(self, tmp_path):
        a = _make_gpkg(tmp_path / "a.gpkg", _points_gdf())
        b = _make_gpkg(tmp_path / "b.gpkg", _points_gdf())
        return a, b

    def test_batch_writes_two_files(self, tmp_path):
        a, b = self._two_inputs(tmp_path)
        outdir = tmp_path / "out"
        result = run_cli("batch", str(a), str(b), "-o", str(outdir))
        assert result.returncode == 0, result.stderr or result.stdout
        assert outdir.exists()
        written = [p for p in outdir.iterdir() if p.is_file()]
        assert len(written) == 2, [p.name for p in written]

    def test_batch_merge_single_file(self, tmp_path):
        a, b = self._two_inputs(tmp_path)
        outdir = tmp_path / "out_merge"
        result = run_cli("batch", str(a), str(b), "-o", str(outdir), "--merge")
        assert result.returncode == 0, result.stderr or result.stdout
        assert outdir.exists()
        written = sorted(p.name for p in outdir.iterdir() if p.is_file())
        assert written == ["merged.gpkg"], written

    def test_batch_format_geojson(self, tmp_path):
        a, b = self._two_inputs(tmp_path)
        outdir = tmp_path / "out_geojson"
        result = run_cli(
            "batch", str(a), str(b), "-o", str(outdir), "--format", "geojson"
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert outdir.exists()
        written = [p for p in outdir.iterdir() if p.is_file()]
        assert len(written) == 2, [p.name for p in written]
        assert all(p.suffix == ".geojson" for p in written), [p.name for p in written]


# --------------------------------------------------------------------------- #
# Phase 1 surfacing: profiles and multi-layer validation
# --------------------------------------------------------------------------- #

from shapely.geometry import box  # noqa: E402


def _polys_gdf(boxes, crs="EPSG:4326"):
    return gpd.GeoDataFrame(
        {"id": list(range(len(boxes)))},
        geometry=[box(*b) for b in boxes],
        crs=crs,
    )


class TestProfilesCLI:
    def test_validate_profile_adds_conformance(self, clean_gpkg):
        result = run_cli("validate", str(clean_gpkg), "--profile", "geopackage", "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert data["conformance"]["profile"] == "geopackage"

    def test_info_list_profiles(self):
        result = run_cli("info", "--list-profiles", "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        names = {p["name"] for p in json.loads(result.stdout)}
        assert names == {"rfc7946", "geopackage", "geoparquet"}

    def test_fail_on_nonconformance_exit_one(self, tmp_path):
        # A non-WGS84 GeoJSON is non-conformant to RFC 7946.
        path = tmp_path / "merc.geojson"
        _points_gdf(crs="EPSG:3857").to_file(path, driver="GeoJSON")
        result = run_cli(
            "validate", str(path), "--profile", "rfc7946", "--fail-on-nonconformance"
        )
        assert result.returncode == 1


class TestMultiLayerCLI:
    def test_must_not_overlap_via_against(self, tmp_path):
        a = tmp_path / "parcels.geojson"
        b = tmp_path / "roads.geojson"
        _polys_gdf([(0, 0, 2, 2)]).to_file(a, driver="GeoJSON")
        _polys_gdf([(1, 1, 3, 3)]).to_file(b, driver="GeoJSON")
        result = run_cli(
            "validate", str(a), "--against", str(b),
            "--must-not-overlap", "parcels:roads", "--json",
        )
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        overlaps = data["inter_layer"]["checks"]["must_not_overlap"]
        assert overlaps[0]["overlap_pair_count"] == 1

    def test_multilayer_gpkg_autodetected(self, tmp_path):
        path = tmp_path / "multi.gpkg"
        _polys_gdf([(0, 0, 1, 1)]).to_file(path, layer="parcels", driver="GPKG")
        _polys_gdf([(2, 2, 3, 3)]).to_file(path, layer="roads", driver="GPKG")
        result = run_cli("validate", str(path), "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert data["inter_layer"]["layer_count"] == 2


class TestConfigGatingCLI:
    def _overlap_gpkg(self, tmp_path):
        path = tmp_path / "overlap.gpkg"
        _polys_gdf([(0, 0, 2, 2), (1, 1, 3, 3)]).to_file(path, driver="GPKG")
        return path

    def test_no_config_overlap_exits_zero(self, tmp_path):
        # Legacy behaviour: soft findings do not gate without config/--strict.
        result = run_cli("validate", str(self._overlap_gpkg(tmp_path)))
        assert result.returncode == 0, result.stderr or result.stdout

    def test_strict_overlap_exits_one(self, tmp_path):
        result = run_cli("validate", str(self._overlap_gpkg(tmp_path)), "--strict")
        assert result.returncode == 1

    def test_config_severity_error_gates(self, tmp_path):
        cfg = tmp_path / "geolint.toml"
        cfg.write_text('[severity]\noverlapping_polygons = "error"\n', encoding="utf-8")
        result = run_cli(
            "validate", str(self._overlap_gpkg(tmp_path)), "--config", str(cfg)
        )
        assert result.returncode == 1

    def test_baseline_suppresses(self, tmp_path):
        gpkg = self._overlap_gpkg(tmp_path)
        base = tmp_path / "baseline.json"
        # Record the current findings...
        w = run_cli("validate", str(gpkg), "--strict", "--write-baseline", str(base))
        assert w.returncode == 0, w.stderr or w.stdout
        assert base.exists()
        # ...then they no longer gate.
        r = run_cli("validate", str(gpkg), "--strict", "--baseline", str(base))
        assert r.returncode == 0, r.stderr or r.stdout

    def test_write_baseline_fails_on_unloadable(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a real zip")
        base = tmp_path / "baseline.json"
        r = run_cli("validate", str(bad), "--write-baseline", str(base))
        assert r.returncode == 1  # a load failure must not silently write a baseline

    def test_contract_violation_gates(self, tmp_path):
        cfg = tmp_path / "geolint.toml"
        cfg.write_text(
            '[contract]\nrequired_columns = ["nonexistent_column"]\n', encoding="utf-8"
        )
        result = run_cli(
            "validate", str(self._overlap_gpkg(tmp_path)), "--config", str(cfg), "--json"
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert any(v["rule"] == "required_column" for v in data["contract"])


class TestCIOutputsCLI:
    def test_sarif_and_error_layer(self, tmp_path):
        gpkg = tmp_path / "overlap.gpkg"
        _polys_gdf([(0, 0, 2, 2), (1, 1, 3, 3)]).to_file(gpkg, driver="GPKG")
        sarif = tmp_path / "out.sarif"
        errlayer = tmp_path / "errors.geojson"
        result = run_cli(
            "validate", str(gpkg), "--sarif", str(sarif), "--error-layer", str(errlayer)
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert sarif.exists() and errlayer.exists()
        data = json.loads(sarif.read_text())
        assert data["version"] == "2.1.0"
        assert data["runs"][0]["tool"]["driver"]["name"] == "GeoLint"
