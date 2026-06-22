"""
Tests for GeoLint interactive mode: the session spine and the REPL dispatch.

The REPL's ``handle_line`` is pure (no terminal I/O), so it is driven directly
here; one subprocess test exercises the full piped shell end-to-end.
"""

import subprocess
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from geolint.interactive import repl
from geolint.interactive.session import GeoLintSession, SessionError

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_gpkg(path: Path, crs="EPSG:4326") -> Path:
    """Write a 2-feature GeoPackage; the first polygon is an invalid bowtie."""
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])  # self-intersecting
    clean = Polygon([(2, 2), (2, 3), (3, 3), (3, 2)])
    gdf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[bowtie, clean])
    if crs is not None:
        gdf = gdf.set_crs(crs)
    gdf.to_file(path, driver="GPKG")
    return path


class TestSession:
    def test_load_sets_state_and_summary(self, tmp_path):
        session = GeoLintSession()
        assert session.loaded is False
        summary = session.load(_make_gpkg(tmp_path / "a.gpkg"))
        assert session.loaded is True
        assert summary["feature_count"] == 2
        assert summary["epsg"] == 4326
        assert summary["health_score"] is not None

    def test_load_missing_file_raises(self):
        with pytest.raises(SessionError):
            GeoLintSession().load("definitely_missing.gpkg")

    def test_operations_before_load_raise(self):
        session = GeoLintSession()
        with pytest.raises(SessionError):
            session.info()

    def test_fix_does_not_lower_health(self, tmp_path):
        session = GeoLintSession()
        session.load(_make_gpkg(tmp_path / "a.gpkg"))
        before = session.health_score()
        session.fix(fix_invalid=True, remove_empty=True, normalize_winding_order=True)
        assert session.health_score() >= before

    def test_reproject_changes_crs(self, tmp_path):
        session = GeoLintSession()
        session.load(_make_gpkg(tmp_path / "a.gpkg"))
        report = session.reproject("EPSG:3857")
        assert report["target_crs"]["epsg"] == 3857
        assert session.gdf.crs.to_epsg() == 3857

    def test_save_and_reset(self, tmp_path):
        session = GeoLintSession()
        session.load(_make_gpkg(tmp_path / "a.gpkg"))
        session.reproject("EPSG:3857")
        out = session.save(tmp_path / "out.gpkg")
        assert out.exists()
        session.reset()
        assert session.gdf.crs.to_epsg() == 4326

    def test_assign_crs_and_infer_on_no_crs(self, tmp_path):
        session = GeoLintSession()
        session.load(_make_gpkg(tmp_path / "nocrs.gpkg", crs=None))
        if session.gdf.crs is None:  # depends on driver round-trip
            assert len(session.infer_crs()) > 0
            with pytest.raises(SessionError):
                session.reproject("EPSG:3857")
            session.assign_crs("EPSG:4326")
            assert session.gdf.crs.to_epsg() == 4326


class TestReplDispatch:
    def test_quit_aliases_return_false(self):
        session = GeoLintSession()
        assert repl.handle_line(session, "/quit") is False
        assert repl.handle_line(session, "exit") is False

    def test_empty_and_unknown_keep_loop(self):
        session = GeoLintSession()
        assert repl.handle_line(session, "   ") is True
        assert repl.handle_line(session, "frobnicate") is True

    def test_command_before_load_does_not_crash(self):
        session = GeoLintSession()
        assert repl.handle_line(session, "info") is True
        assert repl.handle_line(session, "reproject EPSG:3857") is True

    def test_full_pipeline_via_dispatch(self, tmp_path):
        # Paths are quoted because the temp dir can contain spaces.
        path = _make_gpkg(tmp_path / "a.gpkg")
        session = GeoLintSession()
        assert repl.handle_line(session, f'load "{path}"') is True
        assert session.loaded is True
        assert repl.handle_line(session, "info") is True
        assert repl.handle_line(session, "check") is True
        assert repl.handle_line(session, "fix --normalize-winding") is True
        assert repl.handle_line(session, "reproject EPSG:3857") is True
        assert session.gdf.crs.to_epsg() == 3857
        out = tmp_path / "o.gpkg"
        assert repl.handle_line(session, f'save "{out}"') is True
        assert out.exists()

    def test_bad_fix_flag_keeps_loop(self, tmp_path):
        session = GeoLintSession()
        repl.handle_line(session, f'load "{_make_gpkg(tmp_path / "a.gpkg")}"')
        assert repl.handle_line(session, "fix --bogus") is True

    def test_quoted_path_with_spaces(self, tmp_path):
        target = tmp_path / "a folder"
        target.mkdir()
        path = _make_gpkg(target / "a.gpkg")
        session = GeoLintSession()
        assert repl.handle_line(session, f'load "{path}"') is True
        assert session.loaded is True


class TestReplSubprocess:
    def test_piped_shell_session(self, tmp_path):
        path = _make_gpkg(tmp_path / "a.gpkg")
        out = tmp_path / "out.gpkg"
        script = f'load "{path}"\ncheck\nfix\nsave "{out}"\nquit\n'
        result = subprocess.run(
            [sys.executable, "-m", "geolint.cli.main", "shell"],
            input=script,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        assert out.exists()
