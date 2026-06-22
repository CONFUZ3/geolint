"""
Core validation and processing engine for GeoLint.
"""

from .validation import (
    load_dataset,
    load_layers,
    list_layers,
    run_validation,
    run_multilayer_validation,
)
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
    "save_dataset",
    "resolve_format",
    "FORMAT_EXTENSIONS",
]
