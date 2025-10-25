"""
Report generation and aggregation for GeoLint.

Handles JSON report creation, batch report aggregation, and display formatting.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union, Any

import pandas as pd


def generate_report(
    validation_report: Dict,
    crs_info: Dict = None,
    geometry_report: Dict = None,
    transform_report: Dict = None,
    processing_options: Dict = None
) -> Dict[str, Any]:
    """
    Generate a comprehensive JSON report for a single dataset.
    
    Args:
        validation_report: Validation results from run_validation
        crs_info: CRS information from get_crs_info
        geometry_report: Geometry processing results
        transform_report: Transformation results
        processing_options: Options used for processing
        
    Returns:
        Comprehensive JSON report
    """
    report = {
        'geolint_version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'processing_summary': {
            'status': 'completed',
            'has_issues': validation_report.get('validation', {}).get('has_issues', False),
            'issues_found': len(validation_report.get('warnings', [])) + len(validation_report.get('errors', []))
        },
        'file_info': {
            'file_path': validation_report.get('file_path', ''),
            'file_name': validation_report.get('file_name', ''),
            'file_size': validation_report.get('file_size', 0),
            'feature_count': validation_report.get('validation', {}).get('feature_count', 0),
            'column_count': validation_report.get('validation', {}).get('column_count', 0)
        },
        'validation': validation_report.get('validation', {}),
        'shapefile_bundle': validation_report.get('shapefile_bundle', {}),
        'geometry_validation': validation_report.get('geometry_validation', {}),
        'warnings': validation_report.get('warnings', []),
        'errors': validation_report.get('errors', [])
    }
    
    # Add CRS information if provided
    if crs_info:
        report['crs_info'] = crs_info
    
    # Add geometry processing results if provided
    if geometry_report:
        report['geometry_processing'] = geometry_report
    
    # Add transformation results if provided
    if transform_report:
        report['transformation'] = transform_report
    
    # Add processing options if provided
    if processing_options:
        report['processing_options'] = processing_options
    
    # Calculate overall health score
    report['health_score'] = _calculate_health_score(report)
    
    return report


def generate_batch_report(
    batch_results: Dict,
    individual_reports: List[Dict] = None
) -> Dict[str, Any]:
    """
    Generate an aggregate report for batch processing.
    
    Args:
        batch_results: Results from BatchProcessor.process_batch
        individual_reports: List of individual dataset reports
        
    Returns:
        Comprehensive batch report
    """
    report = {
        'geolint_version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'batch_summary': {
            'total_datasets': batch_results.get('total_datasets', 0),
            'success': batch_results.get('success', False),
            'processing_steps': len(batch_results.get('processing_steps', [])),
            'final_dataset_created': batch_results.get('final_dataset') is not None
        },
        'processing_steps': batch_results.get('processing_steps', []),
        'individual_reports': individual_reports or [],
        'aggregate_statistics': _calculate_aggregate_statistics(batch_results, individual_reports)
    }
    
    # Add error information if processing failed
    if not batch_results.get('success', True):
        report['error'] = batch_results.get('error', 'Unknown error')
    
    return report


def _calculate_health_score(report: Dict) -> float:
    """
    Calculate a health score (0-100) for the dataset.
    
    Args:
        report: Dataset report
        
    Returns:
        Health score between 0 and 100
    """
    score = 100.0
    
    # Deduct points for issues
    validation = report.get('validation', {})
    geometry_validation = report.get('geometry_validation', {})
    
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
    shapefile_bundle = report.get('shapefile_bundle', {})
    if not shapefile_bundle.get('is_complete', True):
        score -= 10
    
    # Warnings and errors
    warnings_count = len(report.get('warnings', []))
    errors_count = len(report.get('errors', []))
    
    score -= warnings_count * 2  # -2 points per warning
    score -= errors_count * 5    # -5 points per error
    
    return max(0, min(100, score))


def _calculate_aggregate_statistics(
    batch_results: Dict, 
    individual_reports: List[Dict] = None
) -> Dict[str, Any]:
    """
    Calculate aggregate statistics for batch processing.
    
    Args:
        batch_results: Batch processing results
        individual_reports: Individual dataset reports
        
    Returns:
        Aggregate statistics
    """
    if not individual_reports:
        return {}
    
    # Calculate aggregate metrics
    total_features = sum(
        report.get('file_info', {}).get('feature_count', 0) 
        for report in individual_reports
    )
    
    total_warnings = sum(
        len(report.get('warnings', [])) 
        for report in individual_reports
    )
    
    total_errors = sum(
        len(report.get('errors', [])) 
        for report in individual_reports
    )
    
    # CRS distribution
    crs_counts = {}
    for report in individual_reports:
        crs_info = report.get('crs_info', {})
        if crs_info and crs_info.get('epsg'):
            epsg = crs_info['epsg']
            crs_counts[epsg] = crs_counts.get(epsg, 0) + 1
    
    # Health scores
    health_scores = [
        report.get('health_score', 0) 
        for report in individual_reports
    ]
    
    return {
        'total_features': total_features,
        'total_warnings': total_warnings,
        'total_errors': total_errors,
        'crs_distribution': crs_counts,
        'health_scores': {
            'average': sum(health_scores) / len(health_scores) if health_scores else 0,
            'min': min(health_scores) if health_scores else 0,
            'max': max(health_scores) if health_scores else 0
        },
        'datasets_with_issues': sum(
            1 for report in individual_reports 
            if report.get('processing_summary', {}).get('has_issues', False)
        )
    }


def format_report_for_display(report: Dict) -> Dict[str, Any]:
    """
    Format a report for display in Streamlit UI.
    
    Args:
        report: Raw report dictionary
        
    Returns:
        Formatted report for UI display
    """
    formatted = {
        'summary': {
            'file_name': report.get('file_info', {}).get('file_name', 'Unknown'),
            'feature_count': report.get('file_info', {}).get('feature_count', 0),
            'health_score': report.get('health_score', 0),
            'status': '✅ Clean' if report.get('health_score', 0) >= 80 else 
                     '⚠️ Issues Found' if report.get('health_score', 0) >= 50 else '❌ Major Issues'
        },
        'validation': {
            'crs_present': report.get('validation', {}).get('crs_present', False),
            'crs_info': report.get('crs_info', {}),
            'geometry_stats': {
                'valid': report.get('geometry_validation', {}).get('valid_count', 0),
                'invalid': report.get('geometry_validation', {}).get('invalid_count', 0),
                'empty': report.get('geometry_validation', {}).get('empty_count', 0),
                'mixed_types': report.get('geometry_validation', {}).get('mixed_types', False),
                'geometry_types': report.get('geometry_validation', {}).get('geometry_types', [])
            }
        },
        'issues': {
            'warnings': report.get('warnings', []),
            'errors': report.get('errors', []),
            'total_issues': len(report.get('warnings', [])) + len(report.get('errors', []))
        },
        'processing': {
            'geometry_processing': report.get('geometry_processing', {}),
            'transformation': report.get('transformation', {})
        }
    }
    
    return formatted


def save_report(report: Dict, output_path: Union[str, Path]) -> None:
    """
    Save a report to a JSON file.
    
    Args:
        report: Report dictionary to save
        output_path: Path to save the report
    """
    output_path = Path(output_path)
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def load_report(report_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load a report from a JSON file.
    
    Args:
        report_path: Path to the report file
        
    Returns:
        Loaded report dictionary
    """
    report_path = Path(report_path)
    
    with open(report_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_summary_report(reports: List[Dict]) -> Dict[str, Any]:
    """
    Create a summary report from multiple individual reports.
    
    Args:
        reports: List of individual dataset reports
        
    Returns:
        Summary report
    """
    if not reports:
        return {'error': 'No reports provided'}
    
    # Calculate summary statistics
    total_files = len(reports)
    total_features = sum(
        report.get('file_info', {}).get('feature_count', 0) 
        for report in reports
    )
    
    files_with_issues = sum(
        1 for report in reports 
        if report.get('processing_summary', {}).get('has_issues', False)
    )
    
    total_warnings = sum(
        len(report.get('warnings', [])) 
        for report in reports
    )
    
    total_errors = sum(
        len(report.get('errors', [])) 
        for report in reports
    )
    
    # Health score distribution
    health_scores = [report.get('health_score', 0) for report in reports]
    
    # CRS distribution
    crs_distribution = {}
    for report in reports:
        crs_info = report.get('crs_info', {})
        if crs_info and crs_info.get('epsg'):
            epsg = crs_info['epsg']
            crs_distribution[epsg] = crs_distribution.get(epsg, 0) + 1
    
    return {
        'geolint_version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_files': total_files,
            'total_features': total_features,
            'files_with_issues': files_with_issues,
            'total_warnings': total_warnings,
            'total_errors': total_errors
        },
        'health_scores': {
            'average': sum(health_scores) / len(health_scores) if health_scores else 0,
            'min': min(health_scores) if health_scores else 0,
            'max': max(health_scores) if health_scores else 0,
            'distribution': {
                'excellent': sum(1 for score in health_scores if score >= 90),
                'good': sum(1 for score in health_scores if 70 <= score < 90),
                'fair': sum(1 for score in health_scores if 50 <= score < 70),
                'poor': sum(1 for score in health_scores if score < 50)
            }
        },
        'crs_distribution': crs_distribution,
        'individual_reports': reports
    }
