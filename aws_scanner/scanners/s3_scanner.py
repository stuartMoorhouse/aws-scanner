"""S3 bucket scanner."""
import boto3
from typing import List, Dict, Any
from botocore.exceptions import ClientError
import logging

from .base_scanner import BaseScanner
from ..types import Resource
from ..utils import retry_with_backoff, handle_aws_error, AWSAccessDeniedError
from ..type_defs import S3BucketInfo, BotoClient

logger = logging.getLogger(__name__)


class S3Scanner(BaseScanner):
    """Scanner for S3 buckets."""
    
    @property
    def service_name(self) -> str:
        """Return the service name."""
        return 'S3'
    
    def scan_single_region(self, region: str) -> List[Resource]:
        """
        Scan S3 buckets in a single region.
        
        Note: S3 is a global service, but we only scan in one region to avoid duplicates.
        
        Args:
            region: AWS region to scan
            
        Returns:
            List of S3 bucket resources
        """
        # S3 is global, only scan in us-east-1 to avoid duplicates
        if region != 'us-east-1':
            return []
        
        client = boto3.client('s3', region_name=region)
        resources: List[Resource] = []
        
        try:
            self._scan_buckets(client, resources)
        except Exception as e:
            logger.error(f"Error scanning S3 buckets: {e}")
            
        return resources
    
    @retry_with_backoff()
    def _scan_buckets(self, client: BotoClient, resources: List[Resource]) -> None:
        """Scan S3 buckets."""
        try:
            response = client.list_buckets()
            
            for bucket in response.get('Buckets', []):
                bucket_name = bucket.get('Name', '')
                
                try:
                    # Get bucket details with retry
                    bucket_info = self._get_bucket_info(client, bucket_name)
                    
                    # Create resource
                    resource = self._create_bucket_resource(
                        bucket_name,
                        bucket.get('CreationDate'),
                        bucket_info
                    )
                    resources.append(resource)
                    
                except Exception as e:
                    logger.warning(f"Error getting details for bucket {bucket_name}: {e}")
                    # Still add the bucket with basic info
                    resources.append(Resource(
                        id=bucket_name,
                        type='Bucket',
                        service='S3',
                        name=bucket_name,
                        region='global',
                        created_at=bucket.get('CreationDate'),
                        state='available',
                        estimated_monthly_cost=0.50,  # Minimum estimate
                        additional_info={'error': 'Could not fetch bucket details'}
                    ))
                    
        except ClientError as e:
            handle_aws_error(e, 'S3 Buckets')
        except AWSAccessDeniedError:
            logger.info("No access to S3 buckets")
        except Exception as e:
            logger.exception("Unexpected error scanning S3 buckets")
            raise
    
    @retry_with_backoff()
    def _get_bucket_info(self, client: BotoClient, bucket_name: str) -> S3BucketInfo:
        """Get detailed information about a bucket."""
        info: S3BucketInfo = {}
        
        # Get bucket location
        try:
            location_response = client.get_bucket_location(Bucket=bucket_name)
            location = location_response.get('LocationConstraint') or 'us-east-1'
            regional_client = boto3.client('s3', region_name=location)
        except Exception:
            regional_client = client
            location = 'unknown'
        
        # Get bucket size and object count (sample first 1000 objects)
        try:
            paginator = regional_client.get_paginator('list_objects_v2')
            object_count = 0
            total_size = 0
            
            for page in paginator.paginate(Bucket=bucket_name, MaxKeys=1000):
                objects = page.get('Contents', [])
                object_count += len(objects)
                total_size += sum(obj.get('Size', 0) for obj in objects)
                
                # Only sample first page for performance
                break
            
            info['objectCount'] = object_count
            info['totalSize'] = total_size / (1024 ** 3)  # Convert to GB
            
        except Exception as e:
            logger.debug(f"Could not get object count for {bucket_name}: {e}")
        
        # Get versioning status
        try:
            versioning = regional_client.get_bucket_versioning(Bucket=bucket_name)
            info['versioning'] = versioning.get('Status') == 'Enabled'
        except Exception:
            pass
        
        # Get encryption status
        try:
            regional_client.get_bucket_encryption(Bucket=bucket_name)
            info['encryption'] = True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ServerSideEncryptionConfigurationNotFoundError':
                info['encryption'] = False
        except Exception:
            pass
        
        # Get public access block
        try:
            public_access = regional_client.get_public_access_block(Bucket=bucket_name)
            config = public_access.get('PublicAccessBlockConfiguration', {})
            info['publicAccess'] = not all([
                config.get('BlockPublicAcls', False),
                config.get('IgnorePublicAcls', False),
                config.get('BlockPublicPolicy', False),
                config.get('RestrictPublicBuckets', False)
            ])
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchPublicAccessBlockConfiguration':
                info['publicAccess'] = True  # No block means potentially public
        except Exception:
            pass
        
        # Get lifecycle rules count
        try:
            lifecycle = regional_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
            info['lifecycleRules'] = len(lifecycle.get('Rules', []))
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
                info['lifecycleRules'] = 0
        except Exception:
            pass
        
        # Get tags
        try:
            tagging = regional_client.get_bucket_tagging(Bucket=bucket_name)
            tags = {tag['Key']: tag['Value'] for tag in tagging.get('TagSet', [])}
            if tags:
                info['tags'] = tags
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchTagSet':
                logger.debug(f"Error getting tags for {bucket_name}: {e}")
        except Exception:
            pass
        
        return info
    
    def _create_bucket_resource(
        self, 
        bucket_name: str, 
        created_at: Any,
        info: S3BucketInfo
    ) -> Resource:
        """Create Resource object from S3 bucket data."""
        # Estimate monthly cost based on size and features
        size_gb = info.get('totalSize', 0)
        object_count = info.get('objectCount', 0)
        
        # S3 Standard pricing estimates
        storage_cost = size_gb * 0.023  # $0.023 per GB for first 50TB
        request_cost = (object_count / 1000) * 0.0004  # GET requests estimate
        
        # Add costs for features
        if info.get('versioning'):
            storage_cost *= 1.2  # 20% overhead for versioning
        
        if info.get('lifecycleRules', 0) > 0:
            storage_cost *= 0.8  # Assume 20% savings from lifecycle rules
        
        estimated_cost = max(storage_cost + request_cost, 0.50)  # Minimum $0.50
        
        # Build additional info
        additional_info = {k: v for k, v in info.items() if v is not None}
        
        # Add human-readable size
        if 'totalSize' in additional_info:
            size = additional_info['totalSize']
            if size < 1:
                additional_info['sizeStr'] = f"{size * 1024:.2f} MB"
            else:
                additional_info['sizeStr'] = f"{size:.2f} GB"
        
        return Resource(
            id=bucket_name,
            type='Bucket',
            service='S3',
            name=info.get('tags', {}).get('Name', bucket_name),
            region='global',
            created_at=created_at,
            state='available',
            estimated_monthly_cost=estimated_cost,
            additional_info=additional_info
        )