# GeoLint

**GeoLint is the spatial equivalent of a code linter and auto-formatter—for maps.**

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

## Philosophy

- **Validation First**: Always validate before attempting to fix
- **Explicit Over Implicit**: Trust existing metadata, only infer when missing
- **Report Everything**: All actions logged in structured JSON reports
- **Vector Focus**: Designed specifically for vector data (raster support planned for v3.0)

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

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please see CONTRIBUTING.md for guidelines.

## Roadmap

- **v1.0**: Core validation and web interface ✅
- **v1.5**: API endpoints and advanced UI features
- **v2.0**: Batch processing and robust CRS inference
- **v3.0**: Raster data support
