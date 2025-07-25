import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class Route53Scanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'Route53'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        resources: List[Resource] = []
        
        # Route53 is global, only scan from us-east-1
        if region != 'us-east-1':
            return resources
        
        client = boto3.client('route53', region_name=region)
        
        # Scan Hosted Zones
        self._scan_hosted_zones(client, resources)
        
        # Scan Health Checks
        self._scan_health_checks(client, resources)
        
        return resources
    
    def _scan_hosted_zones(self, client, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('list_hosted_zones')
            
            for page in paginator.paginate():
                for zone in page.get('HostedZones', []):
                    zone_id = zone.get('Id', '').split('/')[-1]  # Extract ID from path
                    zone_name = zone.get('Name', 'Unknown')
                    
                    # Get record count for the zone
                    record_count = 0
                    try:
                        record_response = client.get_hosted_zone_count(HostedZoneId=zone_id)
                        record_count = record_response.get('RecordSetCount', 0)
                    except:
                        pass
                    
                    # Get tags
                    tags = {}
                    try:
                        tags_response = client.list_tags_for_resource(
                            ResourceType='hostedzone',
                            ResourceId=zone_id
                        )
                        for tag in tags_response.get('ResourceTagSet', {}).get('Tags', []):
                            tags[tag.get('Key', '')] = tag.get('Value', '')
                    except:
                        pass
                    
                    # Hosted zone pricing: $0.50 per hosted zone per month
                    # + $0.40 per million queries (not included in this estimate)
                    base_cost = 0.50
                    
                    # Additional cost for private hosted zones
                    if zone.get('Config', {}).get('PrivateZone'):
                        base_cost = 0.50  # Same price but billed per VPC association
                    
                    resources.append(Resource(
                        id=zone_id,
                        type='Hosted Zone',
                        service='Route53',
                        name=tags.get('Name', zone_name),
                        region='global',
                        state='active',
                        estimated_monthly_cost=base_cost,
                        additional_info={
                            'domainName': zone_name,
                            'recordSetCount': record_count,
                            'privateZone': zone.get('Config', {}).get('PrivateZone', False),
                            'comment': zone.get('Config', {}).get('Comment'),
                            'callerReference': zone.get('CallerReference'),
                            'tags': tags
                        }
                    ))
                    
        except Exception as e:
            self.handle_error(e, 'Route53 Hosted Zones')
    
    def _scan_health_checks(self, client, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('list_health_checks')
            
            for page in paginator.paginate():
                for health_check in page.get('HealthChecks', []):
                    hc_id = health_check.get('Id', 'Unknown')
                    hc_config = health_check.get('HealthCheckConfig', {})
                    
                    # Get tags
                    tags = {}
                    try:
                        tags_response = client.list_tags_for_resource(
                            ResourceType='healthcheck',
                            ResourceId=hc_id
                        )
                        for tag in tags_response.get('ResourceTagSet', {}).get('Tags', []):
                            tags[tag.get('Key', '')] = tag.get('Value', '')
                    except:
                        pass
                    
                    # Health check pricing varies by type
                    # HTTP/HTTPS/TCP: $0.50/month
                    # HTTPS with string matching: $0.75/month
                    # Calculated/CloudWatch: $0.50/month
                    hc_type = hc_config.get('Type', '')
                    if hc_type in ['HTTPS_STR_MATCH', 'HTTP_STR_MATCH']:
                        monthly_cost = 0.75
                    else:
                        monthly_cost = 0.50
                    
                    # Additional charges for optional features
                    if hc_config.get('MeasureLatency'):
                        monthly_cost += 0.20  # Latency measurements
                    
                    resources.append(Resource(
                        id=hc_id,
                        type='Health Check',
                        service='Route53',
                        name=tags.get('Name', f'Health Check {hc_id}'),
                        region='global',
                        state='active',
                        estimated_monthly_cost=monthly_cost,
                        additional_info={
                            'type': hc_type,
                            'protocol': hc_config.get('Type'),
                            'resourcePath': hc_config.get('ResourcePath'),
                            'fullyQualifiedDomainName': hc_config.get('FullyQualifiedDomainName'),
                            'port': hc_config.get('Port'),
                            'measureLatency': hc_config.get('MeasureLatency', False),
                            'failureThreshold': hc_config.get('FailureThreshold'),
                            'disabled': hc_config.get('Disabled', False),
                            'tags': tags
                        }
                    ))
                    
        except Exception as e:
            self.handle_error(e, 'Route53 Health Checks')