"""
Tests for the report module.
"""

import pytest
import json
from pathlib import Path
import tempfile

from geolint.core.report import (
    generate_report, generate_batch_report, format_report_for_display,
    save_report, load_report, create_summary_report
)


class TestGenerateReport:
    """Test report generation functionality."""
    
    def test_generate_report_basic(self, sample_validation_report):
        """Test basic report generation."""
        report = generate_report(sample_validation_report)
        
        assert isinstance(report, dict)
        assert 'geolint_version' in report
        assert 'timestamp' in report
        assert 'processing_summary' in report
        assert 'file_info' in report
        assert 'validation' in report
        assert 'health_score' in report
        
        assert report['geolint_version'] == '1.0.0'
        assert report['processing_summary']['status'] == 'completed'
        assert report['health_score'] >= 0
        assert report['health_score'] <= 100
    
    def test_generate_report_with_crs_info(self, sample_validation_report, sample_crs_info):
        """Test report generation with CRS information."""
        report = generate_report(sample_validation_report, crs_info=sample_crs_info)
        
        assert 'crs_info' in report
        assert report['crs_info'] == sample_crs_info
    
    def test_generate_report_with_geometry_report(self, sample_validation_report, sample_geometry_report):
        """Test report generation with geometry processing report."""
        report = generate_report(sample_validation_report, geometry_report=sample_geometry_report)
        
        assert 'geometry_processing' in report
        assert report['geometry_processing'] == sample_geometry_report
    
    def test_generate_report_with_transform_report(self, sample_validation_report, sample_transform_report):
        """Test report generation with transformation report."""
        report = generate_report(sample_validation_report, transform_report=sample_transform_report)
        
        assert 'transformation' in report
        assert report['transformation'] == sample_transform_report
    
    def test_generate_report_with_processing_options(self, sample_validation_report):
        """Test report generation with processing options."""
        processing_options = {
            'fix_invalid': True,
            'remove_empty': True,
            'target_crs': 'EPSG:4326'
        }
        
        report = generate_report(sample_validation_report, processing_options=processing_options)
        
        assert 'processing_options' in report
        assert report['processing_options'] == processing_options
    
    def test_generate_report_health_score_calculation(self):
        """Test health score calculation."""
        # Perfect dataset
        perfect_report = {
            'validation': {
                'crs_present': True,
                'has_issues': False
            },
            'geometry_validation': {
                'invalid_count': 0,
                'empty_count': 0,
                'mixed_types': False
            },
            'warnings': [],
            'errors': []
        }
        
        report = generate_report(perfect_report)
        assert report['health_score'] == 100
        
        # Dataset with issues
        issues_report = {
            'validation': {
                'crs_present': False,
                'has_issues': True
            },
            'geometry_validation': {
                'invalid_count': 5,
                'empty_count': 2,
                'mixed_types': True
            },
            'warnings': ['No CRS information found', 'Invalid geometries found'],
            'errors': []
        }
        
        report = generate_report(issues_report)
        assert report['health_score'] < 100
        assert report['health_score'] >= 0


class TestGenerateBatchReport:
    """Test batch report generation functionality."""
    
    def test_generate_batch_report_success(self, sample_batch_processor):
        """Test batch report generation for successful processing."""
        batch_results = {
            'total_datasets': 2,
            'success': True,
            'processing_steps': [
                {'step': 'validation', 'success': True},
                {'step': 'crs_unification', 'success': True},
                {'step': 'geometry_fixing', 'success': True}
            ],
            'final_dataset': 'some_dataset'
        }
        
        individual_reports = [
            {'health_score': 90, 'file_info': {'feature_count': 10}},
            {'health_score': 85, 'file_info': {'feature_count': 15}}
        ]
        
        report = generate_batch_report(batch_results, individual_reports)
        
        assert isinstance(report, dict)
        assert 'geolint_version' in report
        assert 'timestamp' in report
        assert 'batch_summary' in report
        assert 'processing_steps' in report
        assert 'individual_reports' in report
        assert 'aggregate_statistics' in report
        
        assert report['batch_summary']['total_datasets'] == 2
        assert report['batch_summary']['success'] is True
        assert report['batch_summary']['processing_steps'] == 3
        assert report['batch_summary']['final_dataset_created'] is True
    
    def test_generate_batch_report_failure(self):
        """Test batch report generation for failed processing."""
        batch_results = {
            'total_datasets': 2,
            'success': False,
            'error': 'Processing failed',
            'processing_steps': []
        }
        
        report = generate_batch_report(batch_results)
        
        assert report['batch_summary']['success'] is False
        assert 'error' in report
        assert report['error'] == 'Processing failed'
    
    def test_generate_batch_report_no_individual_reports(self):
        """Test batch report generation without individual reports."""
        batch_results = {
            'total_datasets': 2,
            'success': True,
            'processing_steps': []
        }
        
        report = generate_batch_report(batch_results)
        
        assert report['individual_reports'] == []
        assert report['aggregate_statistics'] == {}


class TestFormatReportForDisplay:
    """Test report formatting for display functionality."""
    
    def test_format_report_for_display(self, sample_validation_report):
        """Test formatting report for display."""
        report = generate_report(sample_validation_report)
        formatted = format_report_for_display(report)
        
        assert isinstance(formatted, dict)
        assert 'summary' in formatted
        assert 'validation' in formatted
        assert 'issues' in formatted
        assert 'processing' in formatted
        
        # Check summary structure
        summary = formatted['summary']
        assert 'file_name' in summary
        assert 'feature_count' in summary
        assert 'health_score' in summary
        assert 'status' in summary
        
        # Check validation structure
        validation = formatted['validation']
        assert 'crs_present' in validation
        assert 'crs_info' in validation
        assert 'geometry_stats' in validation
        
        # Check issues structure
        issues = formatted['issues']
        assert 'warnings' in issues
        assert 'errors' in issues
        assert 'total_issues' in issues


class TestSaveAndLoadReport:
    """Test report saving and loading functionality."""
    
    def test_save_and_load_report(self, sample_validation_report):
        """Test saving and loading a report."""
        report = generate_report(sample_validation_report)
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp_file:
            report_path = Path(tmp_file.name)
        
        try:
            # Save report
            save_report(report, report_path)
            assert report_path.exists()
            
            # Load report
            loaded_report = load_report(report_path)
            assert isinstance(loaded_report, dict)
            assert loaded_report['geolint_version'] == report['geolint_version']
            assert loaded_report['health_score'] == report['health_score']
            
        finally:
            # Cleanup
            report_path.unlink(missing_ok=True)
    
    def test_save_report_nonexistent_directory(self, sample_validation_report):
        """Test saving report to non-existent directory."""
        report = generate_report(sample_validation_report)
        
        # Create path with non-existent directory
        report_path = Path("nonexistent/directory/report.json")
        
        # Should create directory
        save_report(report, report_path)
        assert report_path.exists()
        
        # Cleanup
        report_path.unlink(missing_ok=True)
        report_path.parent.rmdir()
        report_path.parent.parent.rmdir()


class TestCreateSummaryReport:
    """Test summary report creation functionality."""
    
    def test_create_summary_report(self, sample_validation_report):
        """Test creating summary report from multiple reports."""
        reports = [
            generate_report(sample_validation_report),
            generate_report(sample_validation_report),
            generate_report(sample_validation_report)
        ]
        
        summary = create_summary_report(reports)
        
        assert isinstance(summary, dict)
        assert 'geolint_version' in summary
        assert 'timestamp' in summary
        assert 'summary' in summary
        assert 'health_scores' in summary
        assert 'crs_distribution' in summary
        assert 'individual_reports' in summary
        
        # Check summary statistics
        assert summary['summary']['total_files'] == 3
        assert summary['summary']['total_features'] > 0
        assert summary['summary']['files_with_issues'] >= 0
        assert summary['summary']['total_warnings'] >= 0
        assert summary['summary']['total_errors'] >= 0
        
        # Check health score distribution
        health_scores = summary['health_scores']
        assert 'average' in health_scores
        assert 'min' in health_scores
        assert 'max' in health_scores
        assert 'distribution' in health_scores
        
        # Check distribution categories
        distribution = health_scores['distribution']
        assert 'excellent' in distribution
        assert 'good' in distribution
        assert 'fair' in distribution
        assert 'poor' in distribution
    
    def test_create_summary_report_empty_list(self):
        """Test creating summary report from empty list."""
        summary = create_summary_report([])
        
        assert isinstance(summary, dict)
        assert 'error' in summary
        assert summary['error'] == 'No reports provided'
    
    def test_create_summary_report_single_report(self, sample_validation_report):
        """Test creating summary report from single report."""
        report = generate_report(sample_validation_report)
        summary = create_summary_report([report])
        
        assert isinstance(summary, dict)
        assert summary['summary']['total_files'] == 1
        assert summary['individual_reports'] == [report]
