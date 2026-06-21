"""
Core validation and processing engine for GeoLint.
"""

from .validation import load_dataset, run_validation
from .crs import get_crs_info, infer_crs, get_popular_crs
from .geometry import (
    fix_geometries,
    remove_empty_geometries,
    normalize_winding,
    remove_duplicate_geometries,
    remove_duplicate_vertices,
)
from .transform import reproject_dataset, get_transform_preview, detect_common_crs
from .batch import BatchProcessor
from .report import generate_report, generate_batch_report
from .checks import run_checks

__all__ = [
    "load_dataset",
    "run_validation",
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
    "BatchProcessor",
    "generate_report",
    "generate_batch_report",
    "run_checks",
]
