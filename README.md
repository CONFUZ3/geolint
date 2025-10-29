# GeoLint

**GeoLint is the spatial equivalent of a code linter and auto-formatter for maps.**

A robust, open-source Python toolkit to systematically detect, validate, repair, and standardize geospatial vector datasets with an intuitive web interface.

## Features

### 🔍 **Validation Engine**
- File integrity checks (shapefile bundles, format validation)
- Geometry validity analysis
- Mixed geometry type detection
- Coordinate Reference System (CRS) presence verification

### 🗺️ **CRS Management**
- Automatic CRS detection and inference
- Interactive CRS selection with confidence scoring
- Popular CRS quick-select (WGS84, Web Mercator, UTM zones)
- Bounds preview before/after reprojection

### 🔧 **Auto-Repair**
- Fix invalid geometries using `shapely.make_valid`
- Remove empty geometries
- Explode multipart geometries (optional)
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

```bash
pip install -r requirements.txt
```

### Run the Web App

```bash
streamlit run geolint/web/app.py
```

Open your browser to `http://localhost:8501`

### Command Line Usage

After installation, you can also use the CLI:

```bash
# Validate a file and print a summary
geolint validate path/to/data.gpkg

# Batch process multiple files (unify CRS to EPSG:4326)
geolint batch path/one.geojson path/two.gpkg --unify-crs --target-crs EPSG:4326 --fix-geometries

# Launch the web UI from the CLI
geolint web
```

## Supported Formats

- **Input**: Shapefile (.zip), GeoPackage (.gpkg), GeoJSON (.geojson)
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
│   │   ├── crs.py
│   │   ├── geometry.py
│   │   ├── transform.py
│   │   ├── batch.py
│   │   └── report.py
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

