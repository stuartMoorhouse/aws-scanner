"""Pytest configuration and fixtures."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from typing import List, Dict, Any

from aws_scanner.types import Resource
from aws_scanner.config import ScannerConfig


@pytest.fixture
def mock_boto_client():
    """Create a mock boto3 client."""
    client = MagicMock()
    client.get_paginator = MagicMock()
    return client


@pytest.fixture
def sample_ec2_instance():
    """Sample EC2 instance data from AWS API."""
    return {
        'InstanceId': 'i-1234567890abcdef0',
        'InstanceType': 't3.micro',
        'State': {'Name': 'running'},
        'LaunchTime': datetime(2024, 1, 1, 12, 0, 0),
        'PublicIpAddress': '1.2.3.4',
        'PrivateIpAddress': '10.0.0.1',
        'VpcId': 'vpc-12345',
        'SubnetId': 'subnet-12345',
        'Placement': {'AvailabilityZone': 'us-east-1a'},
        'Tags': [
            {'Key': 'Name', 'Value': 'test-instance'},
            {'Key': 'Environment', 'Value': 'test'}
        ]
    }


@pytest.fixture
def sample_ebs_volume():
    """Sample EBS volume data from AWS API."""
    return {
        'VolumeId': 'vol-1234567890abcdef0',
        'VolumeType': 'gp3',
        'Size': 100,
        'State': 'in-use',
        'CreateTime': datetime(2024, 1, 1, 12, 0, 0),
        'Encrypted': True,
        'AvailabilityZone': 'us-east-1a',
        'Attachments': [
            {
                'InstanceId': 'i-1234567890abcdef0',
                'Device': '/dev/sda1',
                'State': 'attached'
            }
        ],
        'Tags': [
            {'Key': 'Name', 'Value': 'test-volume'}
        ]
    }


@pytest.fixture
def sample_s3_bucket():
    """Sample S3 bucket data from AWS API."""
    return {
        'Name': 'test-bucket-12345',
        'CreationDate': datetime(2024, 1, 1, 12, 0, 0)
    }


@pytest.fixture
def sample_lambda_function():
    """Sample Lambda function data from AWS API."""
    return {
        'FunctionName': 'test-function',
        'FunctionArn': 'arn:aws:lambda:us-east-1:123456789012:function:test-function',
        'Runtime': 'python3.9',
        'MemorySize': 256,
        'Timeout': 30,
        'Handler': 'lambda_function.lambda_handler',
        'CodeSize': 1024,
        'LastModified': '2024-01-01T12:00:00.000+0000',
        'State': 'Active',
        'Architectures': ['x86_64'],
        'Environment': {
            'Variables': {
                'ENV': 'test'
            }
        }
    }


@pytest.fixture
def mock_scanner_config():
    """Create a mock scanner configuration."""
    return ScannerConfig(
        max_concurrent_regions=2,
        max_concurrent_services=2,
        max_retries=2,
        retry_delay=0.1,
        retry_backoff=2.0,
        requests_per_second=10.0,
        skip_regions=['us-west-2'],
        only_regions=None,
        log_level='INFO'
    )


@pytest.fixture
def sample_resources():
    """Sample list of resources for testing."""
    return [
        Resource(
            id='i-1234567890abcdef0',
            type='Instance',
            service='EC2',
            name='web-server',
            region='us-east-1',
            created_at=datetime(2024, 1, 1),
            state='running',
            estimated_monthly_cost=7.50,
            additional_info={'instanceType': 't3.micro'}
        ),
        Resource(
            id='vol-1234567890abcdef0',
            type='EBS Volume',
            service='EC2',
            name='data-volume',
            region='us-east-1',
            created_at=datetime(2024, 1, 1),
            state='in-use',
            estimated_monthly_cost=8.00,
            additional_info={'size': 100, 'volumeType': 'gp3'}
        ),
        Resource(
            id='test-bucket',
            type='Bucket',
            service='S3',
            name='test-bucket',
            region='global',
            created_at=datetime(2024, 1, 1),
            state='available',
            estimated_monthly_cost=2.30,
            additional_info={'objectCount': 1000, 'totalSize': 100.0}
        )
    ]


@pytest.fixture(autouse=True)
def reset_config():
    """Reset global config before each test."""
    from aws_scanner import config
    config._config = None
    yield
    config._config = None


@pytest.fixture
def mock_aws_regions():
    """Mock AWS regions response."""
    return {
        'Regions': [
            {'RegionName': 'us-east-1'},
            {'RegionName': 'us-west-1'},
            {'RegionName': 'eu-west-1'}
        ]
    }