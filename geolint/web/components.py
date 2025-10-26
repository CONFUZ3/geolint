"""
Reusable Streamlit UI components for GeoLint.

Provides common UI components like metric cards, CRS selectors, and file uploaders.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Optional, Any
import plotly.express as px
import plotly.graph_objects as go
import geopandas as gpd


def metric_card(title: str, value: Any, delta: Optional[str] = None, 
                status: str = "info", help_text: Optional[str] = None) -> None:
    """
    Display a metric card with title, value, and optional delta.
    
    Args:
        title: Card title
        value: Main value to display
        delta: Optional delta value (e.g., "+5%")
        status: Card status ("success", "warning", "error", "info")
        help_text: Optional help text for tooltip
    """
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f"**{title}**")
        if help_text:
            st.markdown(f"<span class='tooltip' title='{help_text}'>i</span>", unsafe_allow_html=True)
    
    with col2:
        if delta:
            st.markdown(f"<span class='status-badge {status}'>{delta}</span>", unsafe_allow_html=True)
    
    # Display value with appropriate formatting
    if isinstance(value, (int, float)):
        if value >= 1000000:
            formatted_value = f"{value/1000000:.1f}M"
        elif value >= 1000:
            formatted_value = f"{value/1000:.1f}K"
        else:
            formatted_value = f"{value:,}"
    else:
        formatted_value = str(value)
    
    st.markdown(f"<h2 style='color: #667eea; margin: 0;'>{formatted_value}</h2>", unsafe_allow_html=True)


def status_badge(text: str, status: str = "info") -> None:
    """
    Display a status badge.
    
    Args:
        text: Badge text
        status: Badge status ("success", "warning", "error", "info")
    """
    st.markdown(f"<span class='status-badge {status}'>{text}</span>", unsafe_allow_html=True)


def crs_selector(current_crs: Optional[Dict] = None, 
                 popular_crs: Dict = None) -> Optional[str]:
    """
    Display an interactive CRS selector with dropdown.
    
    Args:
        current_crs: Current CRS information
        popular_crs: Popular CRS by category
        
    Returns:
        Selected CRS string or None
    """
    st.markdown("### Coordinate Reference System")
    
    # Current CRS display
    if current_crs and current_crs.get('crs'):
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"**Current CRS:** {current_crs.get('name', 'Unknown')}")
        with col2:
            st.markdown(f"**EPSG:** {current_crs.get('epsg', 'N/A')}")
    
    # Create comprehensive CRS options for dropdown
    crs_options = {
        # Global/Web CRS (prioritized for web mapping)
        "Web Mercator (EPSG:3857)": "EPSG:3857",
        "WGS84 (EPSG:4326)": "EPSG:4326",
        
        # European CRS
        "ETRS89 / UTM Zone 32N (EPSG:25832)": "EPSG:25832",
        "ETRS89 / UTM Zone 33N (EPSG:25833)": "EPSG:25833",
        "ETRS89 / UTM Zone 34N (EPSG:25834)": "EPSG:25834",
        "ETRS89 / UTM Zone 35N (EPSG:25835)": "EPSG:25835",
        "ETRS89 / UTM Zone 36N (EPSG:25836)": "EPSG:25836",
        "ETRS89 / UTM Zone 37N (EPSG:25837)": "EPSG:25837",
        "ETRS89 / UTM Zone 38N (EPSG:25838)": "EPSG:25838",
        
        # North American CRS
        "NAD83 / UTM Zone 10N (EPSG:26910)": "EPSG:26910",
        "NAD83 / UTM Zone 11N (EPSG:26911)": "EPSG:26911",
        "NAD83 / UTM Zone 12N (EPSG:26912)": "EPSG:26912",
        "NAD83 / UTM Zone 13N (EPSG:26913)": "EPSG:26913",
        "NAD83 / UTM Zone 14N (EPSG:26914)": "EPSG:26914",
        "NAD83 / UTM Zone 15N (EPSG:26915)": "EPSG:26915",
        "NAD83 / UTM Zone 16N (EPSG:26916)": "EPSG:26916",
        "NAD83 / UTM Zone 17N (EPSG:26917)": "EPSG:26917",
        "NAD83 / UTM Zone 18N (EPSG:26918)": "EPSG:26918",
        "NAD83 / UTM Zone 19N (EPSG:26919)": "EPSG:26919",
        "NAD83 / UTM Zone 20N (EPSG:26920)": "EPSG:26920",
        
        # Global UTM Zones (Northern Hemisphere)
        "UTM Zone 1N (EPSG:32601)": "EPSG:32601",
        "UTM Zone 2N (EPSG:32602)": "EPSG:32602",
        "UTM Zone 3N (EPSG:32603)": "EPSG:32603",
        "UTM Zone 4N (EPSG:32604)": "EPSG:32604",
        "UTM Zone 5N (EPSG:32605)": "EPSG:32605",
        "UTM Zone 6N (EPSG:32606)": "EPSG:32606",
        "UTM Zone 7N (EPSG:32607)": "EPSG:32607",
        "UTM Zone 8N (EPSG:32608)": "EPSG:32608",
        "UTM Zone 9N (EPSG:32609)": "EPSG:32609",
        "UTM Zone 10N (EPSG:32610)": "EPSG:32610",
        "UTM Zone 11N (EPSG:32611)": "EPSG:32611",
        "UTM Zone 12N (EPSG:32612)": "EPSG:32612",
        "UTM Zone 13N (EPSG:32613)": "EPSG:32613",
        "UTM Zone 14N (EPSG:32614)": "EPSG:32614",
        "UTM Zone 15N (EPSG:32615)": "EPSG:32615",
        "UTM Zone 16N (EPSG:32616)": "EPSG:32616",
        "UTM Zone 17N (EPSG:32617)": "EPSG:32617",
        "UTM Zone 18N (EPSG:32618)": "EPSG:32618",
        "UTM Zone 19N (EPSG:32619)": "EPSG:32619",
        "UTM Zone 20N (EPSG:32620)": "EPSG:32620",
        "UTM Zone 21N (EPSG:32621)": "EPSG:32621",
        "UTM Zone 22N (EPSG:32622)": "EPSG:32622",
        "UTM Zone 23N (EPSG:32623)": "EPSG:32623",
        "UTM Zone 24N (EPSG:32624)": "EPSG:32624",
        "UTM Zone 25N (EPSG:32625)": "EPSG:32625",
        "UTM Zone 26N (EPSG:32626)": "EPSG:32626",
        "UTM Zone 27N (EPSG:32627)": "EPSG:32627",
        "UTM Zone 28N (EPSG:32628)": "EPSG:32628",
        "UTM Zone 29N (EPSG:32629)": "EPSG:32629",
        "UTM Zone 30N (EPSG:32630)": "EPSG:32630",
        "UTM Zone 31N (EPSG:32631)": "EPSG:32631",
        "UTM Zone 32N (EPSG:32632)": "EPSG:32632",
        "UTM Zone 33N (EPSG:32633)": "EPSG:32633",
        "UTM Zone 34N (EPSG:32634)": "EPSG:32634",
        "UTM Zone 35N (EPSG:32635)": "EPSG:32635",
        "UTM Zone 36N (EPSG:32636)": "EPSG:32636",
        "UTM Zone 37N (EPSG:32637)": "EPSG:32637",
        "UTM Zone 38N (EPSG:32638)": "EPSG:32638",
        "UTM Zone 39N (EPSG:32639)": "EPSG:32639",
        "UTM Zone 40N (EPSG:32640)": "EPSG:32640",
        "UTM Zone 41N (EPSG:32641)": "EPSG:32641",
        "UTM Zone 42N (EPSG:32642)": "EPSG:32642",
        "UTM Zone 43N (EPSG:32643)": "EPSG:32643",
        "UTM Zone 44N (EPSG:32644)": "EPSG:32644",
        "UTM Zone 45N (EPSG:32645)": "EPSG:32645",
        "UTM Zone 46N (EPSG:32646)": "EPSG:32646",
        "UTM Zone 47N (EPSG:32647)": "EPSG:32647",
        "UTM Zone 48N (EPSG:32648)": "EPSG:32648",
        "UTM Zone 49N (EPSG:32649)": "EPSG:32649",
        "UTM Zone 50N (EPSG:32650)": "EPSG:32650",
        "UTM Zone 51N (EPSG:32651)": "EPSG:32651",
        "UTM Zone 52N (EPSG:32652)": "EPSG:32652",
        "UTM Zone 53N (EPSG:32653)": "EPSG:32653",
        "UTM Zone 54N (EPSG:32654)": "EPSG:32654",
        "UTM Zone 55N (EPSG:32655)": "EPSG:32655",
        "UTM Zone 56N (EPSG:32656)": "EPSG:32656",
        "UTM Zone 57N (EPSG:32657)": "EPSG:32657",
        "UTM Zone 58N (EPSG:32658)": "EPSG:32658",
        "UTM Zone 59N (EPSG:32659)": "EPSG:32659",
        "UTM Zone 60N (EPSG:32660)": "EPSG:32660"
    }
    
    # Determine current CRS display name
    current_crs_name = None
    if current_crs and current_crs.get('epsg'):
        current_epsg = current_crs.get('epsg')
        if current_epsg == 3857:
            current_crs_name = "Web Mercator (EPSG:3857)"
        elif current_epsg == 4326:
            current_crs_name = "WGS84 (EPSG:4326)"
        else:
            # Find matching CRS in options
            for name, epsg in crs_options.items():
                if epsg == f"EPSG:{current_epsg}":
                    current_crs_name = name
                    break
            
            if not current_crs_name:
                current_crs_name = f"{current_crs.get('name', 'Unknown')} (EPSG:{current_epsg})"
    
    # CRS selection dropdown
    selected_crs_name = st.selectbox(
        "Choose Coordinate Reference System:",
        options=list(crs_options.keys()),
        index=list(crs_options.keys()).index(current_crs_name) if current_crs_name and current_crs_name in crs_options else 0,
        help="Select the coordinate reference system for transformation"
    )
    
    selected_crs = crs_options[selected_crs_name]
    
    return selected_crs


def file_uploader(accept_types: List[str] = None, 
                  max_files: int = 1,
                  help_text: str = None) -> List[Any]:
    """
    Enhanced file uploader with drag-and-drop styling.
    
    Args:
        accept_types: List of accepted file types
        max_files: Maximum number of files to upload
        help_text: Help text to display
        
    Returns:
        List of uploaded files
    """
    if accept_types is None:
        accept_types = ['.zip', '.gpkg', '.geojson', '.shp']
    
    st.markdown("### Upload Geospatial Data")
    
    if help_text:
        st.info(help_text)
    
    # File type display
    file_types_str = ", ".join(accept_types)
    st.markdown(f"**Supported formats:** {file_types_str}")
    
    # Upload files
    uploaded_files = st.file_uploader(
        "Choose files",
        type=accept_types,
        accept_multiple_files=(max_files > 1),
        help="Drag and drop files here or click to browse"
    )
    
    if uploaded_files:
        if max_files == 1 and not isinstance(uploaded_files, list):
            uploaded_files = [uploaded_files]
        
        # Display uploaded files info
        st.markdown("**Uploaded files:**")
        for i, file in enumerate(uploaded_files):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"File: {file.name}")
            with col2:
                size_mb = file.size / (1024 * 1024)
                st.write(f"{size_mb:.1f} MB")
            with col3:
                status_badge("Ready", "success")
    
    return uploaded_files if uploaded_files else []


def create_map_visualization(gdf: Any) -> None:
    """
    Create an interactive map visualization using Folium.
    
    Args:
        gdf: GeoDataFrame to visualize
    """
    if gdf is None or len(gdf) == 0:
        st.info("No data available for map visualization.")
        return
    
    try:
        import folium
        from streamlit_folium import st_folium
        
        # Display CRS information
        if gdf.crs is None:
            st.warning("No CRS information found. Assuming WGS84 (EPSG:4326).")
            gdf = gdf.set_crs("EPSG:4326")
        else:
            current_epsg = gdf.crs.to_epsg()
            crs_name = gdf.crs.name
            
            if current_epsg == 4326:
                st.success("Data in WGS84 (EPSG:4326) - optimal for web mapping")
            elif current_epsg == 3857:
                st.success("Data in Web Mercator (EPSG:3857) - optimal for web mapping")
            else:
                st.info(f"Data in {crs_name} (EPSG:{current_epsg}) - will be reprojected for web display")
        
        # Show dataset info
        st.markdown(f"**Dataset Info:** {len(gdf)} features, CRS: {gdf.crs}")
        bounds = gdf.total_bounds
        st.markdown(f"**Bounds:** X: {bounds[0]:.6f} to {bounds[2]:.6f}, Y: {bounds[1]:.6f} to {bounds[3]:.6f}")
        
        # Determine if reprojection is needed
        current_epsg = gdf.crs.to_epsg()
        web_friendly_crs = [4326, 3857]  # WGS84 and Web Mercator
        
        if current_epsg not in web_friendly_crs:
            st.info("Reprojecting to WGS84 for web visualization...")
            gdf_web = gdf.to_crs("EPSG:4326")
            use_web_mercator_tiles = False
        else:
            # Use data as-is for web-friendly CRS
            gdf_web = gdf.copy()
            if current_epsg == 4326:
                st.success("Data already in WGS84 - optimal for web mapping")
                use_web_mercator_tiles = False
            elif current_epsg == 3857:
                st.success("Data in Web Mercator - optimal for web mapping")
                use_web_mercator_tiles = True
        
        # Calculate map center and zoom based on CRS
        bounds_web = gdf_web.total_bounds
        
        if current_epsg == 3857:
            # For Web Mercator, convert to lat/lon for map center
            from pyproj import Transformer
            transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
            center_x = (bounds_web[0] + bounds_web[2]) / 2
            center_y = (bounds_web[1] + bounds_web[3]) / 2
            center_lon, center_lat = transformer.transform(center_x, center_y)
        else:
            # For WGS84, use coordinates directly
            center_lat = (bounds_web[1] + bounds_web[3]) / 2
            center_lon = (bounds_web[0] + bounds_web[2]) / 2
        
        # Create Folium map with appropriate tiles
        if use_web_mercator_tiles:
            # Use Web Mercator tiles for EPSG:3857 data
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=10,
                tiles='OpenStreetMap',
                crs='EPSG3857'
            )
        else:
            # Use standard tiles for WGS84 data
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=10,
                tiles='OpenStreetMap'
            )
        
        # Handle different geometry types
        geom_types = gdf_web.geometry.geom_type.unique()
        
        if 'Point' in geom_types:
            # Add point data
            point_data = gdf_web[gdf_web.geometry.geom_type == 'Point'].copy()
            
            # Sample for performance if too many points
            if len(point_data) > 1000:
                sample_size = min(1000, len(point_data))
                step = len(point_data) // sample_size
                point_data = point_data.iloc[::step]
                st.info(f"Showing {len(point_data)} of {len(gdf_web[gdf_web.geometry.geom_type == 'Point'])} points for performance.")
            
            # Add points to map
            for idx, row in point_data.iterrows():
                if current_epsg == 3857:
                    # For Web Mercator, convert coordinates to lat/lon for Folium
                    from pyproj import Transformer
                    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                    lon, lat = transformer.transform(row.geometry.x, row.geometry.y)
                else:
                    # For WGS84, use coordinates directly
                    lat, lon = row.geometry.y, row.geometry.x
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=3,
                    popup=f"Feature {idx}",
                    color='blue',
                    fill=True
                ).add_to(m)
        
        # Add other geometry types as centroids
        other_geoms = gdf_web[~gdf_web.geometry.geom_type.isin(['Point'])]
        if len(other_geoms) > 0:
            # Sample for performance
            if len(other_geoms) > 500:
                sample_size = min(500, len(other_geoms))
                step = len(other_geoms) // sample_size
                other_geoms = other_geoms.iloc[::step]
                st.info(f"Showing centroids of {len(other_geoms)} of {len(gdf_web[~gdf_web.geometry.geom_type.isin(['Point'])])} non-point features for performance.")
            
            for idx, row in other_geoms.iterrows():
                centroid = row.geometry.centroid
                if current_epsg == 3857:
                    # For Web Mercator, convert coordinates to lat/lon for Folium
                    from pyproj import Transformer
                    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                    lon, lat = transformer.transform(centroid.x, centroid.y)
                else:
                    # For WGS84, use coordinates directly
                    lat, lon = centroid.y, centroid.x
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=5,
                    popup=f"Feature {idx} ({row.geometry.geom_type})",
                    color='red',
                    fill=True
                ).add_to(m)
        
        # Add geometry type legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 150px; height: 90px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px">
        <p><b>Geometry Types:</b></p>
        <p><i class="fa fa-circle" style="color:blue"></i> Points</p>
        <p><i class="fa fa-circle" style="color:red"></i> Other (centroids)</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Display the map with stable key based on data
        import hashlib
        data_signature = f"{len(gdf)}_{gdf.crs.to_epsg() if gdf.crs else 'no_crs'}"
        stable_key = f"map_{hashlib.md5(data_signature.encode()).hexdigest()[:8]}"
        st_folium(m, width=700, height=500, key=stable_key)
        
        # Show geometry type distribution
        geom_type_counts = gdf.geometry.geom_type.value_counts()
        st.markdown("**Geometry Types:**")
        for geom_type, count in geom_type_counts.items():
            st.write(f"• {geom_type}: {count}")
        
        # Show dataset summary
        st.markdown("**Dataset Summary:**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Features", len(gdf))
        with col2:
            st.metric("Geometry Types", len(geom_types))
        with col3:
            if gdf.crs:
                epsg_code = gdf.crs.to_epsg()
                crs_name = gdf.crs.name
                
                if epsg_code == 4326:
                    st.metric("CRS", "WGS84 (EPSG:4326)")
                elif epsg_code == 3857:
                    st.metric("CRS", "Web Mercator (EPSG:3857)")
                else:
                    st.metric("CRS", f"{crs_name} (EPSG:{epsg_code})")
            else:
                st.metric("CRS", "Unknown")
            
    except Exception as e:
        st.error(f"Could not create map visualization: {str(e)}")
        st.markdown("**Fallback Information:**")
        try:
            bounds = gdf.total_bounds
            st.write(f"Dataset bounds: {bounds}")
            st.write(f"Feature count: {len(gdf)}")
            st.write(f"Geometry types: {gdf.geometry.geom_type.unique()}")
        except:
            st.write("Unable to display fallback information.")


def validation_dashboard(validation_report: Dict, gdf: Any = None) -> None:
    """
    Display a comprehensive validation dashboard.
    
    Args:
        validation_report: Validation results dictionary
        gdf: Optional GeoDataFrame for map visualization
    """
    st.markdown("### Validation Dashboard")
    
    # Calculate health score
    health_score = _calculate_health_score(validation_report)
    status = "success" if health_score >= 80 else "warning" if health_score >= 50 else "error"
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        metric_card(
            "Health Score",
            f"{health_score:.0f}/100",
            status=status,
            help_text="Overall dataset health score"
        )
    
    with col2:
        feature_count = validation_report.get('validation', {}).get('feature_count', 0)
        metric_card(
            "Features",
            feature_count,
            help_text="Total number of features in the dataset"
        )
    
    with col3:
        crs_present = validation_report.get('validation', {}).get('crs_present', False)
        crs_status = "success" if crs_present else "error"
        
        # Get CRS details if available
        crs_info = validation_report.get('crs_info', {})
        if crs_present and crs_info:
            crs_display = f"{crs_info.get('name', 'Unknown')} (EPSG:{crs_info.get('epsg', 'N/A')})"
        elif crs_present:
            crs_display = "Present (Unknown)"
        else:
            crs_display = "Missing"
            
        metric_card(
            "CRS Status",
            crs_display,
            status=crs_status,
            help_text="Coordinate Reference System information"
        )


def _calculate_health_score(validation_report: Dict) -> float:
    """
    Calculate a health score (0-100) for the dataset.
    
    Args:
        validation_report: Validation results dictionary
        
    Returns:
        Health score between 0 and 100
    """
    score = 100.0
    
    # Deduct points for issues
    validation = validation_report.get('validation', {})
    geometry_validation = validation_report.get('geometry_validation', {})
    
    # CRS issues (-20 points)
    if not validation.get('crs_present', False):
        score -= 20
    
    # Geometry issues
    invalid_count = geometry_validation.get('invalid_count', 0)
    empty_count = geometry_validation.get('empty_count', 0)
    total_features = geometry_validation.get('total_features', 1)
    
    # Invalid geometries (-30 points max)
    if invalid_count > 0:
        invalid_ratio = invalid_count / total_features
        score -= min(30, invalid_ratio * 100)
    
    # Empty geometries (-20 points max)
    if empty_count > 0:
        empty_ratio = empty_count / total_features
        score -= min(20, empty_ratio * 100)
    
    # Mixed geometry types (-10 points)
    if geometry_validation.get('mixed_types', False):
        score -= 10
    
    # Shapefile bundle issues (-10 points)
    shapefile_bundle = validation_report.get('shapefile_bundle', {})
    if not shapefile_bundle.get('is_complete', True):
        score -= 10
    
    # Warnings and errors
    warnings_count = len(validation_report.get('warnings', []))
    errors_count = len(validation_report.get('errors', []))
    
    score -= warnings_count * 2  # -2 points per warning
    score -= errors_count * 5    # -5 points per error
    
    return max(0, min(100, score))


def batch_queue_display(datasets: List[Dict]) -> None:
    """
    Display batch processing queue.
    
    Args:
        datasets: List of dataset information dictionaries
    """
    st.markdown("### Batch Processing Queue")
    
    if not datasets:
        st.info("No datasets in queue. Upload files to get started.")
        return
    
    # Summary statistics
    total_features = sum(d.get('feature_count', 0) for d in datasets)
    total_size = sum(d.get('file_size', 0) for d in datasets)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        metric_card("Datasets", len(datasets))
    
    with col2:
        metric_card("Total Features", total_features)
    
    with col3:
        size_mb = total_size / (1024 * 1024)
        metric_card("Total Size", f"{size_mb:.1f} MB")


def progress_bar(current: int, total: int, message: str = "") -> None:
    """
    Display a progress bar with message.
    
    Args:
        current: Current progress value
        total: Total progress value
        message: Optional progress message
    """
    progress = current / total if total > 0 else 0
    
    st.markdown(f"**{message}**")
    st.progress(progress)
    
    if message:
        st.markdown(f"*{current}/{total} completed*")


def error_message(message: str, details: str = None) -> None:
    """
    Display an error message with optional details.
    
    Args:
        message: Main error message
        details: Optional detailed error information
    """
    st.markdown(f"""
    <div class="error-message">
        <strong>Error:</strong> {message}
        {f"<br><small>{details}</small>" if details else ""}
    </div>
    """, unsafe_allow_html=True)


def success_message(message: str, details: str = None) -> None:
    """
    Display a success message with optional details.
    
    Args:
        message: Main success message
        details: Optional detailed information
    """
    st.markdown(f"""
    <div class="success-message">
        <strong>Success:</strong> {message}
        {f"<br><small>{details}</small>" if details else ""}
    </div>
    """, unsafe_allow_html=True)


def warning_message(message: str, details: str = None) -> None:
    """
    Display a warning message with optional details.
    
    Args:
        message: Main warning message
        details: Optional detailed information
    """
    st.markdown(f"""
    <div class="warning-message">
        <strong>Warning:</strong> {message}
        {f"<br><small>{details}</small>" if details else ""}
    </div>
    """, unsafe_allow_html=True)


def info_message(message: str, details: str = None) -> None:
    """
    Display an info message with optional details.
    
    Args:
        message: Main info message
        details: Optional detailed information
    """
    st.markdown(f"""
    <div class="info-message">
        <strong>Info:</strong> {message}
        {f"<br><small>{details}</small>" if details else ""}
    </div>
    """, unsafe_allow_html=True)


def download_section(cleaned_data: Any, report_data: Dict, 
                    filename: str = "cleaned_data") -> None:
    """
    Display download section with cleaned data and report.
    
    Args:
        cleaned_data: Processed geospatial data
        report_data: Processing report
        filename: Base filename for downloads
    """
    st.markdown("### Download Results")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Cleaned Data")
        
        # Format selector
        format_choice = st.selectbox(
            "Choose format:",
            ["GeoPackage (.gpkg)", "GeoJSON (.geojson)", "Shapefile (.zip)"],
            help="Select the output format for your cleaned data"
        )
        
        # Create download using in-memory approach
        if format_choice == "GeoPackage (.gpkg)":
            import io
            buffer = io.BytesIO()
            cleaned_data.to_file(buffer, driver='GPKG')
            file_data = buffer.getvalue()
            file_extension = '.gpkg'
            mime_type = "application/geopackage+sqlite3"
            
        elif format_choice == "GeoJSON (.geojson)":
            import io
            buffer = io.BytesIO()
            cleaned_data.to_file(buffer, driver='GeoJSON')
            file_data = buffer.getvalue()
            file_extension = '.geojson'
            mime_type = "application/geo+json"
            
        elif format_choice == "Shapefile (.zip)":
            # For shapefile, create zip in memory
            import zipfile
            import io
            import tempfile
            import os
            
            # Create temporary directory for shapefile
            with tempfile.TemporaryDirectory() as temp_dir:
                shapefile_path = os.path.join(temp_dir, f'{filename}.shp')
                cleaned_data.to_file(shapefile_path, driver='ESRI Shapefile')
                
                # Create zip in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zipf:
                    for file in os.listdir(temp_dir):
                        if file.startswith(filename):
                            zipf.write(os.path.join(temp_dir, file), file)
                
                file_data = zip_buffer.getvalue()
                file_extension = '.zip'
                mime_type = "application/zip"
        else:
            # Default to GeoPackage
            import io
            buffer = io.BytesIO()
            cleaned_data.to_file(buffer, driver='GPKG')
            file_data = buffer.getvalue()
            file_extension = '.gpkg'
            mime_type = "application/geopackage+sqlite3"
        
        # Provide download
        st.download_button(
            label="Download Cleaned Data",
            data=file_data,
            file_name=f"{filename}{file_extension}",
            mime=mime_type
        )
    
    with col2:
        st.markdown("#### Processing Report")
        
        # Report download
        if st.button("Download JSON Report", type="secondary"):
            try:
                import json
                
                # Convert report to JSON
                report_json = json.dumps(report_data, indent=2, default=str)
                
                # Provide download
                st.download_button(
                    label="Download JSON Report",
                    data=report_json,
                    file_name=f"{filename}_report.json",
                    mime="application/json"
                )
                
            except Exception as e:
                st.error(f"Failed to create report download: {str(e)}")
        
        # Display report summary
        st.markdown("**Report Summary:**")
        st.json({
            "Health Score": report_data.get('health_score', 0),
            "Features Processed": report_data.get('file_info', {}).get('feature_count', 0),
            "Issues Found": len(report_data.get('warnings', [])) + len(report_data.get('errors', [])),
            "Processing Time": report_data.get('timestamp', 'Unknown')
        })


def expandable_section(title: str, content: Any, expanded: bool = False) -> None:
    """
    Display an expandable section.
    
    Args:
        title: Section title
        content: Section content (function or any)
        expanded: Whether section should be expanded by default
    """
    with st.expander(title, expanded=expanded):
        if callable(content):
            content()
        else:
            st.write(content)