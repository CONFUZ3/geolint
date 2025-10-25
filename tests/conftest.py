"""
Pytest configuration and fixtures for GeoLint tests.
"""

import pytest
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point, Polygon, LineString
from pathlib import Path
import tempfile
import zipfile


@pytest.fixture
def sample_point_gdf():
    """Create a sample GeoDataFrame with Point geometries."""
    data = {
        'id': [1, 2, 3, 4, 5],
        'name': ['A', 'B', 'C', 'D', 'E'],
        'geometry': [
            Point(0, 0),
            Point(1, 1),
            Point(2, 2),
            Point(3, 3),
            Point(4, 4)
        ]
    }
    return gpd.GeoDataFrame(data, crs='EPSG:4326')


@pytest.fixture
def sample_polygon_gdf():
    """Create a sample GeoDataFrame with Polygon geometries."""
    data = {
        'id': [1, 2, 3],
        'name': ['Polygon A', 'Polygon B', 'Polygon C'],
        'geometry': [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
            Polygon([(4, 4), (5, 4), (5, 5), (4, 5)])
        ]
    }
    return gpd.GeoDataFrame(data, crs='EPSG:4326')


@pytest.fixture
def sample_line_gdf():
    """Create a sample GeoDataFrame with LineString geometries."""
    data = {
        'id': [1, 2],
        'name': ['Line A', 'Line B'],
        'geometry': [
            LineString([(0, 0), (1, 1), (2, 2)]),
            LineString([(3, 3), (4, 4), (5, 5)])
        ]
    }
    return gpd.GeoDataFrame(data, crs='EPSG:4326')


@pytest.fixture
def sample_mixed_gdf():
    """Create a sample GeoDataFrame with mixed geometry types."""
    data = {
        'id': [1, 2, 3, 4],
        'name': ['Point', 'Line', 'Polygon', 'Point2'],
        'geometry': [
            Point(0, 0),
            LineString([(1, 1), (2, 2)]),
            Polygon([(3, 3), (4, 3), (4, 4), (3, 4)]),
            Point(5, 5)
        ]
    }
    return gpd.GeoDataFrame(data, crs='EPSG:4326')


@pytest.fixture
def sample_invalid_gdf():
    """Create a sample GeoDataFrame with invalid geometries."""
    data = {
        'id': [1, 2, 3],
        'name': ['Valid', 'Invalid', 'Empty'],
        'geometry': [
            Point(0, 0),  # Valid
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),  # Self-intersecting (invalid)
            Point()  # Empty geometry
        ]
    }
    return gpd.GeoDataFrame(data, crs='EPSG:4326')


@pytest.fixture
def sample_no_crs_gdf():
    """Create a sample GeoDataFrame without CRS."""
    data = {
        'id': [1, 2, 3],
        'name': ['A', 'B', 'C'],
        'geometry': [
            Point(0, 0),
            Point(1, 1),
            Point(2, 2)
        ]
    }
    return gpd.GeoDataFrame(data)


@pytest.fixture
def sample_empty_gdf():
    """Create an empty GeoDataFrame."""
    return gpd.GeoDataFrame(columns=['id', 'name', 'geometry'], crs='EPSG:4326')


@pytest.fixture
def sample_shapefile_zip():
    """Create a temporary shapefile zip for testing."""
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
        zip_path = Path(tmp_file.name)
    
    # Create a simple shapefile
    gdf = gpd.GeoDataFrame({
        'id': [1, 2, 3],
        'name': ['A', 'B', 'C'],
        'geometry': [
            Point(0, 0),
            Point(1, 1),
            Point(2, 2)
        ]
    }, crs='EPSG:4326')
    
    # Save as shapefile
    with tempfile.TemporaryDirectory() as temp_dir:
        shp_path = Path(temp_dir) / 'test.shp'
        gdf.to_file(shp_path)
        
        # Create zip file
        with zipfile.ZipFile(zip_path, 'w') as zip_ref:
            for file_path in shp_path.parent.glob('test.*'):
                zip_ref.write(file_path, file_path.name)
    
    yield zip_path
    
    # Cleanup
    zip_path.unlink(missing_ok=True)


@pytest.fixture
def sample_geopackage():
    """Create a temporary GeoPackage file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
        gpkg_path = Path(tmp_file.name)
    
    gdf = gpd.GeoDataFrame({
        'id': [1, 2, 3],
        'name': ['A', 'B', 'C'],
        'geometry': [
            Point(0, 0),
            Point(1, 1),
            Point(2, 2)
        ]
    }, crs='EPSG:4326')
    
    gdf.to_file(gpkg_path, driver='GPKG')
    
    yield gpkg_path
    
    # Cleanup
    gpkg_path.unlink(missing_ok=True)


@pytest.fixture
def sample_geojson():
    """Create a temporary GeoJSON file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.geojson', delete=False) as tmp_file:
        geojson_path = Path(tmp_file.name)
    
    gdf = gpd.GeoDataFrame({
        'id': [1, 2, 3],
        'name': ['A', 'B', 'C'],
        'geometry': [
            Point(0, 0),
            Point(1, 1),
            Point(2, 2)
        ]
    }, crs='EPSG:4326')
    
    gdf.to_file(geojson_path, driver='GeoJSON')
    
    yield geojson_path
    
    # Cleanup
    geojson_path.unlink(missing_ok=True)


@pytest.fixture
def sample_validation_report():
    """Create a sample validation report for testing."""
    return {
        'file_path': '/test/path.shp',
        'file_name': 'test.shp',
        'file_size': 1024,
        'timestamp': '2024-01-01T00:00:00',
        'validation': {
            'loaded_successfully': True,
            'feature_count': 5,
            'column_count': 3,
            'crs_present': True,
            'has_issues': False,
            'status': 'clean'
        },
        'shapefile_bundle': {
            'has_shp': True,
            'has_shx': True,
            'has_dbf': True,
            'has_prj': True,
            'is_complete': True,
            'missing_files': []
        },
        'geometry_validation': {
            'total_features': 5,
            'valid_count': 5,
            'invalid_count': 0,
            'empty_count': 0,
            'mixed_types': False,
            'geometry_types': ['Point'],
            'multipart_count': 0,
            'invalid_indices': []
        },
        'warnings': [],
        'errors': []
    }


@pytest.fixture
def sample_crs_info():
    """Create a sample CRS info dictionary for testing."""
    return {
        'crs': 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
        'epsg': 4326,
        'is_geographic': True,
        'is_projected': False,
        'units': 'degree',
        'name': 'WGS 84'
    }


@pytest.fixture
def sample_crs_suggestions():
    """Create sample CRS suggestions for testing."""
    return [
        {
            'epsg': 4326,
            'name': 'WGS 84',
            'confidence': 0.9,
            'type': 'geographic',
            'area_of_use': 'World'
        },
        {
            'epsg': 3857,
            'name': 'WGS 84 / Pseudo-Mercator',
            'confidence': 0.8,
            'type': 'projected',
            'area_of_use': 'World'
        },
        {
            'epsg': 32633,
            'name': 'WGS 84 / UTM zone 33N',
            'confidence': 0.7,
            'type': 'projected',
            'area_of_use': 'Europe'
        }
    ]


@pytest.fixture
def sample_geometry_report():
    """Create a sample geometry processing report for testing."""
    return {
        'operations': [
            {
                'operation': 'fix_invalid',
                'geometries_fixed': 2,
                'geometries_removed': 0
            },
            {
                'operation': 'remove_empty',
                'geometries_removed': 1
            }
        ],
        'original_count': 10,
        'final_count': 9,
        'total_removed': 1,
        'geometry_types': {'Point': 5, 'Polygon': 4},
        'bounds': {
            'minx': 0.0,
            'miny': 0.0,
            'maxx': 10.0,
            'maxy': 10.0,
            'width': 10.0,
            'height': 10.0,
            'area': 100.0
        }
    }


@pytest.fixture
def sample_transform_report():
    """Create a sample transformation report for testing."""
    return {
        'transformed': True,
        'original_crs': {
            'crs': 'EPSG:4326',
            'epsg': 4326,
            'is_geographic': True,
            'is_projected': False
        },
        'target_crs': {
            'crs': 'EPSG:3857',
            'epsg': 3857,
            'is_geographic': False,
            'is_projected': True
        },
        'bounds_original': [0.0, 0.0, 10.0, 10.0],
        'bounds_target': [0.0, 0.0, 1113194.9, 1113194.9],
        'area_original': 100.0,
        'area_target': 1234567890.0,
        'area_ratio': 12345678.9,
        'feature_count': 5
    }


@pytest.fixture
def sample_batch_processor():
    """Create a sample BatchProcessor with test data."""
    from geolint.core.batch import BatchProcessor
    
    processor = BatchProcessor()
    
    # Add sample datasets
    gdf1 = gpd.GeoDataFrame({
        'id': [1, 2],
        'geometry': [Point(0, 0), Point(1, 1)]
    }, crs='EPSG:4326')
    
    gdf2 = gpd.GeoDataFrame({
        'id': [3, 4],
        'geometry': [Point(2, 2), Point(3, 3)]
    }, crs='EPSG:4326')
    
    processor.add_dataset(gdf1, 'dataset1')
    processor.add_dataset(gdf2, 'dataset2')
    
    return processor
