"""Secrets Manager resource scanner.

Each secret costs $0.40/month, plus $0.05 per 10,000 API calls. We report the
per-secret standing charge.
"""
from typing import List
import logging

from botocore.exceptions import ClientError

from .base_scanner import BaseScanner
from ..types import Resource
from ..utils import handle_aws_error, AWSAccessDeniedError

logger = logging.getLogger(__name__)

SECRET_MONTHLY_COST = 0.40


class SecretsManagerScanner(BaseScanner):
    """Scanner for AWS Secrets Manager secrets."""

    @property
    def service_name(self) -> str:
        return 'SecretsManager'

    def scan_single_region(self, region: str) -> List[Resource]:
        client = self.session.client('secretsmanager', region_name=region)
        resources: List[Resource] = []

        try:
            for page in client.get_paginator('list_secrets').paginate():
                for secret in page.get('SecretList', []):
                    resources.append(Resource(
                        id=secret.get('ARN', secret.get('Name', 'Unknown')),
                        type='Secret',
                        service='SecretsManager',
                        name=secret.get('Name'),
                        region=region,
                        created_at=secret.get('CreatedDate'),
                        state='active',
                        estimated_monthly_cost=SECRET_MONTHLY_COST,
                        additional_info={
                            'description': secret.get('Description') or None,
                            'lastAccessed': str(secret['LastAccessedDate']) if secret.get('LastAccessedDate') else None,
                            'lastChanged': str(secret['LastChangedDate']) if secret.get('LastChangedDate') else None,
                            'rotationEnabled': secret.get('RotationEnabled', False),
                            'kmsKeyId': secret.get('KmsKeyId') or 'aws/secretsmanager',
                        }
                    ))
        except ClientError as e:
            handle_aws_error(e, 'Secrets Manager')
        except AWSAccessDeniedError:
            logger.info(f"No access to Secrets Manager in {region}")

        return resources
