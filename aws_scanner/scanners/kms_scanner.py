"""KMS resource scanner.

Reports customer-managed KMS keys (AWS-managed keys `alias/aws/*` are free
and are skipped). Standard customer-managed CMKs cost $1/month per key.
"""
from typing import List
import logging

from botocore.exceptions import ClientError

from .base_scanner import BaseScanner
from ..types import Resource
from ..utils import handle_aws_error, AWSAccessDeniedError

logger = logging.getLogger(__name__)

CUSTOMER_MANAGED_CMK_MONTHLY_COST = 1.00


class KMSScanner(BaseScanner):
    """Scanner for KMS customer-managed keys."""

    @property
    def service_name(self) -> str:
        return 'KMS'

    def scan_single_region(self, region: str) -> List[Resource]:
        client = self.session.client('kms', region_name=region)
        resources: List[Resource] = []

        try:
            # Build alias index so we can label keys with their friendly name
            aliases_by_key_id = {}
            for page in client.get_paginator('list_aliases').paginate():
                for alias in page.get('Aliases', []):
                    key_id = alias.get('TargetKeyId')
                    if key_id:
                        aliases_by_key_id.setdefault(key_id, []).append(alias['AliasName'])

            for page in client.get_paginator('list_keys').paginate():
                for key in page.get('Keys', []):
                    key_id = key['KeyId']
                    try:
                        meta = client.describe_key(KeyId=key_id)['KeyMetadata']
                    except ClientError as e:
                        # Some keys (e.g. pending deletion in another account) can't be described
                        logger.debug(f"Skipping KMS key {key_id} in {region}: {e}")
                        continue

                    # Only customer-managed keys are billed
                    if meta.get('KeyManager') != 'CUSTOMER':
                        continue

                    aliases = aliases_by_key_id.get(key_id, [])
                    state = meta.get('KeyState', 'Unknown')
                    # Pending deletion / disabled keys still bill until deleted
                    cost = CUSTOMER_MANAGED_CMK_MONTHLY_COST

                    resources.append(Resource(
                        id=key_id,
                        type='CMK',
                        service='KMS',
                        name=aliases[0] if aliases else meta.get('Description') or key_id,
                        region=region,
                        created_at=meta.get('CreationDate'),
                        state=state,
                        estimated_monthly_cost=cost,
                        additional_info={
                            'aliases': ', '.join(aliases) or None,
                            'description': meta.get('Description') or None,
                            'keySpec': meta.get('KeySpec'),
                            'keyUsage': meta.get('KeyUsage'),
                            'rotationEnabled': self._rotation_enabled(client, key_id),
                        }
                    ))
        except ClientError as e:
            handle_aws_error(e, 'KMS Keys')
        except AWSAccessDeniedError:
            logger.info(f"No access to KMS in {region}")

        return resources

    def _rotation_enabled(self, client, key_id: str):
        try:
            return client.get_key_rotation_status(KeyId=key_id).get('KeyRotationEnabled')
        except ClientError:
            return None
