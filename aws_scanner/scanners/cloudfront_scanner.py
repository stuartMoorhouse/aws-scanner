import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class CloudFrontScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'CloudFront'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        resources: List[Resource] = []
        
        # CloudFront is global, only scan from us-east-1
        if region != 'us-east-1':
            return resources
        
        client = boto3.client('cloudfront', region_name=region)
        
        try:
            paginator = client.get_paginator('list_distributions')
            
            for page in paginator.paginate():
                distribution_list = page.get('DistributionList', {})
                
                for item in distribution_list.get('Items', []):
                    distribution_id = item.get('Id', 'Unknown')
                    
                    # Get full distribution details
                    try:
                        dist_response = client.get_distribution(Id=distribution_id)
                        distribution = dist_response.get('Distribution', {})
                        dist_config = distribution.get('DistributionConfig', {})
                        
                        # Get tags
                        tags = {}
                        try:
                            tags_response = client.list_tags_for_resource(
                                Resource=item.get('ARN', '')
                            )
                            for tag in tags_response.get('Tags', {}).get('Items', []):
                                tags[tag.get('Key', '')] = tag.get('Value', '')
                        except:
                            pass
                        
                        # CloudFront pricing is complex - this is a rough estimate
                        # Base cost for distribution + data transfer costs
                        enabled = dist_config.get('Enabled', False)
                        price_class = dist_config.get('PriceClass', 'PriceClass_All')
                        
                        # Base monthly cost estimate
                        base_cost = 0
                        if enabled:
                            if 'All' in price_class:
                                base_cost = 20  # Rough estimate for global distribution
                            elif '200' in price_class:
                                base_cost = 15  # US, Europe, Asia
                            else:
                                base_cost = 10  # US and Europe only
                        
                        # Note: Actual costs heavily depend on data transfer
                        
                        resources.append(Resource(
                            id=distribution_id,
                            type='Distribution',
                            service='CloudFront',
                            name=tags.get('Name', dist_config.get('Comment', distribution_id)),
                            region='global',
                            created_at=item.get('LastModifiedTime'),
                            state='Enabled' if enabled else 'Disabled',
                            estimated_monthly_cost=base_cost,
                            additional_info={
                                'domainName': item.get('DomainName'),
                                'aliases': item.get('Aliases', {}).get('Items', []),
                                'priceClass': price_class,
                                'httpVersion': item.get('HttpVersion'),
                                'isIPV6Enabled': item.get('IsIPV6Enabled'),
                                'viewerCertificate': item.get('ViewerCertificate', {}).get('CertificateSource'),
                                'webACLId': item.get('WebACLId'),
                                'comment': dist_config.get('Comment'),
                                'origins': len(dist_config.get('Origins', {}).get('Items', [])),
                                'tags': tags
                            }
                        ))
                        
                    except Exception as e:
                        self.handle_error(e, f'CloudFront Distribution {distribution_id}')
                        
        except Exception as e:
            self.handle_error(e, 'CloudFront Distributions')
        
        return resources