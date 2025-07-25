"""EC2 resource scanner."""
import boto3
from typing import List, Dict, Any, Optional
from datetime import datetime
from botocore.exceptions import ClientError
import logging

from .base_scanner import BaseScanner
from ..types import Resource
from ..config import get_instance_cost, get_ebs_cost, ELASTIC_IP_PRICING, NAT_GATEWAY_PRICING, SNAPSHOT_PRICING
from ..utils import retry_with_backoff, handle_aws_error, AWSAccessDeniedError
from ..type_defs import EC2InstanceInfo, EBSVolumeInfo, BotoClient

logger = logging.getLogger(__name__)


class EC2Scanner(BaseScanner):
    """Scanner for EC2 resources."""
    
    @property
    def service_name(self) -> str:
        """Return the service name."""
        return 'EC2'
    
    def scan_single_region(self, region: str) -> List[Resource]:
        """
        Scan EC2 resources in a single region.
        
        Args:
            region: AWS region to scan
            
        Returns:
            List of EC2 resources found
        """
        client = boto3.client('ec2', region_name=region)
        resources: List[Resource] = []
        
        # Scan different EC2 resource types
        self._scan_instances(client, region, resources)
        self._scan_volumes(client, region, resources)
        self._scan_snapshots(client, region, resources)
        self._scan_elastic_ips(client, region, resources)
        self._scan_nat_gateways(client, region, resources)
        
        return resources
    
    @retry_with_backoff()
    def _scan_instances(self, client: BotoClient, region: str, resources: List[Resource]) -> None:
        """Scan EC2 instances."""
        try:
            paginator = client.get_paginator('describe_instances')
            
            for page in paginator.paginate():
                for reservation in page.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        if instance.get('State', {}).get('Name') != 'terminated':
                            resource = self._create_instance_resource(instance, region)
                            resources.append(resource)
                            
        except ClientError as e:
            handle_aws_error(e, 'EC2 Instances')
        except AWSAccessDeniedError:
            logger.info(f"No access to EC2 instances in {region}")
        except Exception as e:
            logger.exception(f"Unexpected error scanning EC2 instances in {region}")
            raise
    
    def _create_instance_resource(self, instance: Dict[str, Any], region: str) -> Resource:
        """Create Resource object from EC2 instance data."""
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        instance_type = instance.get('InstanceType', '')
        state = instance.get('State', {}).get('Name', 'unknown')
        
        # Get cost estimate
        estimated_cost = get_instance_cost(instance_type, state)
        
        # Build additional info
        additional_info: EC2InstanceInfo = {
            'instanceType': instance_type,
            'publicIp': instance.get('PublicIpAddress'),
            'privateIp': instance.get('PrivateIpAddress'),
            'vpcId': instance.get('VpcId'),
            'subnetId': instance.get('SubnetId'),
            'availabilityZone': instance.get('Placement', {}).get('AvailabilityZone'),
            'platform': instance.get('Platform'),
            'architecture': instance.get('Architecture'),
        }
        
        # Remove None values
        additional_info = {k: v for k, v in additional_info.items() if v is not None}
        
        return Resource(
            id=instance.get('InstanceId', 'Unknown'),
            type='Instance',
            service='EC2',
            name=tags.get('Name'),
            region=region,
            created_at=instance.get('LaunchTime'),
            state=state,
            estimated_monthly_cost=estimated_cost,
            additional_info=additional_info
        )
    
    @retry_with_backoff()
    def _scan_volumes(self, client: BotoClient, region: str, resources: List[Resource]) -> None:
        """Scan EBS volumes."""
        try:
            paginator = client.get_paginator('describe_volumes')
            
            for page in paginator.paginate():
                for volume in page.get('Volumes', []):
                    if volume.get('State') != 'deleted':
                        resource = self._create_volume_resource(volume, region)
                        resources.append(resource)
                        
        except ClientError as e:
            handle_aws_error(e, 'EBS Volumes')
        except AWSAccessDeniedError:
            logger.info(f"No access to EBS volumes in {region}")
        except Exception as e:
            logger.exception(f"Unexpected error scanning EBS volumes in {region}")
            raise
    
    def _create_volume_resource(self, volume: Dict[str, Any], region: str) -> Resource:
        """Create Resource object from EBS volume data."""
        tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
        volume_type = volume.get('VolumeType', 'gp2')
        size_gb = volume.get('Size', 0)
        
        # Get cost estimate
        estimated_cost = get_ebs_cost(volume_type, size_gb)
        
        # Build additional info
        additional_info: EBSVolumeInfo = {
            'volumeType': volume_type,
            'size': size_gb,
            'iops': volume.get('Iops'),
            'throughput': volume.get('Throughput'),
            'encrypted': volume.get('Encrypted', False),
            'availabilityZone': volume.get('AvailabilityZone', ''),
            'attachments': len(volume.get('Attachments', [])),
        }
        
        return Resource(
            id=volume.get('VolumeId', 'Unknown'),
            type='EBS Volume',
            service='EC2',
            name=tags.get('Name'),
            region=region,
            created_at=volume.get('CreateTime'),
            state=volume.get('State'),
            estimated_monthly_cost=estimated_cost,
            additional_info=additional_info
        )
    
    @retry_with_backoff()
    def _scan_snapshots(self, client: BotoClient, region: str, resources: List[Resource]) -> None:
        """Scan EBS snapshots."""
        try:
            # Get account ID
            account_id = boto3.client('sts').get_caller_identity()['Account']
            
            paginator = client.get_paginator('describe_snapshots')
            
            for page in paginator.paginate(OwnerIds=[account_id]):
                for snapshot in page.get('Snapshots', []):
                    resource = self._create_snapshot_resource(snapshot, region)
                    resources.append(resource)
                    
        except ClientError as e:
            handle_aws_error(e, 'EBS Snapshots')
        except AWSAccessDeniedError:
            logger.info(f"No access to EBS snapshots in {region}")
        except Exception as e:
            logger.exception(f"Unexpected error scanning EBS snapshots in {region}")
            raise
    
    def _create_snapshot_resource(self, snapshot: Dict[str, Any], region: str) -> Resource:
        """Create Resource object from EBS snapshot data."""
        tags = {tag['Key']: tag['Value'] for tag in snapshot.get('Tags', [])}
        size_gb = snapshot.get('VolumeSize', 0)
        
        # Calculate cost
        estimated_cost = size_gb * SNAPSHOT_PRICING
        
        return Resource(
            id=snapshot.get('SnapshotId', 'Unknown'),
            type='Snapshot',
            service='EC2',
            name=tags.get('Name') or snapshot.get('Description'),
            region=region,
            created_at=snapshot.get('StartTime'),
            state=snapshot.get('State'),
            estimated_monthly_cost=estimated_cost,
            additional_info={
                'volumeSize': size_gb,
                'progress': snapshot.get('Progress'),
                'encrypted': snapshot.get('Encrypted', False),
                'description': snapshot.get('Description'),
            }
        )
    
    @retry_with_backoff()
    def _scan_elastic_ips(self, client: BotoClient, region: str, resources: List[Resource]) -> None:
        """Scan Elastic IPs."""
        try:
            response = client.describe_addresses()
            
            for address in response.get('Addresses', []):
                resource = self._create_elastic_ip_resource(address, region)
                resources.append(resource)
                
        except ClientError as e:
            handle_aws_error(e, 'Elastic IPs')
        except AWSAccessDeniedError:
            logger.info(f"No access to Elastic IPs in {region}")
        except Exception as e:
            logger.exception(f"Unexpected error scanning Elastic IPs in {region}")
            raise
    
    def _create_elastic_ip_resource(self, address: Dict[str, Any], region: str) -> Resource:
        """Create Resource object from Elastic IP data."""
        tags = {tag['Key']: tag['Value'] for tag in address.get('Tags', [])}
        
        # Elastic IPs only cost money when not attached to a running instance
        is_attached = bool(address.get('InstanceId'))
        estimated_cost = 0.0 if is_attached else ELASTIC_IP_PRICING
        
        return Resource(
            id=address.get('AllocationId', 'Unknown'),
            type='Elastic IP',
            service='EC2',
            name=tags.get('Name'),
            region=region,
            created_at=None,  # Elastic IPs don't have creation time in API
            state='attached' if is_attached else 'unattached',
            estimated_monthly_cost=estimated_cost,
            additional_info={
                'publicIp': address.get('PublicIp'),
                'domain': address.get('Domain'),
                'instanceId': address.get('InstanceId'),
                'networkInterfaceId': address.get('NetworkInterfaceId'),
                'privateIpAddress': address.get('PrivateIpAddress'),
            }
        )
    
    @retry_with_backoff()
    def _scan_nat_gateways(self, client: BotoClient, region: str, resources: List[Resource]) -> None:
        """Scan NAT Gateways."""
        try:
            paginator = client.get_paginator('describe_nat_gateways')
            
            for page in paginator.paginate():
                for nat_gateway in page.get('NatGateways', []):
                    if nat_gateway.get('State') not in ['deleted', 'deleting', 'failed']:
                        resource = self._create_nat_gateway_resource(nat_gateway, region)
                        resources.append(resource)
                        
        except ClientError as e:
            handle_aws_error(e, 'NAT Gateways')
        except AWSAccessDeniedError:
            logger.info(f"No access to NAT Gateways in {region}")
        except Exception as e:
            logger.exception(f"Unexpected error scanning NAT Gateways in {region}")
            raise
    
    def _create_nat_gateway_resource(self, nat_gateway: Dict[str, Any], region: str) -> Resource:
        """Create Resource object from NAT Gateway data."""
        tags = {tag['Key']: tag['Value'] for tag in nat_gateway.get('Tags', [])}
        
        # NAT Gateways cost money when available
        state = nat_gateway.get('State', 'unknown')
        estimated_cost = NAT_GATEWAY_PRICING['monthly'] if state == 'available' else 0.0
        
        return Resource(
            id=nat_gateway.get('NatGatewayId', 'Unknown'),
            type='NAT Gateway',
            service='EC2',
            name=tags.get('Name'),
            region=region,
            created_at=nat_gateway.get('CreateTime'),
            state=state,
            estimated_monthly_cost=estimated_cost,
            additional_info={
                'vpcId': nat_gateway.get('VpcId'),
                'subnetId': nat_gateway.get('SubnetId'),
                'connectivityType': nat_gateway.get('ConnectivityType'),
                'natGatewayAddresses': [
                    addr.get('PublicIp') for addr in nat_gateway.get('NatGatewayAddresses', [])
                ],
            }
        )