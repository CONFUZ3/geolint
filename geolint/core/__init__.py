"""
Core validation and processing engine for GeoLint.
"""

from .validation import (
    load_dataset,
    load_layers,
    list_layers,
    run_validation,
    run_multilayer_validation,
    is_remote,
    to_vsi_path,
)
from .duckdb_backend import duckdb_available, quick_stats, can_handle
from .crs import get_crs_info, infer_crs, get_popular_crs
from .geometry import (
    fix_geometries,
    remove_empty_geometries,
    normalize_winding,
    remove_duplicate_geometries,
    remove_duplicate_vertices,
)
from .transform import (
    reproject_dataset,
    get_transform_preview,
    detect_common_crs,
    align_layers_crs,
)
from .batch import BatchProcessor
from .report import generate_report, generate_batch_report, generate_multilayer_report
from .checks import run_checks, run_multilayer_checks
from .profiles import run_profile, list_profiles, PROFILE_NAMES
from .config import Config, load_config, default_config, DEFAULT_SEVERITIES
from .contracts import check_schema_contract
from .findings import (
    collect_findings,
    summarize,
    exit_code,
    load_baseline,
    write_baseline,
    apply_baseline,
)
from .sarif import to_sarif
from .error_layer import write_error_layer, flagged_index_map
from .io import save_dataset, resolve_format, FORMAT_EXTENSIONS

__all__ = [
    "load_dataset",
    "load_layers",
    "list_layers",
    "run_validation",
    "run_multilayer_validation",
    "get_crs_info",
    "infer_crs",
    "get_popular_crs",
    "fix_geometries",
    "remove_empty_geometries",
    "normalize_winding",
    "remove_duplicate_geometries",
    "remove_duplicate_vertices",
    "reproject_dataset",
    "get_transform_preview",
    "detect_common_crs",
    "align_layers_crs",
    "BatchProcessor",
    "generate_report",
    "generate_batch_report",
    "generate_multilayer_report",
    "run_checks",
    "run_multilayer_checks",
    "run_profile",
    "list_profiles",
    "PROFILE_NAMES",
    "Config",
    "load_config",
    "default_config",
    "DEFAULT_SEVERITIES",
    "check_schema_contract",
    "collect_findings",
    "summarize",
    "exit_code",
    "load_baseline",
    "write_baseline",
    "apply_baseline",
    "to_sarif",
    "write_error_layer",
    "flagged_index_map",
    "is_remote",
    "to_vsi_path",
    "duckdb_available",
    "quick_stats",
    "can_handle",
    "save_dataset",
    "resolve_format",
    "FORMAT_EXTENSIONS",
]
