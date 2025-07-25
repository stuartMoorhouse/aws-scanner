"""Unit tests for EC2 scanner."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from botocore.exceptions import ClientError

from aws_scanner.scanners.ec2_scanner import EC2Scanner
from aws_scanner.types import Resource
from aws_scanner.utils import AWSAccessDeniedError


class TestEC2Scanner:
    """Test cases for EC2Scanner."""
    
    def test_scanner_properties(self):
        """Test scanner basic properties."""
        scanner = EC2Scanner(['us-east-1'])
        assert scanner.service_name == 'EC2'
    
    @patch('boto3.client')
    def test_scan_single_region_success(self, mock_boto_client, mock_boto_client_fixture):
        """Test successful scan of a single region."""
        mock_client = mock_boto_client_fixture
        mock_boto_client.return_value = mock_client
        
        scanner = EC2Scanner(['us-east-1'])
        
        # Mock the individual scan methods
        with patch.object(scanner, '_scan_instances') as mock_instances, \
             patch.object(scanner, '_scan_volumes') as mock_volumes, \
             patch.object(scanner, '_scan_snapshots') as mock_snapshots, \
             patch.object(scanner, '_scan_elastic_ips') as mock_ips, \
             patch.object(scanner, '_scan_nat_gateways') as mock_nats:
            
            resources = scanner.scan_single_region('us-east-1')
            
            # Verify all scan methods were called
            mock_instances.assert_called_once()
            mock_volumes.assert_called_once()
            mock_snapshots.assert_called_once()
            mock_ips.assert_called_once()
            mock_nats.assert_called_once()
            
            # Verify boto client was created for correct region
            mock_boto_client.assert_called_with('ec2', region_name='us-east-1')
    
    @patch('boto3.client')
    def test_scan_instances(self, mock_boto_client, sample_ec2_instance):
        """Test scanning EC2 instances."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # Mock paginator
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                'Reservations': [
                    {
                        'Instances': [sample_ec2_instance]
                    }
                ]
            }
        ]
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        scanner._scan_instances(mock_client, 'us-east-1', resources)
        
        assert len(resources) == 1
        resource = resources[0]
        assert resource.id == 'i-1234567890abcdef0'
        assert resource.type == 'Instance'
        assert resource.service == 'EC2'
        assert resource.name == 'test-instance'
        assert resource.state == 'running'
        assert resource.estimated_monthly_cost == 7.50  # t3.micro price
        assert resource.additional_info['instanceType'] == 't3.micro'
        assert resource.additional_info['publicIp'] == '1.2.3.4'
    
    @patch('boto3.client')
    def test_scan_instances_terminated(self, mock_boto_client, sample_ec2_instance):
        """Test that terminated instances are skipped."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # Modify instance to be terminated
        sample_ec2_instance['State']['Name'] = 'terminated'
        
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Reservations': [{'Instances': [sample_ec2_instance]}]}
        ]
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        scanner._scan_instances(mock_client, 'us-east-1', resources)
        
        assert len(resources) == 0
    
    @patch('boto3.client')
    def test_scan_volumes(self, mock_boto_client, sample_ebs_volume):
        """Test scanning EBS volumes."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Volumes': [sample_ebs_volume]}
        ]
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        scanner._scan_volumes(mock_client, 'us-east-1', resources)
        
        assert len(resources) == 1
        resource = resources[0]
        assert resource.id == 'vol-1234567890abcdef0'
        assert resource.type == 'EBS Volume'
        assert resource.name == 'test-volume'
        assert resource.state == 'in-use'
        assert resource.estimated_monthly_cost == 8.00  # 100GB * $0.08
        assert resource.additional_info['size'] == 100
        assert resource.additional_info['volumeType'] == 'gp3'
        assert resource.additional_info['encrypted'] is True
    
    @patch('boto3.client')
    def test_scan_elastic_ips(self, mock_boto_client):
        """Test scanning Elastic IPs."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # Mock response
        mock_client.describe_addresses.return_value = {
            'Addresses': [
                {
                    'AllocationId': 'eipalloc-12345',
                    'PublicIp': '1.2.3.4',
                    'Domain': 'vpc',
                    'Tags': [{'Key': 'Name', 'Value': 'test-eip'}]
                },
                {
                    'AllocationId': 'eipalloc-67890',
                    'PublicIp': '5.6.7.8',
                    'Domain': 'vpc',
                    'InstanceId': 'i-12345',  # Attached to instance
                    'Tags': []
                }
            ]
        }
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        scanner._scan_elastic_ips(mock_client, 'us-east-1', resources)
        
        assert len(resources) == 2
        
        # Unattached EIP should have cost
        unattached = resources[0]
        assert unattached.estimated_monthly_cost == 3.60
        assert unattached.state == 'unattached'
        
        # Attached EIP should have no cost
        attached = resources[1]
        assert attached.estimated_monthly_cost == 0.0
        assert attached.state == 'attached'
    
    @patch('boto3.client')
    def test_scan_nat_gateways(self, mock_boto_client):
        """Test scanning NAT Gateways."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                'NatGateways': [
                    {
                        'NatGatewayId': 'nat-12345',
                        'State': 'available',
                        'VpcId': 'vpc-12345',
                        'SubnetId': 'subnet-12345',
                        'CreateTime': datetime(2024, 1, 1),
                        'Tags': [{'Key': 'Name', 'Value': 'test-nat'}]
                    },
                    {
                        'NatGatewayId': 'nat-67890',
                        'State': 'deleted',  # Should be skipped
                        'Tags': []
                    }
                ]
            }
        ]
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        scanner._scan_nat_gateways(mock_client, 'us-east-1', resources)
        
        assert len(resources) == 1
        resource = resources[0]
        assert resource.id == 'nat-12345'
        assert resource.estimated_monthly_cost == 45.00
        assert resource.state == 'available'
    
    @patch('boto3.client')
    def test_error_handling_access_denied(self, mock_boto_client):
        """Test handling of access denied errors."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # Mock access denied error
        error = ClientError(
            {'Error': {'Code': 'UnauthorizedOperation', 'Message': 'Not authorized'}},
            'DescribeInstances'
        )
        
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.side_effect = error
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        
        # Should not raise exception, just log
        scanner._scan_instances(mock_client, 'us-east-1', resources)
        assert len(resources) == 0
    
    @patch('boto3.client')
    @patch('boto3.client')  # For STS client
    def test_scan_snapshots_with_account_id(self, mock_sts_client, mock_ec2_client):
        """Test scanning snapshots with account ID."""
        # Mock EC2 client
        mock_client = MagicMock()
        mock_ec2_client.return_value = mock_client
        
        # Mock STS client for getting account ID
        mock_sts = MagicMock()
        mock_sts_client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {'Account': '123456789012'}
        
        # Mock paginator
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                'Snapshots': [
                    {
                        'SnapshotId': 'snap-12345',
                        'VolumeSize': 50,
                        'State': 'completed',
                        'StartTime': datetime(2024, 1, 1),
                        'Description': 'Test snapshot',
                        'Encrypted': True,
                        'Tags': []
                    }
                ]
            }
        ]
        
        scanner = EC2Scanner(['us-east-1'])
        resources = []
        scanner._scan_snapshots(mock_client, 'us-east-1', resources)
        
        assert len(resources) == 1
        resource = resources[0]
        assert resource.id == 'snap-12345'
        assert resource.type == 'Snapshot'
        assert resource.estimated_monthly_cost == 2.50  # 50GB * $0.05
        
        # Verify paginator was called with owner ID
        mock_paginator.paginate.assert_called_with(OwnerIds=['123456789012'])
    
    def test_create_instance_resource_unknown_type(self, sample_ec2_instance):
        """Test creating resource with unknown instance type."""
        scanner = EC2Scanner(['us-east-1'])
        
        # Use unknown instance type
        sample_ec2_instance['InstanceType'] = 'unknown.xlarge'
        
        resource = scanner._create_instance_resource(sample_ec2_instance, 'us-east-1')
        
        # Should use default cost
        assert resource.estimated_monthly_cost == 50.0
    
    def test_create_instance_resource_stopped(self, sample_ec2_instance):
        """Test that stopped instances have no cost."""
        scanner = EC2Scanner(['us-east-1'])
        
        sample_ec2_instance['State']['Name'] = 'stopped'
        
        resource = scanner._create_instance_resource(sample_ec2_instance, 'us-east-1')
        
        assert resource.estimated_monthly_cost == 0.0
        assert resource.state == 'stopped'