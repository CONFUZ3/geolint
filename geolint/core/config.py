"""
Configuration loading for GeoLint (the config-as-code layer).

A project may declare a ``geolint.toml`` (or ``.geolint.toml`` / ``.geolint.yml``)
that selects per-check severities, thresholds, and a data contract. This turns
GeoLint from a reporter into a linter: error-severity findings can gate CI.

TOML is parsed with the stdlib ``tomllib`` (Python 3.11+) or ``tomli``; YAML is
supported when ``PyYAML`` is installed.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    try:
        import tomli as _toml
    except ModuleNotFoundError:
        _toml = None


# Built-in default severity per check id. Severity is one of:
# 'error' | 'warning' | 'info' | 'off'.
DEFAULT_SEVERITIES: Dict[str, str] = {
    # geometry validity
    'invalid_geometries': 'error',
    'null_geometries': 'error',
    'empty_geometries': 'warning',
    'mixed_types': 'warning',
    'crs_missing': 'error',
    # topology
    'duplicate_geometries': 'warning',
    'overlapping_polygons': 'warning',
    'slivers': 'warning',
    'duplicate_vertices': 'info',
    'coverage_gaps': 'warning',
    'line_dangles': 'warning',
    'self_intersections': 'warning',
    'pseudo_nodes': 'info',
    # attributes
    'id_uniqueness': 'error',
    'null_attributes': 'info',
    'shapefile_field_names': 'warning',
    # coordinates / spec
    'winding_order': 'warning',
    'coordinate_range': 'error',
    # data contract violations (single bucket)
    'contract': 'error',
    # conformance profile failures
    'conformance': 'error',
}

_VALID_SEVERITIES = {'error', 'warning', 'info', 'off'}

_CONFIG_FILENAMES = (
    'geolint.toml', '.geolint.toml',
    'geolint.yml', '.geolint.yml',
    'geolint.yaml', '.geolint.yaml',
)


@dataclass
class Config:
    """Resolved GeoLint configuration."""
    severities: Dict[str, str] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)
    contract: Optional[Dict] = None
    source: Optional[str] = None

    def severity(self, check_id: str) -> str:
        """Return the configured severity for a check id (built-in default otherwise)."""
        return self.severities.get(check_id, DEFAULT_SEVERITIES.get(check_id, 'warning'))

    def threshold(self, name: str, default):
        """Return a configured numeric threshold or the supplied default."""
        return self.thresholds.get(name, default)


def default_config() -> Config:
    """A Config with built-in defaults and no contract."""
    return Config(severities=dict(DEFAULT_SEVERITIES), thresholds={}, contract=None)


def _parse_file(path: Path) -> Dict:
    suffix = path.suffix.lower()
    if suffix in ('.yml', '.yaml'):
        try:
            import yaml
        except ModuleNotFoundError as e:  # pragma: no cover
            raise RuntimeError(
                "YAML config requires PyYAML (pip install pyyaml), or use TOML"
            ) from e
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    # TOML
    if _toml is None:  # pragma: no cover
        raise RuntimeError("TOML config requires Python 3.11+ or the 'tomli' package")
    with open(path, 'rb') as f:
        return _toml.load(f)


def _build_config(data: Dict, source: Optional[str]) -> Config:
    # Allow either top-level keys or a [geolint] table wrapper.
    if 'geolint' in data and isinstance(data['geolint'], dict):
        data = data['geolint']

    severities = dict(DEFAULT_SEVERITIES)
    for key, value in (data.get('severity') or {}).items():
        sev = str(value).lower()
        if sev not in _VALID_SEVERITIES:
            raise ValueError(
                f"invalid severity '{value}' for '{key}' "
                f"(expected one of {sorted(_VALID_SEVERITIES)})"
            )
        severities[key] = sev

    thresholds = dict(data.get('thresholds') or {})
    contract = data.get('contract')

    return Config(
        severities=severities,
        thresholds=thresholds,
        contract=contract,
        source=source,
    )


def discover_config_path(start: Optional[Path] = None) -> Optional[Path]:
    """
    Find a config file next to ``start`` (a file or directory) or the cwd.

    Searches the directory containing ``start`` (or ``start`` itself if it is a
    directory) for the known config filenames.
    """
    base = Path(start) if start is not None else Path.cwd()
    directory = base if base.is_dir() else base.parent
    for name in _CONFIG_FILENAMES:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def load_config(source: Optional[Path] = None, *, discover_from: Optional[Path] = None) -> Config:
    """
    Load a Config.

    Args:
        source: Explicit path to a config file. When given, it must exist.
        discover_from: A file/dir to search near when ``source`` is None. If no
            config file is found, the built-in defaults are returned.

    Returns:
        A resolved Config (built-in defaults merged with any file overrides).
    """
    if source is not None:
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"config not found: {source}")
        return _build_config(_parse_file(source), str(source))

    found = discover_config_path(discover_from)
    if found is None:
        return default_config()
    return _build_config(_parse_file(found), str(found))
