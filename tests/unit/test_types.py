"""Unit tests for types module."""
import pytest
from datetime import datetime
from dataclasses import asdict

from aws_scanner.types import Resource, ScanResult, ServiceSummary


class TestResource:
    """Test cases for Resource dataclass."""
    
    def test_resource_creation_minimal(self):
        """Test creating resource with minimal fields."""
        resource = Resource(
            id='test-id',
            type='TestType',
            service='TestService',
            region='us-east-1'
        )
        
        assert resource.id == 'test-id'
        assert resource.type == 'TestType'
        assert resource.service == 'TestService'
        assert resource.region == 'us-east-1'
        assert resource.name is None
        assert resource.created_at is None
        assert resource.state is None
        assert resource.estimated_monthly_cost is None
        assert resource.additional_info == {}
    
    def test_resource_creation_full(self):
        """Test creating resource with all fields."""
        created_at = datetime(2024, 1, 1, 12, 0, 0)
        additional_info = {'key': 'value', 'nested': {'data': 123}}
        
        resource = Resource(
            id='test-id',
            type='TestType',
            service='TestService',
            region='us-east-1',
            name='Test Resource',
            created_at=created_at,
            state='active',
            estimated_monthly_cost=99.99,
            additional_info=additional_info
        )
        
        assert resource.name == 'Test Resource'
        assert resource.created_at == created_at
        assert resource.state == 'active'
        assert resource.estimated_monthly_cost == 99.99
        assert resource.additional_info == additional_info
    
    def test_resource_equality(self):
        """Test resource equality comparison."""
        resource1 = Resource(
            id='test-id',
            type='TestType',
            service='TestService',
            region='us-east-1'
        )
        
        resource2 = Resource(
            id='test-id',
            type='TestType',
            service='TestService',
            region='us-east-1'
        )
        
        resource3 = Resource(
            id='different-id',
            type='TestType',
            service='TestService',
            region='us-east-1'
        )
        
        assert resource1 == resource2
        assert resource1 != resource3
    
    def test_resource_as_dict(self):
        """Test converting resource to dictionary."""
        resource = Resource(
            id='test-id',
            type='TestType',
            service='TestService',
            region='us-east-1',
            estimated_monthly_cost=50.0
        )
        
        resource_dict = asdict(resource)
        
        assert isinstance(resource_dict, dict)
        assert resource_dict['id'] == 'test-id'
        assert resource_dict['estimated_monthly_cost'] == 50.0
        assert resource_dict['additional_info'] == {}


class TestScanResult:
    """Test cases for ScanResult dataclass."""
    
    def test_scan_result_creation(self):
        """Test creating scan result."""
        resources = [
            Resource(id='1', type='Test', service='TestService', region='us-east-1'),
            Resource(id='2', type='Test', service='TestService', region='us-east-1')
        ]
        
        result = ScanResult(
            service='TestService',
            resources=resources,
            errors=['Error 1', 'Error 2'],
            scan_duration=1.23
        )
        
        assert result.service == 'TestService'
        assert len(result.resources) == 2
        assert len(result.errors) == 2
        assert result.scan_duration == 1.23
    
    def test_scan_result_empty(self):
        """Test creating empty scan result."""
        result = ScanResult(
            service='TestService',
            resources=[],
            errors=[],
            scan_duration=0.0
        )
        
        assert result.resources == []
        assert result.errors == []
        assert result.scan_duration == 0.0


class TestServiceSummary:
    """Test cases for ServiceSummary dataclass."""
    
    def test_service_summary_creation(self):
        """Test creating service summary."""
        summary = ServiceSummary(
            service='EC2',
            total_resources=10,
            total_estimated_monthly_cost=150.50,
            resources_by_region={'us-east-1': 5, 'us-west-2': 5}
        )
        
        assert summary.service == 'EC2'
        assert summary.total_resources == 10
        assert summary.total_estimated_monthly_cost == 150.50
        assert summary.resources_by_region['us-east-1'] == 5
        assert summary.resources_by_region['us-west-2'] == 5
    
    def test_service_summary_defaults(self):
        """Test service summary with default values."""
        summary = ServiceSummary(
            service='Lambda',
            total_resources=5
        )
        
        assert summary.service == 'Lambda'
        assert summary.total_resources == 5
        assert summary.total_estimated_monthly_cost is None
        assert summary.resources_by_region == {}
    
    def test_service_summary_modification(self):
        """Test modifying service summary."""
        summary = ServiceSummary(
            service='S3',
            total_resources=3
        )
        
        # Add region data
        summary.resources_by_region['us-east-1'] = 2
        summary.resources_by_region['eu-west-1'] = 1
        
        assert len(summary.resources_by_region) == 2
        assert summary.resources_by_region['us-east-1'] == 2