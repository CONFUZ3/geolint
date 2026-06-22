"""
Dataset writing helpers for GeoLint.

Resolves output formats and saves GeoDataFrames to disk in the
supported formats (GeoPackage, GeoJSON, zipped Shapefile, Parquet).
"""

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Union

import geopandas as gpd

SUPPORTED_OUTPUT_FORMATS = {"gpkg", "geojson", "shp", "parquet"}
FORMAT_EXTENSIONS = {
    "gpkg": ".gpkg",
    "geojson": ".geojson",
    "shp": ".zip",
    "parquet": ".parquet",
}

# Aliases accepted when a format is given explicitly.
_FORMAT_ALIASES = {
    "shapefile": "shp",
    "zip": "shp",
    "json": "geojson",
}

# Mapping from file suffix to canonical format.
_SUFFIX_FORMATS = {
    ".gpkg": "gpkg",
    ".geojson": "geojson",
    ".json": "geojson",
    ".zip": "shp",
    ".shp": "shp",
    ".parquet": "parquet",
}


def resolve_format(output_path: Union[str, Path], fmt: Optional[str] = None) -> str:
    """
    Resolve the canonical output format for a dataset.

    Args:
        output_path: Destination path used to infer the format when ``fmt``
            is not provided.
        fmt: Optional explicit format. Accepts canonical names and aliases
            ("shapefile"/"zip" -> "shp", "json" -> "geojson").

    Returns:
        The canonical format string (one of SUPPORTED_OUTPUT_FORMATS).

    Raises:
        ValueError: If an explicit ``fmt`` is not a supported format.
    """
    if fmt is not None:
        fmt = fmt.lower()
        fmt = _FORMAT_ALIASES.get(fmt, fmt)
        if fmt not in SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(f"Unsupported output format: {fmt}")
        return fmt

    suffix = Path(output_path).suffix.lower()
    return _SUFFIX_FORMATS.get(suffix, "gpkg")


def save_dataset(
    gdf: gpd.GeoDataFrame,
    output_path: Union[str, Path],
    fmt: Optional[str] = None,
) -> Path:
    """
    Save a GeoDataFrame to disk in the resolved format.

    Args:
        gdf: GeoDataFrame to write. Must not be empty.
        output_path: Destination path (str or Path).
        fmt: Optional explicit format override (see ``resolve_format``).

    Returns:
        The Path actually written. For the "shp" format this is the ``.zip``
        path containing the shapefile and its sidecar files.

    Raises:
        ValueError: If ``gdf`` is empty or the format cannot be resolved.
    """
    if gdf.empty:
        raise ValueError("Cannot save an empty dataset")

    fmt = resolve_format(output_path, fmt)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "gpkg":
        gdf.to_file(output_path, driver="GPKG")
        return output_path

    if fmt == "geojson":
        gdf.to_file(output_path, driver="GeoJSON")
        return output_path

    if fmt == "parquet":
        gdf.to_parquet(output_path)
        return output_path

    # fmt == "shp": produce a zipped shapefile.
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        shapefile_path = Path(temp_dir) / "data.shp"
        gdf.to_file(shapefile_path, driver="ESRI Shapefile")

        with zipfile.ZipFile(output_path, "w") as zipf:
            for file in os.listdir(temp_dir):
                zipf.write(os.path.join(temp_dir, file), file)

    return output_path
