import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class DynamoDBScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'DynamoDB'
    
    def scan_single_region(self, region: str) -> List[Resource]:
        client = boto3.client('dynamodb', region_name=region)
        resources: List[Resource] = []
        
        try:
            paginator = client.get_paginator('list_tables')
            all_tables = []
            
            # Get all table names
            for page in paginator.paginate():
                all_tables.extend(page.get('TableNames', []))
            
            # Get details for each table
            for table_name in all_tables:
                try:
                    response = client.describe_table(TableName=table_name)
                    table = response.get('Table')
                    if not table:
                        continue
                    
                    estimated_cost = 0
                    
                    # Calculate cost based on billing mode
                    billing_mode = table.get('BillingModeSummary', {}).get('BillingMode')
                    if billing_mode == 'PAY_PER_REQUEST':
                        # On-demand pricing - rough estimate
                        estimated_cost = 5  # Base estimate for on-demand
                    else:
                        # Provisioned capacity
                        provisioned = table.get('ProvisionedThroughput', {})
                        read_units = provisioned.get('ReadCapacityUnits', 0)
                        write_units = provisioned.get('WriteCapacityUnits', 0)
                        
                        # $0.00065 per RCU per hour = ~$0.47 per month
                        # $0.00065 per WCU per hour = ~$0.47 per month
                        estimated_cost = (read_units * 0.47) + (write_units * 0.47)
                    
                    # Add storage cost: $0.25 per GB per month
                    size_bytes = table.get('TableSizeBytes', 0)
                    size_gb = size_bytes / (1024 * 1024 * 1024)
                    estimated_cost += size_gb * 0.25
                    
                    resources.append(Resource(
                        id=table.get('TableArn', table_name),
                        type='Table',
                        service='DynamoDB',
                        name=table_name,
                        region=region,
                        created_at=table.get('CreationDateTime'),
                        state=table.get('TableStatus'),
                        estimated_monthly_cost=estimated_cost,
                        additional_info={
                            'billingMode': billing_mode or 'PROVISIONED',
                            'itemCount': table.get('ItemCount'),
                            'sizeBytes': size_bytes,
                            'sizeGB': f"{size_gb:.2f}",
                            'readCapacityUnits': provisioned.get('ReadCapacityUnits'),
                            'writeCapacityUnits': provisioned.get('WriteCapacityUnits')
                        }
                    ))
                except Exception as e:
                    print(f"Error describing table {table_name}: {e}")
        except Exception as e:
            self.handle_error(e, 'DynamoDB Tables')
        
        return resources