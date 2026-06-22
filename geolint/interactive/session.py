"""
Stateful session for GeoLint interactive mode (REPL and wizard).

Wraps the core engine around a single working dataset, tracking the loaded
GeoDataFrame, an original snapshot for ``reset``, the latest validation
report, and a history of applied operations. Every method is UI-agnostic and
returns plain data (or raises :class:`SessionError`), so the REPL and the
wizard can render results however they like.
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import geopandas as gpd

from geolint.core.crs import get_crs_info, infer_crs
from geolint.core.geometry import process_geometries
from geolint.core.io import save_dataset
from geolint.core.report import generate_report
from geolint.core.transform import reproject_dataset
from geolint.core.validation import run_validation


class SessionError(Exception):
    """Raised for expected, user-facing errors (no dataset loaded, bad CRS, ...)."""


# Map process_geometries keyword args to short, human-readable labels.
_FIX_LABELS = {
    "fix_invalid": "fix-invalid",
    "remove_empty": "remove-empty",
    "remove_duplicates": "remove-duplicates",
    "clean_vertices": "clean-vertices",
    "normalize_winding_order": "normalize-winding",
    "do_explode_multipart": "explode-multipart",
    "simplify": "simplify",
}


def _format_fix_opts(opts: Dict[str, Any]) -> str:
    """Render the active geometry-fix options as a compact label string."""
    labels = [label for key, label in _FIX_LABELS.items() if opts.get(key)]
    return ", ".join(labels) if labels else "(no-op)"


class GeoLintSession:
    """Holds the working dataset and exposes engine operations as methods."""

    def __init__(self) -> None:
        self.gdf: Optional[gpd.GeoDataFrame] = None
        self.original_gdf: Optional[gpd.GeoDataFrame] = None
        self.source_path: Optional[Path] = None
        self.report: Optional[Dict[str, Any]] = None
        self.operations: List[str] = []

    @property
    def loaded(self) -> bool:
        """True once a dataset has been loaded."""
        return self.gdf is not None

    def _require_loaded(self) -> None:
        if not self.loaded:
            raise SessionError("No dataset loaded. Use 'load <path>' first.")

    # ------------------------------------------------------------------ load
    def load(self, path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load and validate a dataset, replacing any current state.

        Returns a :meth:`summary` dict. Raises SessionError if the file is
        missing or could not be read.
        """
        path = Path(path)
        if not path.exists():
            raise SessionError(f"File not found: {path}")

        report, gdf = run_validation(path)
        if gdf.empty and report.get("errors"):
            raise SessionError(report["errors"][0])

        self.gdf = gdf
        self.original_gdf = gdf.copy()
        self.source_path = path
        self.report = report
        self.operations = []
        return self.summary()

    # ------------------------------------------------------------ inspection
    def info(self) -> Dict[str, Any]:
        """Return structural facts about the current dataset."""
        self._require_loaded()
        gdf = self.gdf
        geometry_types = (
            sorted(set(gdf.geom_type.dropna().unique())) if not gdf.empty else []
        )
        return {
            "source": str(self.source_path) if self.source_path else None,
            "feature_count": len(gdf),
            "column_count": len(gdf.columns),
            "columns": [c for c in gdf.columns if c != "geometry"],
            "geometry_types": geometry_types,
            "bounds": list(gdf.total_bounds) if not gdf.empty else None,
            "crs": get_crs_info(gdf),
        }

    def validate(self) -> Dict[str, Any]:
        """Re-validate the *current* working dataset and return the full report."""
        self._require_loaded()
        self._revalidate()
        return self.full_report()

    def infer_crs(self) -> List[Dict[str, Any]]:
        """Suggest a CRS for the dataset (empty list if a CRS is already set)."""
        self._require_loaded()
        return infer_crs(self.gdf)

    # ------------------------------------------------------------- mutations
    def assign_crs(self, crs: str) -> None:
        """Assign a CRS without reprojecting coordinates."""
        self._require_loaded()
        try:
            self.gdf = self.gdf.set_crs(crs, allow_override=True)
        except Exception as exc:
            raise SessionError(f"Could not assign CRS '{crs}': {exc}")
        self.operations.append(f"assign-crs {crs}")
        self._revalidate()

    def reproject(self, crs: str) -> Dict[str, Any]:
        """Reproject the dataset to ``crs``; returns the transform report."""
        self._require_loaded()
        if self.gdf.crs is None:
            raise SessionError("Dataset has no CRS. Use 'assign-crs <crs>' first.")
        gdf, transform_report = reproject_dataset(self.gdf, crs)
        if transform_report.get("transformed") is False:
            raise SessionError(
                f"Reprojection failed: {transform_report.get('error')}"
            )
        self.gdf = gdf
        self.operations.append(f"reproject {crs}")
        self._revalidate()
        return transform_report

    def fix(self, **opts: Any) -> Dict[str, Any]:
        """
        Run geometry processing on the current dataset.

        Accepts the same keyword arguments as
        :func:`geolint.core.geometry.process_geometries`. Returns the geometry
        report.
        """
        self._require_loaded()
        gdf, geom_report = process_geometries(self.gdf, **opts)
        self.gdf = gdf
        self.operations.append("fix " + _format_fix_opts(opts))
        self._revalidate()
        return geom_report

    def save(self, path: Union[str, Path], fmt: Optional[str] = None) -> Path:
        """Write the current dataset to ``path``; returns the path written."""
        self._require_loaded()
        if self.gdf.empty:
            raise SessionError("Nothing to save: dataset is empty.")
        out = save_dataset(self.gdf, path, fmt)
        self.operations.append(f"save {out}")
        return out

    def reset(self) -> None:
        """Revert the working dataset to the originally loaded version."""
        if self.original_gdf is None:
            raise SessionError("No dataset loaded to reset.")
        self.gdf = self.original_gdf.copy()
        self.operations.append("reset")
        self._revalidate()

    # ------------------------------------------------------------- reporting
    def summary(self) -> Dict[str, Any]:
        """Compact one-glance state used after load and by ``status``."""
        self._require_loaded()
        crs = get_crs_info(self.gdf)
        return {
            "source": str(self.source_path) if self.source_path else None,
            "feature_count": len(self.gdf),
            "crs": crs.get("crs"),
            "epsg": crs.get("epsg"),
            "health_score": self.health_score(),
            "operations": list(self.operations),
        }

    def full_report(self) -> Dict[str, Any]:
        """The comprehensive JSON report for the current dataset."""
        self._require_loaded()
        crs_info = get_crs_info(self.gdf) if self.gdf.crs is not None else None
        return generate_report(self.report or {}, crs_info=crs_info)

    def health_score(self) -> Optional[float]:
        """Health score (0-100) for the current dataset, or None if unloaded."""
        if not self.loaded or self.report is None:
            return None
        crs_info = get_crs_info(self.gdf) if self.gdf.crs is not None else None
        return generate_report(self.report, crs_info=crs_info).get("health_score")

    # ------------------------------------------------------------- internals
    def _revalidate(self) -> None:
        """
        Refresh ``self.report`` from the current in-memory dataset.

        The dataset is written to a temporary GeoPackage and re-run through
        :func:`run_validation` so the report (and therefore the health score)
        reflects edits applied this session. On any failure the previous
        report is kept.
        """
        if self.gdf is None or self.gdf.empty:
            return
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir) / "current.gpkg"
                self.gdf.to_file(tmp_path, driver="GPKG")
                report, _ = run_validation(tmp_path)
            self.report = report
        except Exception:
            # Keep the previous report if revalidation fails (e.g. odd geometry).
            pass
