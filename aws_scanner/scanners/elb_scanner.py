import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class ELBScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'ELB'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        resources: List[Resource] = []
        
        # Scan Classic Load Balancers
        self._scan_classic_load_balancers(region, resources)
        
        # Scan Application/Network/Gateway Load Balancers
        self._scan_v2_load_balancers(region, resources)
        
        return resources
    
    def _scan_classic_load_balancers(self, region: str, resources: List[Resource]) -> None:
        client = boto3.client('elb', region_name=region)
        
        try:
            paginator = client.get_paginator('describe_load_balancers')
            
            for page in paginator.paginate():
                for lb in page.get('LoadBalancerDescriptions', []):
                    # Classic LB: ~$25/month + data processing
                    estimated_cost = 25
                    
                    resources.append(Resource(
                        id=lb.get('LoadBalancerName', 'Unknown'),
                        type='Classic Load Balancer',
                        service='ELB',
                        name=lb.get('LoadBalancerName'),
                        region=region,
                        created_at=lb.get('CreatedTime'),
                        state='active',
                        estimated_monthly_cost=estimated_cost,
                        additional_info={
                            'dnsName': lb.get('DNSName'),
                            'scheme': lb.get('Scheme'),
                            'vpcId': lb.get('VPCId'),
                            'availabilityZones': lb.get('AvailabilityZones'),
                            'instanceCount': len(lb.get('Instances', []))
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'Classic Load Balancers')
    
    def _scan_v2_load_balancers(self, region: str, resources: List[Resource]) -> None:
        client = boto3.client('elbv2', region_name=region)
        
        try:
            paginator = client.get_paginator('describe_load_balancers')
            
            for page in paginator.paginate():
                for lb in page.get('LoadBalancers', []):
                    # Pricing varies by type
                    lb_type_display = 'Unknown'
                    estimated_cost = 0
                    
                    lb_type = lb.get('Type')
                    if lb_type == 'application':
                        lb_type_display = 'Application Load Balancer'
                        estimated_cost = 23  # ~$0.0225/hour
                    elif lb_type == 'network':
                        lb_type_display = 'Network Load Balancer'
                        estimated_cost = 23  # ~$0.0225/hour
                    elif lb_type == 'gateway':
                        lb_type_display = 'Gateway Load Balancer'
                        estimated_cost = 23  # ~$0.0225/hour
                    
                    state = lb.get('State', {}).get('Code')
                    
                    resources.append(Resource(
                        id=lb.get('LoadBalancerArn', 'Unknown'),
                        type=lb_type_display,
                        service='ELB',
                        name=lb.get('LoadBalancerName'),
                        region=region,
                        created_at=lb.get('CreatedTime'),
                        state=state,
                        estimated_monthly_cost=estimated_cost if state == 'active' else 0,
                        additional_info={
                            'dnsName': lb.get('DNSName'),
                            'scheme': lb.get('Scheme'),
                            'vpcId': lb.get('VpcId'),
                            'availabilityZones': [az.get('ZoneName') for az in lb.get('AvailabilityZones', []) if az.get('ZoneName')],
                            'ipAddressType': lb.get('IpAddressType')
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'V2 Load Balancers')