"""Unit tests for main script."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import argparse

from scan_aws import (
    parse_arguments,
    get_all_regions,
    generate_markdown_report,
    display_summary,
    scan_services_concurrently
)
from aws_scanner.types import Resource


class TestParseArguments:
    """Test cases for argument parsing."""
    
    def test_default_arguments(self):
        """Test default argument values."""
        with patch('sys.argv', ['scan_aws.py']):
            args = parse_arguments()
            
            assert args.regions is None
            assert args.skip_regions is None
            assert args.services is None
            assert args.skip_services is None
            assert args.output == 'aws-resources-report.md'
            assert args.format == 'markdown'
            assert args.log_level == 'INFO'
            assert args.config is None
            assert args.no_progress is False
    
    def test_custom_arguments(self):
        """Test custom argument values."""
        with patch('sys.argv', [
            'scan_aws.py',
            '--regions', 'us-east-1', 'us-west-2',
            '--skip-services', 'EC2',
            '--output', 'custom-report.md',
            '--log-level', 'DEBUG',
            '--no-progress'
        ]):
            args = parse_arguments()
            
            assert args.regions == ['us-east-1', 'us-west-2']
            assert args.skip_services == ['EC2']
            assert args.output == 'custom-report.md'
            assert args.log_level == 'DEBUG'
            assert args.no_progress is True


class TestGetAllRegions:
    """Test cases for get_all_regions function."""
    
    @patch('boto3.client')
    def test_get_all_regions_success(self, mock_boto_client, mock_aws_regions):
        """Test successful region fetching."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_regions.return_value = mock_aws_regions
        
        regions = get_all_regions()
        
        assert len(regions) == 3
        assert 'us-east-1' in regions
        assert 'us-west-1' in regions
        assert 'eu-west-1' in regions
        assert regions == sorted(regions)  # Should be sorted
    
    @patch('boto3.client')
    def test_get_all_regions_error(self, mock_boto_client):
        """Test region fetching with error."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_regions.side_effect = Exception('API Error')
        
        with pytest.raises(Exception):
            get_all_regions()


class TestGenerateMarkdownReport:
    """Test cases for markdown report generation."""
    
    def test_empty_resources(self):
        """Test report generation with no resources."""
        report = generate_markdown_report([])
        
        assert '# AWS Resources Report' in report
        assert 'No resources found.' in report
        assert 'Total Resources Found: 0' in report
    
    def test_report_with_resources(self, sample_resources):
        """Test report generation with resources."""
        report = generate_markdown_report(sample_resources)
        
        # Check header
        assert '# AWS Resources Report' in report
        assert 'Total Resources Found: 3' in report
        assert 'Total Estimated Monthly Cost: $17.80' in report
        
        # Check table of contents
        assert '## Table of Contents' in report
        assert '- [EC2](#ec2)' in report
        assert '- [S3](#s3)' in report
        
        # Check summary table
        assert '## Summary by Service' in report
        assert '| EC2 | 2 | $15.50 |' in report
        assert '| S3 | 1 | $2.30 |' in report
        
        # Check resource details
        assert '## EC2' in report
        assert '### us-east-1' in report
        assert 'i-1234567890abcdef0' in report
        assert 'web-server' in report
        
        # Check cost breakdown
        assert '## Cost Breakdown' in report
        assert '### Top 10 Most Expensive Resources' in report
    
    def test_report_formatting(self, sample_resources):
        """Test markdown formatting in report."""
        report = generate_markdown_report(sample_resources)
        
        # Check for proper markdown table formatting
        assert '|---------|----------------|----------------------|' in report
        assert '| Type | ID | Name | State | Monthly Cost | Details |' in report
        
        # Check timestamp format
        assert '**Generated:**' in report
        assert 'T' in report  # ISO format timestamp
    
    def test_report_cost_sorting(self):
        """Test that top expensive resources are sorted correctly."""
        resources = [
            Resource(
                id='cheap',
                type='Instance',
                service='EC2',
                region='us-east-1',
                estimated_monthly_cost=1.00
            ),
            Resource(
                id='expensive',
                type='Instance',
                service='EC2',
                region='us-east-1',
                estimated_monthly_cost=100.00
            ),
            Resource(
                id='medium',
                type='Instance',
                service='EC2',
                region='us-east-1',
                estimated_monthly_cost=50.00
            )
        ]
        
        report = generate_markdown_report(resources)
        
        # Check order in top expensive resources
        lines = report.split('\n')
        expensive_section_start = False
        resource_lines = []
        
        for line in lines:
            if '### Top 10 Most Expensive Resources' in line:
                expensive_section_start = True
            elif expensive_section_start and '| EC2' in line:
                resource_lines.append(line)
        
        # Most expensive should be first
        assert 'expensive' in resource_lines[0]
        assert 'medium' in resource_lines[1]
        assert 'cheap' in resource_lines[2]


class TestDisplaySummary:
    """Test cases for display summary function."""
    
    @patch('scan_aws.console')
    def test_display_summary_empty(self, mock_console):
        """Test displaying summary with no resources."""
        display_summary([])
        
        # Should print warning about no resources
        mock_console.print.assert_called()
        calls = [call[0][0] for call in mock_console.print.call_args_list]
        assert any('[yellow]No resources found.[/yellow]' in str(call) for call in calls)
    
    @patch('scan_aws.console')
    def test_display_summary_with_resources(self, mock_console, sample_resources):
        """Test displaying summary with resources."""
        display_summary(sample_resources)
        
        # Should create and print a table
        mock_console.print.assert_called()
        
        # Check that table was created (Rich Table object)
        table_printed = False
        for call in mock_console.print.call_args_list:
            if len(call[0]) > 0:
                arg = call[0][0]
                if hasattr(arg, 'columns'):  # Rich Table has columns
                    table_printed = True
                    break
        
        assert table_printed


class TestScanServicesConcurrently:
    """Test cases for concurrent service scanning."""
    
    @patch('scan_aws.ThreadPoolExecutor')
    @patch('scan_aws.Progress')
    def test_scan_with_progress(self, mock_progress_class, mock_executor):
        """Test scanning with progress bar."""
        # Mock scanners
        scanner1 = Mock()
        scanner1.service_name = 'EC2'
        scanner1.scan_all_regions.return_value = [
            Resource(id='1', type='Instance', service='EC2', region='us-east-1')
        ]
        
        scanner2 = Mock()
        scanner2.service_name = 'S3'
        scanner2.scan_all_regions.return_value = [
            Resource(id='2', type='Bucket', service='S3', region='global')
        ]
        
        # Mock progress bar
        mock_progress = MagicMock()
        mock_progress_class.return_value.__enter__.return_value = mock_progress
        
        # Mock executor
        mock_context = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_context
        
        # Create futures
        from concurrent.futures import Future
        future1 = Future()
        future1.set_result(scanner1.scan_all_regions.return_value)
        future2 = Future()
        future2.set_result(scanner2.scan_all_regions.return_value)
        
        mock_context.submit.side_effect = [future1, future2]
        
        with patch('scan_aws.as_completed', return_value=[future1, future2]):
            resources = scan_services_concurrently([scanner1, scanner2], show_progress=True)
        
        assert len(resources) == 2
        mock_progress.add_task.assert_called_once()
        assert mock_progress.update.call_count >= 2  # Updated for each scanner
    
    @patch('scan_aws.ThreadPoolExecutor')
    def test_scan_without_progress(self, mock_executor):
        """Test scanning without progress bar."""
        scanner = Mock()
        scanner.service_name = 'EC2'
        scanner.scan_all_regions.return_value = []
        
        mock_context = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_context
        
        from concurrent.futures import Future
        future = Future()
        future.set_result([])
        mock_context.submit.return_value = future
        
        with patch('scan_aws.as_completed', return_value=[future]):
            resources = scan_services_concurrently([scanner], show_progress=False)
        
        assert resources == []
        scanner.scan_all_regions.assert_called_once()
    
    @patch('scan_aws.ThreadPoolExecutor')
    @patch('scan_aws.logger')
    def test_scan_with_error(self, mock_logger, mock_executor):
        """Test scanning with scanner error."""
        scanner = Mock()
        scanner.service_name = 'EC2'
        scanner.scan_all_regions.side_effect = Exception('Scanner failed')
        
        mock_context = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_context
        
        from concurrent.futures import Future
        future = Future()
        future.set_exception(Exception('Scanner failed'))
        mock_context.submit.return_value = future
        
        with patch('scan_aws.as_completed', return_value=[future]):
            resources = scan_services_concurrently([scanner], show_progress=False)
        
        assert resources == []
        mock_logger.error.assert_called_with('Failed to scan EC2: Scanner failed')