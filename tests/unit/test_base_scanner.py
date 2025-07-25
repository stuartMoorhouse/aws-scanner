"""Unit tests for base scanner."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import Future
from typing import List

from aws_scanner.scanners.base_scanner import BaseScanner, ScanResult
from aws_scanner.types import Resource


class TestScanner(BaseScanner):
    """Test implementation of BaseScanner."""
    
    @property
    def service_name(self) -> str:
        return 'TestService'
    
    def scan_single_region(self, region: str) -> List[Resource]:
        """Mock implementation."""
        if region == 'error-region':
            raise Exception('Test error')
        
        if region == 'empty-region':
            return []
        
        return [
            Resource(
                id=f'test-resource-{region}',
                type='TestResource',
                service='TestService',
                name=f'Test in {region}',
                region=region,
                estimated_monthly_cost=10.0
            )
        ]


class TestBaseScanner:
    """Test cases for BaseScanner."""
    
    def test_scanner_initialization(self):
        """Test scanner initialization."""
        regions = ['us-east-1', 'us-west-2']
        scanner = TestScanner(regions)
        
        assert scanner.regions == regions
        assert scanner.service_name == 'TestService'
        assert scanner.config is not None
        assert scanner.rate_limiter is not None
    
    def test_filter_regions_with_skip(self, mock_scanner_config):
        """Test region filtering with skip_regions."""
        mock_scanner_config.skip_regions = ['us-west-2']
        
        with patch('aws_scanner.config.get_config', return_value=mock_scanner_config):
            scanner = TestScanner(['us-east-1', 'us-west-2', 'eu-west-1'])
            filtered = scanner._filter_regions(scanner.regions)
            
            assert 'us-west-2' not in filtered
            assert 'us-east-1' in filtered
            assert 'eu-west-1' in filtered
    
    def test_filter_regions_with_only(self, mock_scanner_config):
        """Test region filtering with only_regions."""
        mock_scanner_config.only_regions = ['us-east-1']
        
        with patch('aws_scanner.config.get_config', return_value=mock_scanner_config):
            scanner = TestScanner(['us-east-1', 'us-west-2', 'eu-west-1'])
            filtered = scanner._filter_regions(scanner.regions)
            
            assert filtered == ['us-east-1']
    
    def test_scan_single_region_success(self):
        """Test successful single region scan."""
        scanner = TestScanner(['us-east-1'])
        resources = scanner.scan_single_region('us-east-1')
        
        assert len(resources) == 1
        assert resources[0].id == 'test-resource-us-east-1'
        assert resources[0].region == 'us-east-1'
    
    def test_scan_single_region_empty(self):
        """Test scanning region with no resources."""
        scanner = TestScanner(['empty-region'])
        resources = scanner.scan_single_region('empty-region')
        
        assert resources == []
    
    def test_scan_region_with_error_handling(self):
        """Test error handling in region scan."""
        scanner = TestScanner(['error-region'])
        result = scanner._scan_region_with_error_handling('error-region')
        
        assert isinstance(result, ScanResult)
        assert result.region == 'error-region'
        assert result.resources == []
        assert result.error is not None
        assert str(result.error) == 'Test error'
    
    @patch('aws_scanner.scanners.base_scanner.ThreadPoolExecutor')
    def test_scan_all_regions_concurrent(self, mock_executor):
        """Test concurrent scanning of all regions."""
        # Mock the executor
        mock_context = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_context
        
        # Create futures for results
        future1 = Future()
        future1.set_result(ScanResult(
            region='us-east-1',
            resources=[Resource(
                id='resource1',
                type='Test',
                service='TestService',
                region='us-east-1',
                estimated_monthly_cost=10.0
            )]
        ))
        
        future2 = Future()
        future2.set_result(ScanResult(
            region='us-west-2',
            resources=[Resource(
                id='resource2',
                type='Test',
                service='TestService',
                region='us-west-2',
                estimated_monthly_cost=20.0
            )]
        ))
        
        mock_context.submit.side_effect = [future1, future2]
        
        # Test scanning
        scanner = TestScanner(['us-east-1', 'us-west-2'])
        
        with patch.object(scanner, '_scan_region_with_error_handling') as mock_scan:
            mock_scan.side_effect = [
                ScanResult(region='us-east-1', resources=[]),
                ScanResult(region='us-west-2', resources=[])
            ]
            
            # Patch as_completed to return our futures
            with patch('aws_scanner.scanners.base_scanner.as_completed', 
                      return_value=[future1, future2]):
                resources = scanner.scan_all_regions()
                
                # Verify thread pool was created with correct max_workers
                mock_executor.assert_called_once()
                call_kwargs = mock_executor.call_args[1]
                assert call_kwargs['max_workers'] == scanner.config.max_concurrent_regions
    
    def test_scan_all_regions_with_errors(self):
        """Test scanning with some regions failing."""
        scanner = TestScanner(['us-east-1', 'error-region', 'eu-west-1'])
        
        # Mock concurrent execution to run sequentially for testing
        with patch('aws_scanner.scanners.base_scanner.ThreadPoolExecutor') as mock_executor:
            # Make executor run tasks immediately
            mock_executor.return_value.__enter__.return_value.submit.side_effect = \
                lambda fn, *args: Mock(result=lambda: fn(*args))
            
            with patch('aws_scanner.scanners.base_scanner.as_completed') as mock_completed:
                # Create futures for our results
                futures = []
                for region in scanner.regions:
                    future = Mock()
                    future.result.return_value = scanner._scan_region_with_error_handling(region)
                    futures.append(future)
                
                mock_completed.return_value = futures
                
                resources = scanner.scan_all_regions()
                
                # Should get resources from successful regions only
                assert len(resources) == 2
                assert all(r.region in ['us-east-1', 'eu-west-1'] for r in resources)
    
    def test_rate_limiter_integration(self, mock_scanner_config):
        """Test that rate limiter is used during scanning."""
        mock_scanner_config.requests_per_second = 1.0
        
        with patch('aws_scanner.config.get_config', return_value=mock_scanner_config):
            scanner = TestScanner(['us-east-1'])
            
            with patch.object(scanner.rate_limiter, 'acquire') as mock_acquire:
                scanner._scan_region_with_error_handling('us-east-1')
                mock_acquire.assert_called_once()
    
    def test_handle_error(self):
        """Test error handling method."""
        from botocore.exceptions import ClientError
        
        scanner = TestScanner(['us-east-1'])
        
        # Test with ClientError
        error = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'Access denied'}},
            'DescribeInstances'
        )
        
        with patch('aws_scanner.utils.handle_aws_error') as mock_handle:
            scanner.handle_error(error, 'test context')
            mock_handle.assert_called_once_with(error, 'test context')
    
    def test_abstract_methods_not_implemented(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            # Can't instantiate abstract class without implementing abstract methods
            class BadScanner(BaseScanner):
                pass
            
            BadScanner(['us-east-1'])