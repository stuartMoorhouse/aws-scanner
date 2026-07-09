"""GuardDuty resource scanner.

Reports enabled GuardDuty detectors and which features are on. Cost is
usage-based (bytes analysed, event volume), so no fixed monthly estimate is
produced — but detectors are flagged so you can see where GuardDuty is active.
"""
from typing import List
import logging

from botocore.exceptions import ClientError

from .base_scanner import BaseScanner
from ..types import Resource
from ..utils import handle_aws_error, AWSAccessDeniedError

logger = logging.getLogger(__name__)


class GuardDutyScanner(BaseScanner):
    """Scanner for GuardDuty detectors."""

    @property
    def service_name(self) -> str:
        return 'GuardDuty'

    def scan_single_region(self, region: str) -> List[Resource]:
        client = self.session.client('guardduty', region_name=region)
        resources: List[Resource] = []

        try:
            for page in client.get_paginator('list_detectors').paginate():
                for detector_id in page.get('DetectorIds', []):
                    detail = client.get_detector(DetectorId=detector_id)
                    features = detail.get('Features') or []
                    enabled_features = [
                        f['Name'] for f in features if f.get('Status') == 'ENABLED'
                    ]

                    resources.append(Resource(
                        id=detector_id,
                        type='Detector',
                        service='GuardDuty',
                        name=detector_id,
                        region=region,
                        created_at=detail.get('CreatedAt'),
                        state=detail.get('Status', 'unknown').lower(),
                        estimated_monthly_cost=None,  # Usage-based; can't estimate without CloudWatch metrics
                        additional_info={
                            'findingPublishingFrequency': detail.get('FindingPublishingFrequency'),
                            'enabledFeatures': ', '.join(enabled_features) or 'none',
                            'featureCount': len(enabled_features),
                        }
                    ))
        except ClientError as e:
            handle_aws_error(e, 'GuardDuty')
        except AWSAccessDeniedError:
            logger.info(f"No access to GuardDuty in {region}")

        return resources
