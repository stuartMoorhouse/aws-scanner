"""CloudTrail resource scanner.

Reports CloudTrail trails, including whether they're multi-region and whether
their destination S3 bucket still exists (a common drift issue: bucket deleted
but trail left in place, silently failing delivery).
"""
from typing import List
import logging

from botocore.exceptions import ClientError

from .base_scanner import BaseScanner
from ..types import Resource
from ..utils import handle_aws_error, AWSAccessDeniedError

logger = logging.getLogger(__name__)


class CloudTrailScanner(BaseScanner):
    """Scanner for CloudTrail trails."""

    @property
    def service_name(self) -> str:
        return 'CloudTrail'

    def scan_single_region(self, region: str) -> List[Resource]:
        client = self.session.client('cloudtrail', region_name=region)
        s3 = self.session.client('s3')
        resources: List[Resource] = []

        try:
            trails = client.describe_trails(includeShadowTrails=False).get('trailList', [])

            for trail in trails:
                # Only report the trail in its home region to avoid duplicates
                # from multi-region trails.
                if trail.get('HomeRegion') != region:
                    continue

                name = trail.get('Name')
                bucket = trail.get('S3BucketName')
                bucket_exists = self._bucket_exists(s3, bucket) if bucket else None

                # Check delivery status
                try:
                    status = client.get_trail_status(Name=trail.get('TrailARN', name))
                    logging_enabled = status.get('IsLogging', False)
                    last_delivery_error = status.get('LatestDeliveryError')
                except ClientError:
                    logging_enabled = None
                    last_delivery_error = None

                resources.append(Resource(
                    id=trail.get('TrailARN', name),
                    type='Trail',
                    service='CloudTrail',
                    name=name,
                    region=region,
                    created_at=None,
                    state='logging' if logging_enabled else 'stopped',
                    estimated_monthly_cost=None,  # First trail is free; extras/data events are usage-based
                    additional_info={
                        's3Bucket': bucket,
                        's3BucketExists': bucket_exists,
                        'multiRegion': trail.get('IsMultiRegionTrail', False),
                        'orgTrail': trail.get('IsOrganizationTrail', False),
                        'logFileValidation': trail.get('LogFileValidationEnabled', False),
                        'lastDeliveryError': last_delivery_error or None,
                    }
                ))
        except ClientError as e:
            handle_aws_error(e, 'CloudTrail')
        except AWSAccessDeniedError:
            logger.info(f"No access to CloudTrail in {region}")

        return resources

    _bucket_check_cache: dict = {}

    def _bucket_exists(self, s3_client, bucket: str) -> bool:
        if bucket in self._bucket_check_cache:
            return self._bucket_check_cache[bucket]
        try:
            s3_client.head_bucket(Bucket=bucket)
            exists = True
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            # 404 = missing; 403 = exists but in another account
            exists = code != '404' and 'NoSuchBucket' not in code
        self._bucket_check_cache[bucket] = exists
        return exists
