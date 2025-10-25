"""
Batch processing for multiple geospatial datasets.

Handles multi-dataset operations, CRS unification, and dataset merging.
"""

from typing import Dict, List, Optional, Tuple, Union, Callable

import geopandas as gpd
import pandas as pd
from pathlib import Path

from .validation import run_validation
from .crs import get_crs_info
from .geometry import process_geometries
from .transform import batch_reproject, validate_crs_compatibility, detect_common_crs


class BatchProcessor:
    """
    Batch processor for handling multiple geospatial datasets.
    """
    
    def __init__(self):
        self.datasets = []
        self.validation_reports = []
        self.processing_reports = []
    
    def add_dataset(self, gdf: gpd.GeoDataFrame, name: str = None) -> int:
        """
        Add a dataset to the batch processor.
        
        Args:
            gdf: GeoDataFrame to add
            name: Optional name for the dataset
            
        Returns:
            Index of the added dataset
        """
        if name is None:
            name = f"dataset_{len(self.datasets)}"
        
        self.datasets.append({
            'gdf': gdf,
            'name': name,
            'index': len(self.datasets)
        })
        
        return len(self.datasets) - 1
    
    def add_dataset_from_file(self, file_path: Union[str, Path], name: str = None) -> Tuple[int, Dict]:
        """
        Add a dataset from a file path.
        
        Args:
            file_path: Path to the dataset file
            name: Optional name for the dataset
            
        Returns:
            Tuple of (dataset_index, validation_report)
        """
        file_path = Path(file_path)
        if name is None:
            name = file_path.stem
        
        # Run validation and load dataset
        validation_report, gdf = run_validation(file_path)
        
        # Add to batch
        index = self.add_dataset(gdf, name)
        
        return index, validation_report
    
    def validate_batch(self) -> Dict[str, Union[int, List[Dict]]]:
        """
        Validate all datasets in the batch.
        
        Returns:
            Dictionary with batch validation results
        """
        if not self.datasets:
            return {'total_datasets': 0, 'validated': 0, 'results': []}
        
        results = []
        validated = 0
        
        for dataset in self.datasets:
            gdf = dataset['gdf']
            name = dataset['name']
            
            # Basic validation
            validation_result = {
                'name': name,
                'index': dataset['index'],
                'feature_count': len(gdf),
                'has_crs': gdf.crs is not None,
                'crs_info': get_crs_info(gdf) if gdf.crs is not None else None,
                'geometry_issues': {
                    'invalid_count': int((~gdf.geometry.is_valid).sum()) if not gdf.empty else 0,
                    'empty_count': int(gdf.geometry.is_empty.sum()) if not gdf.empty else 0,
                    'mixed_types': len(gdf.geom_type.unique()) > 1 if not gdf.empty else False
                }
            }
            
            results.append(validation_result)
            validated += 1
        
        # Analyze CRS distribution
        crs_analysis = self._analyze_crs_distribution()
        
        batch_report = {
            'total_datasets': len(self.datasets),
            'validated': validated,
            'crs_analysis': crs_analysis,
            'results': results
        }
        
        return batch_report
    
    def _analyze_crs_distribution(self) -> Dict[str, Union[str, int, List[Dict]]]:
        """Analyze CRS distribution across all datasets."""
        if not self.datasets:
            return {'common_crs': None, 'confidence': 0.0, 'crs_counts': []}
        
        # Extract GeoDataFrames
        gdfs = [dataset['gdf'] for dataset in self.datasets]
        
        # Use the detect_common_crs function
        return detect_common_crs(gdfs)
    
    def unify_crs(
        self, 
        target_crs: Union[str, int] = "EPSG:4326",
        strategy: str = "manual"
    ) -> Dict[str, Union[int, List[Dict]]]:
        """
        Unify CRS across all datasets.
        
        Args:
            target_crs: Target CRS for unification
            strategy: Unification strategy ("manual", "auto_detect", "use_most_common")
            
        Returns:
            Dictionary with unification results
        """
        if not self.datasets:
            return {'unified': 0, 'failed': 0, 'results': []}
        
        # Determine target CRS based on strategy
        if strategy == "auto_detect":
            crs_analysis = self._analyze_crs_distribution()
            if crs_analysis['common_crs'] and crs_analysis['confidence'] > 0.5:
                target_crs = crs_analysis['common_crs']
            else:
                target_crs = "EPSG:4326"  # Fallback to WGS84
        elif strategy == "use_most_common":
            crs_analysis = self._analyze_crs_distribution()
            if crs_analysis['common_crs']:
                target_crs = crs_analysis['common_crs']
            else:
                target_crs = "EPSG:4326"  # Fallback to WGS84
        
        # Extract GeoDataFrames
        gdfs = [dataset['gdf'] for dataset in self.datasets]
        
        # Perform batch reprojection
        reprojected_gdfs, batch_report = batch_reproject(gdfs, target_crs)
        
        # Update datasets with reprojected versions
        for i, (dataset, reprojected_gdf) in enumerate(zip(self.datasets, reprojected_gdfs)):
            dataset['gdf'] = reprojected_gdf
            dataset['reprojected'] = True
            dataset['target_crs'] = str(target_crs)
        
        return {
            'target_crs': str(target_crs),
            'strategy': strategy,
            'unified': batch_report['successful'],
            'failed': batch_report['failed'],
            'results': batch_report['results']
        }
    
    def fix_geometries_batch(
        self,
        fix_invalid: bool = True,
        remove_empty: bool = True,
        explode_multipart: bool = False,
        simplify: bool = False,
        simplify_tolerance: float = 0.001
    ) -> Dict[str, Union[int, List[Dict]]]:
        """
        Fix geometries across all datasets.
        
        Args:
            fix_invalid: Whether to fix invalid geometries
            remove_empty: Whether to remove empty geometries
            explode_multipart: Whether to explode multipart geometries
            simplify: Whether to simplify geometries
            simplify_tolerance: Simplification tolerance
            
        Returns:
            Dictionary with geometry fixing results
        """
        if not self.datasets:
            return {'processed': 0, 'results': []}
        
        results = []
        processed = 0
        
        for dataset in self.datasets:
            gdf = dataset['gdf']
            name = dataset['name']
            
            try:
                # Process geometries
                processed_gdf, geom_report = process_geometries(
                    gdf,
                    fix_invalid=fix_invalid,
                    remove_empty=remove_empty,
                    explode_multipart=explode_multipart,
                    simplify=simplify,
                    simplify_tolerance=simplify_tolerance
                )
                
                # Update dataset
                dataset['gdf'] = processed_gdf
                dataset['geometry_processed'] = True
                
                result = {
                    'name': name,
                    'index': dataset['index'],
                    'success': True,
                    'original_count': len(gdf),
                    'final_count': len(processed_gdf),
                    'geometry_report': geom_report
                }
                
                processed += 1
                
            except Exception as e:
                result = {
                    'name': name,
                    'index': dataset['index'],
                    'success': False,
                    'error': str(e),
                    'original_count': len(gdf)
                }
            
            results.append(result)
        
        return {
            'processed': processed,
            'total_datasets': len(self.datasets),
            'results': results
        }
    
    def merge_datasets(
        self, 
        merge_strategy: str = "union",
        source_tracking: bool = True
    ) -> Tuple[gpd.GeoDataFrame, Dict[str, Union[int, List[str]]]]:
        """
        Merge all datasets into a single GeoDataFrame.
        
        Args:
            merge_strategy: Strategy for merging ("union", "intersection")
            source_tracking: Whether to add source dataset information
            
        Returns:
            Tuple of (merged_geodataframe, merge_report)
        """
        if not self.datasets:
            return gpd.GeoDataFrame(), {'merged_datasets': 0, 'total_features': 0, 'sources': []}
        
        # Check CRS compatibility
        crs_analysis = self._analyze_crs_distribution()
        if crs_analysis['confidence'] < 1.0:
            # CRS not unified - need to unify first
            self.unify_crs(strategy="use_most_common")
        
        merged_gdfs = []
        sources = []
        
        for dataset in self.datasets:
            gdf = dataset['gdf']
            name = dataset['name']
            
            if not gdf.empty:
                # Add source tracking if requested
                if source_tracking:
                    gdf = gdf.copy()
                    gdf['source_dataset'] = name
                    gdf['source_index'] = dataset['index']
                
                merged_gdfs.append(gdf)
                sources.append(name)
        
        if not merged_gdfs:
            return gpd.GeoDataFrame(), {'merged_datasets': 0, 'total_features': 0, 'sources': []}
        
        # Merge datasets
        if len(merged_gdfs) == 1:
            merged_gdf = merged_gdfs[0]
        else:
            merged_gdf = gpd.pd.concat(merged_gdfs, ignore_index=True)
        
        # Ensure it's a GeoDataFrame
        if not isinstance(merged_gdf, gpd.GeoDataFrame):
            merged_gdf = gpd.GeoDataFrame(merged_gdf)
        
        merge_report = {
            'merged_datasets': len(merged_gdfs),
            'total_features': len(merged_gdf),
            'sources': sources,
            'strategy': merge_strategy,
            'source_tracking': source_tracking
        }
        
        return merged_gdf, merge_report
    
    def process_batch(
        self,
        unify_crs: bool = True,
        target_crs: Union[str, int] = "EPSG:4326",
        crs_strategy: str = "auto_detect",
        fix_geometries: bool = True,
        geometry_options: Dict = None,
        merge_datasets: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Union[int, gpd.GeoDataFrame, Dict]]:
        """
        Complete batch processing pipeline.
        
        Args:
            unify_crs: Whether to unify CRS across datasets
            target_crs: Target CRS for unification
            crs_strategy: CRS unification strategy
            fix_geometries: Whether to fix geometries
            geometry_options: Options for geometry processing
            merge_datasets: Whether to merge all datasets
            progress_callback: Optional progress callback function
            
        Returns:
            Dictionary with processing results
        """
        if progress_callback:
            progress_callback(0, "Starting batch processing")
        
        results = {
            'total_datasets': len(self.datasets),
            'processing_steps': [],
            'final_dataset': None,
            'success': True
        }
        
        try:
            # Step 1: Validate batch
            if progress_callback:
                progress_callback(10, "Validating datasets")
            
            validation_results = self.validate_batch()
            results['processing_steps'].append({
                'step': 'validation',
                'success': True,
                'results': validation_results
            })
            
            # Step 2: Unify CRS if requested
            if unify_crs:
                if progress_callback:
                    progress_callback(30, "Unifying CRS")
                
                crs_results = self.unify_crs(target_crs, crs_strategy)
                results['processing_steps'].append({
                    'step': 'crs_unification',
                    'success': crs_results['unified'] > 0,
                    'results': crs_results
                })
            
            # Step 3: Fix geometries if requested
            if fix_geometries:
                if progress_callback:
                    progress_callback(60, "Fixing geometries")
                
                geometry_options = geometry_options or {}
                geom_results = self.fix_geometries_batch(**geometry_options)
                results['processing_steps'].append({
                    'step': 'geometry_fixing',
                    'success': geom_results['processed'] > 0,
                    'results': geom_results
                })
            
            # Step 4: Merge datasets if requested
            if merge_datasets:
                if progress_callback:
                    progress_callback(90, "Merging datasets")
                
                merged_gdf, merge_report = self.merge_datasets()
                results['final_dataset'] = merged_gdf
                results['processing_steps'].append({
                    'step': 'dataset_merging',
                    'success': True,
                    'results': merge_report
                })
            
            if progress_callback:
                progress_callback(100, "Batch processing complete")
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            if progress_callback:
                progress_callback(100, f"Batch processing failed: {str(e)}")
        
        return results
    
    def get_dataset_summary(self) -> List[Dict[str, Union[str, int, bool]]]:
        """
        Get summary information for all datasets.
        
        Returns:
            List of dataset summaries
        """
        summaries = []
        
        for dataset in self.datasets:
            gdf = dataset['gdf']
            crs_info = get_crs_info(gdf) if gdf.crs is not None else None
            
            summary = {
                'name': dataset['name'],
                'index': dataset['index'],
                'feature_count': len(gdf),
                'has_crs': gdf.crs is not None,
                'crs_epsg': crs_info['epsg'] if crs_info else None,
                'crs_name': crs_info['name'] if crs_info else None,
                'geometry_types': list(gdf.geom_type.unique()) if not gdf.empty else [],
                'invalid_geometries': int((~gdf.geometry.is_valid).sum()) if not gdf.empty else 0,
                'empty_geometries': int(gdf.geometry.is_empty.sum()) if not gdf.empty else 0
            }
            
            summaries.append(summary)
        
        return summaries
    
    def clear(self):
        """Clear all datasets from the processor."""
        self.datasets = []
        self.validation_reports = []
        self.processing_reports = []
