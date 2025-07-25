import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class APIGatewayScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'API Gateway'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        resources: List[Resource] = []
        
        # Scan REST APIs
        self._scan_rest_apis(region, resources)
        
        # Scan HTTP/WebSocket APIs (API Gateway V2)
        self._scan_http_apis(region, resources)
        
        return resources
    
    def _scan_rest_apis(self, region: str, resources: List[Resource]) -> None:
        client = boto3.client('apigateway', region_name=region)
        
        try:
            paginator = client.get_paginator('get_rest_apis')
            
            for page in paginator.paginate():
                for api in page.get('items', []):
                    api_id = api.get('id', 'Unknown')
                    
                    # Get deployment stage information
                    stages = []
                    stage_count = 0
                    try:
                        stages_response = client.get_stages(restApiId=api_id)
                        stages = stages_response.get('item', [])
                        stage_count = len(stages)
                    except:
                        pass
                    
                    # Get tags
                    tags = api.get('tags', {})
                    
                    # REST API pricing: Based on API calls
                    # $3.50 per million API calls (first 333 million)
                    # This is a rough estimate assuming moderate usage
                    # Actual cost depends on number of API calls
                    estimated_calls_per_month = 1000000  # 1M calls/month assumption
                    api_call_cost = (estimated_calls_per_month / 1000000) * 3.50
                    
                    # Cache costs (if enabled)
                    cache_cost = 0
                    for stage in stages:
                        if stage.get('cacheClusterEnabled'):
                            cache_size = stage.get('cacheClusterSize', '0.5')
                            # Cache pricing varies by size
                            if cache_size == '0.5':
                                cache_cost += 38  # $0.02/hour
                            elif cache_size == '1.6':
                                cache_cost += 106  # $0.04/hour
                            elif cache_size == '6.1':
                                cache_cost += 365  # $0.50/hour
                    
                    total_cost = api_call_cost + cache_cost
                    
                    resources.append(Resource(
                        id=api_id,
                        type='REST API',
                        service='API Gateway',
                        name=tags.get('Name', api.get('name', api_id)),
                        region=region,
                        created_at=api.get('createdDate'),
                        state='available',
                        estimated_monthly_cost=total_cost,
                        additional_info={
                            'apiName': api.get('name'),
                            'description': api.get('description'),
                            'endpointTypes': api.get('endpointConfiguration', {}).get('types', []),
                            'apiKeySource': api.get('apiKeySource'),
                            'minimumCompressionSize': api.get('minimumCompressionSize'),
                            'stageCount': stage_count,
                            'cacheEnabled': any(s.get('cacheClusterEnabled') for s in stages),
                            'tags': tags
                        }
                    ))
                    
        except Exception as e:
            self.handle_error(e, 'REST APIs')
    
    def _scan_http_apis(self, region: str, resources: List[Resource]) -> None:
        client = boto3.client('apigatewayv2', region_name=region)
        
        try:
            paginator = client.get_paginator('get_apis')
            
            for page in paginator.paginate():
                for api in page.get('Items', []):
                    api_id = api.get('ApiId', 'Unknown')
                    protocol_type = api.get('ProtocolType', 'HTTP')
                    
                    # Get stages
                    stages = []
                    stage_count = 0
                    try:
                        stages_response = client.get_stages(ApiId=api_id)
                        stages = stages_response.get('Items', [])
                        stage_count = len(stages)
                    except:
                        pass
                    
                    # Get tags
                    tags = api.get('Tags', {})
                    
                    # HTTP API pricing: $1.00 per million API calls
                    # WebSocket API pricing: $1.00 per million messages + connection fees
                    if protocol_type == 'WEBSOCKET':
                        # WebSocket: $0.25 per million connection minutes
                        estimated_connections = 100  # Assumption
                        estimated_minutes_per_connection = 60  # 1 hour average
                        connection_cost = (estimated_connections * estimated_minutes_per_connection * 30 / 1000000) * 0.25
                        
                        estimated_messages = 1000000  # 1M messages/month
                        message_cost = (estimated_messages / 1000000) * 1.00
                        
                        total_cost = connection_cost + message_cost
                    else:
                        # HTTP API
                        estimated_calls_per_month = 1000000  # 1M calls/month assumption
                        total_cost = (estimated_calls_per_month / 1000000) * 1.00
                    
                    resources.append(Resource(
                        id=api_id,
                        type=f'{protocol_type} API',
                        service='API Gateway',
                        name=tags.get('Name', api.get('Name', api_id)),
                        region=region,
                        created_at=api.get('CreatedDate'),
                        state='available',
                        estimated_monthly_cost=total_cost,
                        additional_info={
                            'apiName': api.get('Name'),
                            'description': api.get('Description'),
                            'protocolType': protocol_type,
                            'apiEndpoint': api.get('ApiEndpoint'),
                            'corsConfiguration': bool(api.get('CorsConfiguration')),
                            'disableExecuteApiEndpoint': api.get('DisableExecuteApiEndpoint', False),
                            'stageCount': stage_count,
                            'tags': tags
                        }
                    ))
                    
        except Exception as e:
            self.handle_error(e, 'HTTP/WebSocket APIs')