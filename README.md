# GeoLint

**GeoLint is the spatial equivalent of a code linter and auto-formatter for maps.**

A robust, open-source Python toolkit to systematically detect, validate, repair, and standardize geospatial vector datasets with an intuitive web interface.

## Features

### 🔍 **Validation Engine**
- File integrity checks (shapefile bundles, format validation)
- Geometry validity analysis
- Mixed geometry type detection
- Coordinate Reference System (CRS) presence verification

### ✅ **Data Quality Checks**
- **Topology**: duplicate geometries, overlapping polygons, slivers / zero-area geometries, duplicate vertices, coverage gaps, line dangles, self-intersecting lines, pseudo-nodes
- **Attributes**: ID uniqueness, null fields, shapefile-unsafe field names
- **Spec compliance**: GeoJSON winding order, out-of-range coordinates

### 🧩 **Inter-Layer & Coverage Checks**
- Coverage gaps (enclosed slivers/holes between adjacent polygons)
- Line-network topology: dangles, self-intersections, pseudo-nodes
- Cross-layer rules: must-not-overlap and must-be-covered-by between two layers
- Multi-layer GeoPackage support with CRS alignment (`error` or `align` policy)

### 📐 **Spec Conformance Profiles**
- **RFC 7946** (GeoJSON): WGS84 CRS, right-hand winding, coordinate range, supported geometry types, antimeridian
- **GeoPackage**: container validity, `gpkg_contents`/SRS tables, `geometry_type_name`, R-tree index
- **GeoParquet 1.1**: `geo` file metadata, version, primary column, column encodings, CRS PROJJSON
- CI-friendly: `--fail-on-nonconformance` exits non-zero when an error-severity check fails

### ⚙️ **Config-as-Code, Contracts & Severity**
- `geolint.toml` / `.geolint.yml`: per-check **severity** (error/warning/info/off), thresholds, scoping
- **Data contracts**: required columns, dtypes, expected geometry type / CRS / bounds, and per-column rules (not-null, unique, range, enum, regex)
- Severity-driven **exit codes** (`--strict`) and a **baseline file** for incremental adoption on messy data

### 🚦 **CI-Native Distribution**
- **SARIF 2.1.0** output (`--sarif`) → GitHub code-scanning annotations on PRs
- **GeoJSON error layer** (`--error-layer`) → open flagged features straight in QGIS
- A **pre-commit hook** (`geolint-precommit`) and a reusable **GitHub Action** (`action.yml`)

### ☁️ **Cloud-Native Scale**
- Read **remote** inputs directly: `s3://`, `gs://`, `https://` (via GDAL `/vsi` and pyarrow)
- Optional **DuckDB** backend (`info --fast`) for quick count/bbox over large GeoParquet without loading it all

### 🗺️ **CRS Management**
- Automatic CRS detection and inference
- Interactive CRS selection with confidence scoring
- Popular CRS quick-select (WGS84, Web Mercator, UTM zones)
- Bounds preview before/after reprojection

### 🔧 **Auto-Repair**
- Fix invalid geometries using `shapely.make_valid`
- Remove empty geometries
- Explode multipart geometries (optional)
- Normalize polygon winding order to the RFC 7946 right-hand rule
- Remove duplicate geometries and duplicate/collinear vertices
- Reproject to target CRS

### 📊 **Batch Processing**
- Multi-file upload and processing
- Unified CRS strategy selection
- Merge multiple datasets into single file
- Aggregate validation reports

### 🌐 **Modern Web Interface**
- Clean, responsive Streamlit UI
- Drag-and-drop file upload
- Real-time validation dashboard
- Interactive charts and maps
- Download cleaned files in multiple formats

## Quick Start

### Installation

To run from source, install the dependencies:

```bash
pip install -r requirements.txt
```

To install the package itself (this puts the `geolint` command on your PATH), run from the repo root:

```bash
pip install .          # regular install
pip install -e .       # editable/development install
```

### Run the Web App

```bash
streamlit run geolint/web/app.py
```

Open your browser to `http://localhost:8501`

### Command Line Usage

After installation, the `geolint` command exposes the full toolkit:

#### `geolint validate <input> [--json] [--report PATH]`

Validate only — runs the full check suite and reports problems without modifying any data. Exits non-zero when hard errors are found (warnings alone still exit 0), making it suitable for CI pipelines. Use `--json` for a machine-readable report on stdout and `--report PATH` to write the report to a file.

**Spec conformance:**

- `--profile {rfc7946,geopackage,geoparquet}` — check conformance against a target spec; results appear under the `conformance` key
- `--fail-on-nonconformance` — exit non-zero when an error-severity profile check fails (CI gate)

**Inter-layer & multi-layer** (any of these switches to multi-layer mode; a multi-layer GeoPackage is auto-detected):

- `--layer NAME` — select a GeoPackage layer (repeatable)
- `--against PATH` — additional layer/file for cross-layer checks (repeatable)
- `--must-not-overlap A:B` — assert layer A does not overlap layer B (repeatable)
- `--must-be-covered-by A:B` — assert layer A is fully covered by layer B (repeatable)
- `--coverage-gaps LAYER` / `--coverage-gaps-all` — check layer(s) for coverage gaps
- `--crs-policy {error,align}` — how to handle differing CRS across layers (default `error`)
- `--target-crs EPSG:XXXX` — target CRS for `--crs-policy align`
- `--force` — run checks past the feature-count safety caps

#### `geolint info <input> [--json] [--infer-crs]`

Print CRS information, bounds, and geometry types for a dataset. With `--infer-crs`, GeoLint suggests a likely CRS when none is set. `--json` emits the info as JSON. Use `--list-profiles` (no input needed) to list the available conformance profiles.

#### `geolint fix <input> -o OUTPUT [options]`

Repair, reproject, and export a single file. Options:

- `-f, --format {gpkg,geojson,shp,parquet}` — output format
- `--assign-crs EPSG:XXXX` — set the CRS without reprojecting (use when the data has no CRS)
- `--target-crs EPSG:XXXX` — reproject to the given CRS
- `--no-fix-invalid` — skip invalid-geometry repair
- `--no-remove-empty` — keep empty geometries
- `--remove-duplicates` — drop duplicate geometries
- `--clean-vertices` — remove duplicate/collinear vertices
- `--normalize-winding` — normalize polygon winding to the RFC 7946 right-hand rule
- `--explode-multipart` — split multipart geometries into single parts
- `--simplify TOL` — simplify geometries with the given tolerance
- `--report PATH` — write the operation report to a file
- `--json` — print a machine-readable JSON report

#### `geolint batch <inputs...> -o OUTDIR [options]`

Validate, repair, and reproject many files at once, writing the results to `OUTDIR`. Options:

- `--no-unify-crs` — do not unify the CRS across inputs
- `--target-crs EPSG:XXXX` — target CRS for unification/reprojection
- `--crs-strategy {manual,use_most_common,auto_detect}` — how to choose the unified CRS
- `--no-fix-geometries` — skip geometry repair
- `--merge` — write a single merged file instead of one per input
- `-f, --format {gpkg,geojson,shp,parquet}` — output format
- `--report PATH` — write an aggregate report to a file

#### `geolint web`

Launch the Streamlit web UI.

#### Examples

```bash
# Validate a file in CI (exits non-zero on hard errors)
geolint validate path/to/data.gpkg --json

# Inspect a dataset and suggest a CRS when none is set
geolint info path/to/data.shp.zip --infer-crs

# Repair, reproject, and simplify a single file
geolint fix data.shp.zip -o clean.gpkg --target-crs EPSG:4326 --simplify 0.001

# Assign a CRS to data that has none, then export to GeoJSON
geolint fix points.csv -o points.geojson -f geojson --assign-crs EPSG:4326

# Batch process several files into one merged GeoPackage
geolint batch a.geojson b.gpkg -o out/ --merge -f gpkg

# Check GeoJSON RFC 7946 conformance and fail CI if non-conformant
geolint validate data.geojson --profile rfc7946 --fail-on-nonconformance

# Inter-layer checks across two files
geolint validate parcels.geojson --against roads.geojson \
    --must-not-overlap parcels:roads --json

# Multi-layer GeoPackage: coverage gaps + containment rule
geolint validate city.gpkg --coverage-gaps-all \
    --must-be-covered-by buildings:parcels

# List available conformance profiles
geolint info --list-profiles

# Launch the web UI from the CLI
geolint web
```

### Configuration, CI gating & cloud inputs

Declare a `geolint.toml` (or `.geolint.yml`) in your project root to turn GeoLint into a real gate (see `examples/geolint.toml`):

```toml
[severity]                      # error | warning | info | off
overlapping_polygons = "error"
pseudo_nodes = "off"

[thresholds]
gap_area_tol = 0.0

[contract]                      # data contract: what the dataset must look like
required_columns = ["id", "name"]
geometry_type = "Polygon"
crs = "EPSG:4326"

[[contract.columns]]
name = "id"
not_null = true
unique = true
```

```bash
# Gate CI on a config (error-severity findings -> exit 1); treat warnings as errors with --strict
geolint validate parcels.gpkg --config geolint.toml
geolint validate parcels.gpkg --strict

# Adopt incrementally on messy data: snapshot current findings, then suppress them
geolint validate parcels.gpkg --strict --write-baseline .geolint-baseline.json
geolint validate parcels.gpkg --strict --baseline .geolint-baseline.json

# Emit SARIF for GitHub code scanning, and a GeoJSON layer of the offending features
geolint validate parcels.gpkg --strict --sarif geolint.sarif --error-layer errors.geojson

# Read remote data, or get a fast count/bbox of huge GeoParquet via DuckDB
geolint validate s3://bucket/parcels.parquet --profile geoparquet
geolint info s3://bucket/huge.parquet --fast
```

GeoLint ships a **pre-commit hook** (`.pre-commit-hooks.yaml`) and a reusable **GitHub Action** (`action.yml`); see `examples/github-workflow.yml` for a ready-to-copy workflow that uploads SARIF.

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/CONFUZ3/geolint
  rev: v0.2.0
  hooks:
    - id: geolint
      args: [--strict]
```

## Interactive Mode

For exploratory work, GeoLint ships an interactive REPL and a guided wizard so you can load a dataset once and iterate on it without re-running the CLI.

### REPL Shell

```bash
geolint            # no args -> opens the REPL
geolint shell      # same thing, explicitly
geolint shell data.gpkg   # preload a file on startup
```

Both forms open a persistent shell with a `geolint>` prompt. Command history and tab-completion are available. The following commands are supported inside the shell:

- `load <path>` — load a dataset into the session
- `info` — print CRS, bounds, and geometry types
- `check` (alias `validate`) — run the full validation suite
- `infer-crs` — suggest a likely CRS when none is set
- `assign-crs <crs>` — set the CRS without reprojecting (e.g. `assign-crs EPSG:4326`)
- `reproject <crs>` — reproject the loaded dataset to the given CRS
- `fix [--no-fix-invalid] [--no-remove-empty] [--remove-duplicates] [--clean-vertices] [--normalize-winding] [--explode-multipart] [--simplify TOL]` — repair geometries in place
- `save <path> [--format FMT]` — export the current dataset
- `reset` — discard changes and restore the originally loaded dataset
- `status` — show what is currently loaded and any pending changes
- `health` — quick health summary of the current dataset
- `/help` — list available commands
- `/quit` — exit the shell

The REPL is also scriptable — pipe a list of commands to it:

```bash
printf 'load x.gpkg\ncheck\nquit\n' | geolint shell
```

### Guided Wizard

```bash
geolint wizard           # start the wizard
geolint wizard data.gpkg # preload a file
```

The wizard walks you through a step-by-step flow: load a file -> validate it -> choose a CRS -> choose which fixes to apply -> export the result.

## Supported Formats

- **Input**: Shapefile (.zip), GeoPackage (.gpkg), GeoJSON (.geojson), KML (.kml), CSV with lat/lon columns (.csv), GeoParquet (.parquet)
- **Output**: GeoPackage (.gpkg), GeoJSON (.geojson), Shapefile (.zip)

## Usage

### Single File Mode
1. Upload a geospatial file
2. Review validation results and CRS information
3. Select target CRS and fix options
4. Click "AutoFix" to process
5. Download cleaned file and report

### Batch Processing Mode
1. Upload multiple files
2. Choose unified CRS strategy
3. Run batch validation and operations
4. Download all cleaned files or merged dataset

## Architecture

```
geolint/
├── geolint/
│   ├── core/           # Core validation and processing engine
│   │   ├── validation.py
│   │   ├── checks.py    # Topology, attribute & spec quality checks
│   │   ├── crs.py
│   │   ├── geometry.py
│   │   ├── transform.py
│   │   ├── batch.py
│   │   └── report.py
│   ├── cli/            # Command-line interface
│   │   └── main.py
│   └── web/            # Streamlit web interface
│       ├── app.py
│       ├── components.py
│       └── styles.css
├── tests/              # Comprehensive test suite
└── requirements.txt
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black geolint/
isort geolint/
```

