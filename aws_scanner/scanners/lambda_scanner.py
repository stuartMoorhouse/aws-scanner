"""Lambda function scanner."""
import boto3
from typing import List, Dict, Any
from datetime import datetime
from botocore.exceptions import ClientError
import logging

from .base_scanner import BaseScanner
from ..types import Resource
from ..utils import retry_with_backoff, handle_aws_error, AWSAccessDeniedError
from ..type_defs import LambdaFunctionInfo, BotoClient

logger = logging.getLogger(__name__)


class LambdaScanner(BaseScanner):
    """Scanner for AWS Lambda functions."""
    
    @property
    def service_name(self) -> str:
        """Return the service name."""
        return 'Lambda'
    
    def scan_single_region(self, region: str) -> List[Resource]:
        """
        Scan Lambda functions in a single region.
        
        Args:
            region: AWS region to scan
            
        Returns:
            List of Lambda function resources
        """
        client = boto3.client('lambda', region_name=region)
        resources: List[Resource] = []
        
        try:
            self._scan_functions(client, region, resources)
        except Exception as e:
            logger.error(f"Error scanning Lambda functions in {region}: {e}")
            
        return resources
    
    @retry_with_backoff()
    def _scan_functions(self, client: BotoClient, region: str, resources: List[Resource]) -> None:
        """Scan Lambda functions."""
        try:
            paginator = client.get_paginator('list_functions')
            
            for page in paginator.paginate():
                for func in page.get('Functions', []):
                    resource = self._create_function_resource(func, region)
                    resources.append(resource)
                    
        except ClientError as e:
            handle_aws_error(e, 'Lambda Functions')
        except AWSAccessDeniedError:
            logger.info(f"No access to Lambda functions in {region}")
        except Exception as e:
            logger.exception(f"Unexpected error scanning Lambda functions in {region}")
            raise
    
    def _create_function_resource(self, func: Dict[str, Any], region: str) -> Resource:
        """Create Resource object from Lambda function data."""
        memory_mb = func.get('MemorySize', 128)
        
        # Lambda pricing estimation
        # These are rough estimates - actual usage will vary significantly
        estimated_monthly_invocations = 100_000  # Conservative estimate
        estimated_avg_duration_ms = 100  # Conservative estimate
        
        # Price per GB-second: ~$0.0000166667 for x86
        # Price per request: $0.20 per 1M requests
        gb_seconds = (memory_mb / 1024) * (estimated_avg_duration_ms / 1000) * estimated_monthly_invocations
        compute_cost = gb_seconds * 0.0000166667
        request_cost = (estimated_monthly_invocations / 1_000_000) * 0.20
        
        # Check for ARM architecture (Graviton2) which is 20% cheaper
        architectures = func.get('Architectures', ['x86_64'])
        if 'arm64' in architectures:
            compute_cost *= 0.8
        
        estimated_cost = compute_cost + request_cost
        
        # Parse last modified timestamp
        last_modified = func.get('LastModified')
        created_at = None
        if last_modified:
            try:
                # Parse the ISO format timestamp
                created_at = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            except Exception:
                logger.debug(f"Could not parse timestamp: {last_modified}")
        
        # Build additional info
        additional_info: LambdaFunctionInfo = {
            'runtime': func.get('Runtime'),
            'memorySize': memory_mb,
            'timeout': func.get('Timeout'),
            'handler': func.get('Handler'),
            'codeSize': func.get('CodeSize'),
            'lastModified': last_modified,
            'architectures': architectures,
        }
        
        # Add optional fields
        if func.get('Description'):
            additional_info['description'] = func['Description']
        if func.get('Layers'):
            additional_info['layers'] = len(func['Layers'])
        if func.get('Environment', {}).get('Variables'):
            additional_info['envVars'] = len(func['Environment']['Variables'])
        
        return Resource(
            id=func.get('FunctionArn', 'Unknown'),
            type='Function',
            service='Lambda',
            name=func.get('FunctionName'),
            region=region,
            created_at=created_at,
            state=func.get('State', 'unknown'),
            estimated_monthly_cost=estimated_cost,
            additional_info=additional_info
        )