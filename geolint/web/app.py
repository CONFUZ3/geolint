"""
GeoLint Streamlit Web Application.

Main web interface for geospatial data validation, repair, and standardization.
"""

import io
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any

import streamlit as st
import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Import core modules
from geolint.core import (
    run_validation, get_crs_info, infer_crs, get_popular_crs,
    fix_geometries, remove_empty_geometries, reproject_dataset,
    BatchProcessor, generate_report
)
from geolint.core.report import format_report_for_display

# Import UI components
from geolint.web.components import (
    metric_card, status_badge, crs_selector, file_uploader,
    validation_dashboard, batch_queue_display, progress_bar,
    error_message, success_message, warning_message, info_message,
    download_section, expandable_section
)


def load_custom_css():
    """Load custom CSS styles."""
    css_file = Path(__file__).parent / "styles.css"
    if css_file.exists():
        with open(css_file, 'r') as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if 'current_mode' not in st.session_state:
        st.session_state.current_mode = 'single'
    
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = []
    
    if 'validation_reports' not in st.session_state:
        st.session_state.validation_reports = []
    
    if 'processed_data' not in st.session_state:
        st.session_state.processed_data = None
    
    if 'original_data' not in st.session_state:
        st.session_state.original_data = None
    
    if 'transformed_data' not in st.session_state:
        st.session_state.transformed_data = None
    
    if 'selected_crs' not in st.session_state:
        st.session_state.selected_crs = None
    
    if 'batch_processor' not in st.session_state:
        st.session_state.batch_processor = BatchProcessor()


def render_sidebar():
    """Render the sidebar with mode selection and navigation."""
    st.sidebar.markdown("# 🗺️ GeoLint")
    st.sidebar.markdown("**Geospatial Data Linting Tool**")
    
    # Mode selection
    mode = st.sidebar.radio(
        "Select Mode:",
        ["Single File", "Batch Processing"],
        index=0 if st.session_state.current_mode == 'single' else 1
    )
    
    st.session_state.current_mode = 'single' if mode == "Single File" else 'batch'
    
    # Navigation
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Navigation")
    
    if st.session_state.current_mode == 'single':
        pages = ["Upload & View", "Change CRS", "AutoFix", "Download"]
    else:
        pages = ["Upload", "Queue", "Process", "Download"]
    
    for page in pages:
        st.sidebar.markdown(f"• {page}")
    
    # Help section
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Help")
    st.sidebar.markdown("""
    **Supported Formats:**
    - Shapefile (.zip)
    - GeoPackage (.gpkg)
    - GeoJSON (.geojson)
    
    **Workflow:**
    1. **Upload & View** - Upload data and see it on the map
    2. **Change CRS** - Transform coordinates and compare before/after
    3. **AutoFix** - Clean geometries and finalize data
    4. **Download** - Export your processed data
    
    **Features:**
    - Interactive map visualization
    - CRS transformation with comparison
    - Geometry validation & repair
    - Batch processing
    """)


def single_file_mode():
    """Render single file processing mode."""
    st.markdown("# 📁 Single File Processing")
    
    # Progress indicator
    progress_steps = ["Upload & View", "Change CRS", "AutoFix", "Download"]
    current_step = 0
    
    if st.session_state.get('uploaded_files'):
        current_step = 1
    if st.session_state.get('transformed_data') is not None:
        current_step = 2
    if st.session_state.get('final_report'):
        current_step = 3
    
    # Create progress bar
    progress_cols = st.columns(len(progress_steps))
    for i, (col, step) in enumerate(zip(progress_cols, progress_steps)):
        with col:
            if i <= current_step:
                st.markdown(f"✅ **{step}**")
            else:
                st.markdown(f"⏳ {step}")
    
    st.markdown("---")
    
    # Reset button
    if st.session_state.get('uploaded_files'):
        col1, col2, col3 = st.columns([1, 1, 8])
        with col1:
            if st.button("🔄 Reset", type="secondary"):
                # Clear session state
                for key in ['uploaded_files', 'validation_reports', 'processed_data', 
                           'original_data', 'transformed_data', 'selected_crs', 
                           'final_processed_data', 'final_report', 'geometry_report']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
    
    # Step 1: File Upload & Initial Map View
    st.markdown("## Step 1: Upload File & View Data")
    
    uploaded_files = file_uploader(
        accept_types=['.zip', '.gpkg', '.geojson'],
        max_files=1,
        help_text="Upload a single geospatial file for validation and processing"
    )
    
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files
        
        # Process the uploaded file
        with st.spinner("Loading and validating dataset..."):
            try:
                # Save uploaded file to temporary location
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_files[0].name).suffix) as tmp_file:
                    tmp_file.write(uploaded_files[0].getvalue())
                    tmp_path = Path(tmp_file.name)
                
                # Run validation
                validation_report, gdf = run_validation(tmp_path)
                
                # Store in session state
                st.session_state.validation_reports = [validation_report]
                st.session_state.processed_data = gdf
                st.session_state.original_data = gdf.copy()  # Keep original for comparison
                
                # Display success message with validation summary
                validation_report = st.session_state.validation_reports[0]
                geom_validation = validation_report.get('geometry_validation', {})
                crs_present = validation_report.get('validation', {}).get('crs_present', False)
                
                # Build validation summary
                summary_parts = [f"Found {len(gdf)} features"]
                
                if geom_validation.get('invalid_count', 0) > 0:
                    summary_parts.append(f"{geom_validation['invalid_count']} invalid geometries")
                
                if geom_validation.get('empty_count', 0) > 0:
                    summary_parts.append(f"{geom_validation['empty_count']} empty geometries")
                
                if not crs_present:
                    summary_parts.append("No CRS information")
                
                summary_text = ", ".join(summary_parts)
                
                success_message(
                    "File uploaded and validated successfully!",
                    summary_text
                )
                
            except Exception as e:
                error_message("Failed to process uploaded file", str(e))
                return
        
        # Show immediate map visualization after upload
        if st.session_state.processed_data is not None:
            st.markdown("### 🗺️ Initial Data View")
            
            # Create tabs for data exploration
            explore_tab1, explore_tab2 = st.tabs(["📍 Map View", "📋 Attribute Table"])
            
            with explore_tab1:
                from geolint.web.components import create_map_visualization
                create_map_visualization(st.session_state.processed_data)
            
            with explore_tab2:
                st.markdown("**Attribute Table**")
                
                # Show basic info about the dataset
                gdf = st.session_state.processed_data
                st.markdown(f"**Dataset Overview:** {len(gdf)} features, {len(gdf.columns)} columns")
                
                # Display column information
                st.markdown("**Column Information:**")
                col_info = []
                for col in gdf.columns:
                    if col != 'geometry':  # Skip geometry column for basic info
                        dtype = str(gdf[col].dtype)
                        null_count = gdf[col].isnull().sum()
                        col_info.append({
                            'Column': col,
                            'Type': dtype,
                            'Null Count': null_count,
                            'Unique Values': gdf[col].nunique()
                        })
                
                if col_info:
                    col_df = pd.DataFrame(col_info)
                    st.dataframe(col_df, use_container_width=True)
                
                # Show sample of the data
                st.markdown("**Data Preview (first 10 rows):**")
                
                # Create a copy without geometry for display
                display_df = gdf.drop(columns=['geometry']).head(10)
                
                if len(display_df) > 0:
                    st.dataframe(display_df, use_container_width=True)
                else:
                    st.info("No attribute data to display.")
                
                # Show geometry information
                st.markdown("**Geometry Information:**")
                geom_types = gdf.geometry.geom_type.value_counts()
                st.write(geom_types)
        
        # Step 2: CRS Management & Comparison
        st.markdown("## Step 2: Change Coordinate Reference System")
        
        if st.session_state.processed_data is not None:
            gdf = st.session_state.processed_data
            original_gdf = st.session_state.original_data
            
            # Get current CRS info
            crs_info = get_crs_info(gdf)
            
            # Get popular CRS
            popular_crs = get_popular_crs()
            
            # CRS selector
            selected_crs = crs_selector(
                current_crs=crs_info,
                popular_crs=popular_crs
            )
            
            # Store selected CRS
            if selected_crs:
                st.session_state.selected_crs = selected_crs
                success_message(f"Selected CRS: {selected_crs}")
            
            # Apply CRS transformation if selected
            if selected_crs and selected_crs != f"EPSG:{crs_info.get('epsg', '')}":
                if st.button("🔄 Apply CRS Transformation", type="primary"):
                    with st.spinner("Transforming data to new CRS..."):
                        try:
                            # Transform the data
                            transformed_gdf = gdf.to_crs(selected_crs)
                            st.session_state.transformed_data = transformed_gdf
                            success_message("CRS transformation completed successfully!")
                        except Exception as e:
                            error_message("CRS transformation failed", str(e))
            
            # Show before/after comparison if transformation was applied
            if st.session_state.get('transformed_data') is not None:
                st.markdown("### 🔄 Before vs After CRS Transformation")
                
                # Create comparison tabs
                comparison_tab1, comparison_tab2, comparison_tab3 = st.tabs([
                    "📍 Side-by-Side Maps", 
                    "📊 Data Comparison", 
                    "📐 Bounds Analysis"
                ])
                
                with comparison_tab1:
                    st.markdown("#### Original Data (Before Transformation)")
                    from geolint.web.components import create_map_visualization
                    create_map_visualization(original_gdf)
                    
                    st.markdown("#### Transformed Data (After Transformation)")
                    create_map_visualization(st.session_state.transformed_data)
                
                with comparison_tab2:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Original Data:**")
                        st.write(f"CRS: {original_gdf.crs}")
                        st.write(f"Features: {len(original_gdf)}")
                        bounds = original_gdf.total_bounds
                        st.write(f"Bounds: {bounds}")
                    
                    with col2:
                        st.markdown("**Transformed Data:**")
                        st.write(f"CRS: {st.session_state.transformed_data.crs}")
                        st.write(f"Features: {len(st.session_state.transformed_data)}")
                        bounds = st.session_state.transformed_data.total_bounds
                        st.write(f"Bounds: {bounds}")
                
                with comparison_tab3:
                    st.markdown("#### Bounds Comparison")
                    
                    original_bounds = original_gdf.total_bounds
                    transformed_bounds = st.session_state.transformed_data.total_bounds
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Original Bounds:**")
                        st.write(f"X: {original_bounds[0]:.6f} to {original_bounds[2]:.6f}")
                        st.write(f"Y: {original_bounds[1]:.6f} to {original_bounds[3]:.6f}")
                        original_area = (original_bounds[2] - original_bounds[0]) * (original_bounds[3] - original_bounds[1])
                        st.write(f"Area: {original_area:.6f}")
                    
                    with col2:
                        st.markdown("**Transformed Bounds:**")
                        st.write(f"X: {transformed_bounds[0]:.6f} to {transformed_bounds[2]:.6f}")
                        st.write(f"Y: {transformed_bounds[1]:.6f} to {transformed_bounds[3]:.6f}")
                        transformed_area = (transformed_bounds[2] - transformed_bounds[0]) * (transformed_bounds[3] - transformed_bounds[1])
                        st.write(f"Area: {transformed_area:.6f}")
                    
                    # Calculate area change
                    if original_area > 0:
                        area_ratio = transformed_area / original_area
                        change_pct = (area_ratio - 1) * 100
                        change_type = "increase" if change_pct > 0 else "decrease"
                        st.info(f"Area {change_type}s by {abs(change_pct):.1f}% after transformation")
            
            # Bounds preview if CRS selected but not yet applied
            elif selected_crs and crs_info.get('crs'):
                try:
                    from geolint.core.transform import get_transform_preview
                    preview = get_transform_preview(gdf, selected_crs)
                    
                    if preview.get('preview_available'):
                        st.markdown("#### 📐 Transformation Preview")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**Current Bounds:**")
                            original_bounds = preview['original_bounds']
                            st.write(f"X: {original_bounds[0]:.6f} to {original_bounds[2]:.6f}")
                            st.write(f"Y: {original_bounds[1]:.6f} to {original_bounds[3]:.6f}")
                        
                        with col2:
                            st.markdown("**Target Bounds:**")
                            target_bounds = preview['target_bounds']
                            st.write(f"X: {target_bounds[0]:.6f} to {target_bounds[2]:.6f}")
                            st.write(f"Y: {target_bounds[1]:.6f} to {target_bounds[3]:.6f}")
                        
                        # Area change
                        area_ratio = preview.get('area_ratio', 1.0)
                        if area_ratio != 1.0:
                            change_pct = (area_ratio - 1) * 100
                            change_type = "increase" if change_pct > 0 else "decrease"
                            st.info(f"Area will {change_type} by {abs(change_pct):.1f}%")
                
                except Exception as e:
                    warning_message("Could not generate bounds preview", str(e))
        
        # Step 3: AutoFix Options
        st.markdown("## Step 3: AutoFix Options")
        
        if st.session_state.processed_data is not None:
            # Use transformed data if available, otherwise use original
            working_data = st.session_state.get('transformed_data')
            if working_data is None:
                working_data = st.session_state.processed_data
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 🔧 Geometry Options")
                fix_invalid = st.checkbox("Fix invalid geometries", value=True)
                remove_empty = st.checkbox("Remove empty geometries", value=True)
                explode_multipart = st.checkbox("Explode multipart geometries", value=False)
                simplify = st.checkbox("Simplify geometries", value=False)
                
                if simplify:
                    tolerance = st.slider("Simplification tolerance", 0.001, 0.1, 0.001, 0.001)
                else:
                    tolerance = 0.001
            
            with col2:
                st.markdown("### 🗺️ Additional Options")
                # Show current data status
                if st.session_state.get('transformed_data') is not None:
                    st.success("✅ Data has been transformed to new CRS")
                    st.write(f"Current CRS: {working_data.crs}")
                else:
                    st.info("ℹ️ Using original data CRS")
                    st.write(f"Current CRS: {working_data.crs}")
            
            # AutoFix button
            if st.button("🚀 Run AutoFix", type="primary", use_container_width=True):
                with st.spinner("Processing dataset..."):
                    try:
                        gdf = working_data.copy()
                        
                        # Fix geometries
                        if fix_invalid or remove_empty or explode_multipart or simplify:
                            from geolint.core.geometry import process_geometries
                            
                            gdf, geom_report = process_geometries(
                                gdf,
                                fix_invalid=fix_invalid,
                                remove_empty=remove_empty,
                                explode_multipart=explode_multipart,
                                simplify=simplify,
                                simplify_tolerance=tolerance
                            )
                            
                            st.session_state.geometry_report = geom_report
                        
                        # Store final processed data
                        st.session_state.final_processed_data = gdf
                        
                        # Generate final report
                        final_report = generate_report(
                            st.session_state.validation_reports[0],
                            crs_info=get_crs_info(gdf),
                            geometry_report=st.session_state.get('geometry_report'),
                            transform_report=None  # CRS transformation already handled in Step 2
                        )
                        
                        st.session_state.final_report = final_report
                        
                        success_message(
                            "AutoFix completed successfully!",
                            f"Processed {len(gdf)} features"
                        )
                        
                        # Show processing results
                        if st.session_state.get('geometry_report'):
                            geom_report = st.session_state.geometry_report
                            st.markdown("#### 🔧 Geometry Processing Results")
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                metric_card("Geometries Fixed", geom_report.get('geometries_fixed', 0))
                            with col2:
                                metric_card("Geometries Removed", geom_report.get('geometries_removed', 0))
                            with col3:
                                metric_card("Final Count", geom_report.get('final_count', 0))
                        
                        # Show final data summary
                        st.markdown("#### 📊 Final Data Summary")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Features", len(gdf))
                        with col2:
                            st.metric("CRS", f"{gdf.crs.name} (EPSG:{gdf.crs.to_epsg()})")
                        with col3:
                            geom_types = gdf.geometry.geom_type.nunique()
                            st.metric("Geometry Types", geom_types)
                    
                    except Exception as e:
                        error_message("AutoFix failed", str(e))
        
        # Step 4: Download Results
        if st.session_state.get('final_report'):
            st.markdown("## Step 4: Download Results")
            
            # Use final processed data if available, otherwise use transformed or original
            final_data = st.session_state.get('final_processed_data')
            if final_data is None:
                final_data = st.session_state.get('transformed_data')
            if final_data is None:
                final_data = st.session_state.processed_data
            
            download_section(
                final_data,
                st.session_state.final_report,
                filename="cleaned_data"
            )


def batch_processing_mode():
    """Render batch processing mode."""
    st.markdown("# 📦 Batch Processing")
    
    # Step 1: Multi-file Upload
    st.markdown("## Step 1: Upload Multiple Files")
    
    uploaded_files = file_uploader(
        accept_types=['.zip', '.gpkg', '.geojson'],
        max_files=10,
        help_text="Upload multiple geospatial files for batch processing"
    )
    
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files
        
        # Process uploaded files
        with st.spinner("Loading and validating datasets..."):
            try:
                batch_processor = st.session_state.batch_processor
                batch_processor.clear()
                
                validation_reports = []
                
                for i, uploaded_file in enumerate(uploaded_files):
                    # Save to temporary location
                    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_path = Path(tmp_file.name)
                    
                    # Run validation and add to batch processor
                    validation_report, gdf = run_validation(tmp_path)
                    batch_processor.add_dataset(gdf, uploaded_file.name)
                    validation_reports.append(validation_report)
                
                st.session_state.validation_reports = validation_reports
                
                success_message(
                    f"Successfully loaded {len(uploaded_files)} datasets!",
                    "Ready for batch processing"
                )
                
            except Exception as e:
                error_message("Failed to process uploaded files", str(e))
                return
        
        # Step 2: Batch Queue Display
        st.markdown("## Step 2: Batch Queue")
        
        if st.session_state.batch_processor.datasets:
            # Calculate file sizes from uploaded files
            file_sizes = []
            for i, uploaded_file in enumerate(st.session_state.uploaded_files):
                file_size = len(uploaded_file.getvalue())
                file_sizes.append(file_size)
            
            batch_queue_display([
                {
                    'name': dataset['name'],
                    'feature_count': len(dataset['gdf']),
                    'file_size': file_sizes[i] if i < len(file_sizes) else 0,
                    'crs_name': dataset['gdf'].crs.name if dataset['gdf'].crs else 'Unknown',
                    'status': 'Ready'
                }
                for i, dataset in enumerate(st.session_state.batch_processor.datasets)
            ])
        
        # Step 3: Batch Processing Options
        st.markdown("## Step 3: Batch Processing Options")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🗺️ CRS Strategy")
            crs_strategy = st.radio(
                "Choose CRS unification strategy:",
                ["Keep original CRS for each file", "Use first file's CRS for all", 
                 "Reproject all to common CRS", "Auto-detect optimal common CRS"],
                help="Select how to handle CRS across multiple datasets"
            )
            
            if crs_strategy == "Reproject all to common CRS":
                target_crs = st.text_input("Target CRS:", placeholder="EPSG:4326")
            else:
                target_crs = "EPSG:4326"
        
        with col2:
            st.markdown("### 🔧 Processing Options")
            unify_crs = st.checkbox("Unify CRS", value=True)
            fix_geometries = st.checkbox("Fix geometries", value=True)
            merge_datasets = st.checkbox("Merge into single file", value=False)
            
            if merge_datasets:
                st.info("All datasets will be combined into one GeoPackage file")
        
        # Batch processing button
        if st.button("🚀 Start Batch Processing", type="primary", use_container_width=True):
            with st.spinner("Processing batch..."):
                try:
                    batch_processor = st.session_state.batch_processor
                    
                    # Determine CRS strategy
                    strategy_map = {
                        "Keep original CRS for each file": "manual",
                        "Use first file's CRS for all": "use_most_common",
                        "Reproject all to common CRS": "manual",
                        "Auto-detect optimal common CRS": "auto_detect"
                    }
                    
                    crs_strategy_key = strategy_map[crs_strategy]
                    
                    # Process batch
                    results = batch_processor.process_batch(
                        unify_crs=unify_crs,
                        target_crs=target_crs if crs_strategy == "Reproject all to common CRS" else "EPSG:4326",
                        crs_strategy=crs_strategy_key,
                        fix_geometries=fix_geometries,
                        merge_datasets=merge_datasets
                    )
                    
                    st.session_state.batch_results = results
                    
                    if results['success']:
                        success_message(
                            "Batch processing completed successfully!",
                            f"Processed {results['total_datasets']} datasets"
                        )
                        
                        # Show processing summary
                        st.markdown("#### 📊 Processing Summary")
                        
                        for step in results['processing_steps']:
                            step_name = step['step'].replace('_', ' ').title()
                            status = "✅" if step['success'] else "❌"
                            st.write(f"{status} {step_name}")
                    
                    else:
                        error_message("Batch processing failed", results.get('error', 'Unknown error'))
                
                except Exception as e:
                    error_message("Batch processing failed", str(e))
        
        # Step 4: Download Results
        if st.session_state.get('batch_results') and st.session_state.batch_results.get('success'):
            st.markdown("## Step 4: Download Results")
            
            if st.session_state.batch_results.get('final_dataset') is not None:
                # Merged dataset available
                st.success("All datasets have been merged into a single file!")
                
                merged_gdf = st.session_state.batch_results['final_dataset']
                
                # Format selector
                format_choice = st.selectbox(
                    "Choose format:",
                    ["GeoPackage (.gpkg)", "GeoJSON (.geojson)", "Shapefile (.zip)"],
                    help="Select the output format for your merged data"
                )
                
                # Create download button that generates file on demand
                if format_choice == "GeoPackage (.gpkg)":
                    # Use BytesIO for in-memory file creation
                    import io
                    buffer = io.BytesIO()
                    merged_gdf.to_file(buffer, driver='GPKG')
                    file_data = buffer.getvalue()
                    file_extension = '.gpkg'
                    mime_type = "application/geopackage+sqlite3"
                    
                elif format_choice == "GeoJSON (.geojson)":
                    import io
                    buffer = io.BytesIO()
                    merged_gdf.to_file(buffer, driver='GeoJSON')
                    file_data = buffer.getvalue()
                    file_extension = '.geojson'
                    mime_type = "application/geo+json"
                    
                elif format_choice == "Shapefile (.zip)":
                    # For shapefile, create zip in memory
                    import zipfile
                    import io
                    import os
                    
                    # Create temporary directory for shapefile
                    with tempfile.TemporaryDirectory() as temp_dir:
                        shapefile_path = os.path.join(temp_dir, 'merged_data.shp')
                        merged_gdf.to_file(shapefile_path, driver='ESRI Shapefile')
                        
                        # Create zip in memory
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w') as zipf:
                            for file in os.listdir(temp_dir):
                                if file.startswith('merged_data'):
                                    zipf.write(os.path.join(temp_dir, file), file)
                        
                        file_data = zip_buffer.getvalue()
                        file_extension = '.zip'
                        mime_type = "application/zip"
                
                else:
                    # Default to GeoPackage
                    import io
                    buffer = io.BytesIO()
                    merged_gdf.to_file(buffer, driver='GPKG')
                    file_data = buffer.getvalue()
                    file_extension = '.gpkg'
                    mime_type = "application/geopackage+sqlite3"
                
                # Provide download
                st.download_button(
                    label="📥 Download Merged Dataset",
                    data=file_data,
                    file_name=f"merged_data{file_extension}",
                    mime=mime_type
                )
            
            else:
                # Individual files
                st.info("Download individual processed files")
                
                # Create ZIP download using in-memory approach
                import zipfile
                import io
                
                # Create zip in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zipf:
                    for i, dataset in enumerate(st.session_state.batch_processor.datasets):
                        # Create each dataset in memory
                        dataset_buffer = io.BytesIO()
                        dataset['gdf'].to_file(dataset_buffer, driver='GPKG')
                        
                        # Add to zip
                        zipf.writestr(f"{dataset['name']}.gpkg", dataset_buffer.getvalue())
                
                # Get zip data
                zip_data = zip_buffer.getvalue()
                
                # Provide download
                st.download_button(
                    label="📦 Download All Files as ZIP",
                    data=zip_data,
                    file_name="batch_processed_files.zip",
                    mime="application/zip"
                )


def main():
    """Main application entry point."""
    # Configure page
    st.set_page_config(
        page_title="GeoLint - Geospatial Data Linting Tool",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load custom CSS
    load_custom_css()
    
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar
    render_sidebar()
    
    # Main content area
    if st.session_state.current_mode == 'single':
        single_file_mode()
    else:
        batch_processing_mode()
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
            <p>GeoLint v1.0.0 | Made with ❤️ for the geospatial community</p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
