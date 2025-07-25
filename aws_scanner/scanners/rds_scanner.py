import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class RDSScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'RDS'
    
    def scan_single_region(self, region: str) -> List[Resource]:
        client = boto3.client('rds', region_name=region)
        resources: List[Resource] = []
        
        # Scan DB Instances
        self._scan_db_instances(client, region, resources)
        
        # Scan DB Clusters (Aurora)
        self._scan_db_clusters(client, region, resources)
        
        # Scan DB Snapshots
        self._scan_db_snapshots(client, region, resources)
        
        return resources
    
    def _scan_db_instances(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_db_instances')
            
            for page in paginator.paginate():
                for instance in page.get('DBInstances', []):
                    # Cost estimation based on instance class
                    instance_class = instance.get('DBInstanceClass', '')
                    estimated_cost = 50  # Default
                    if 'db.t3.micro' in instance_class:
                        estimated_cost = 12
                    elif 'db.t3.small' in instance_class:
                        estimated_cost = 25
                    elif 'db.t3.medium' in instance_class:
                        estimated_cost = 50
                    elif 'db.r5.large' in instance_class:
                        estimated_cost = 180
                    elif 'db.r5.xlarge' in instance_class:
                        estimated_cost = 360
                    
                    # Add storage cost
                    storage_gb = instance.get('AllocatedStorage', 0)
                    storage_cost = storage_gb * 0.115  # ~$0.115 per GB per month for gp2
                    
                    resources.append(Resource(
                        id=instance.get('DBInstanceIdentifier', 'Unknown'),
                        type='DB Instance',
                        service='RDS',
                        name=instance.get('DBInstanceIdentifier'),
                        region=region,
                        created_at=instance.get('InstanceCreateTime'),
                        state=instance.get('DBInstanceStatus'),
                        estimated_monthly_cost=estimated_cost + storage_cost if instance.get('DBInstanceStatus') == 'available' else 0,
                        additional_info={
                            'engine': instance.get('Engine'),
                            'engineVersion': instance.get('EngineVersion'),
                            'instanceClass': instance.get('DBInstanceClass'),
                            'allocatedStorage': f"{storage_gb} GB",
                            'multiAZ': instance.get('MultiAZ'),
                            'endpoint': instance.get('Endpoint', {}).get('Address')
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'RDS DB Instances')
    
    def _scan_db_clusters(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_db_clusters')
            
            for page in paginator.paginate():
                for cluster in page.get('DBClusters', []):
                    # Aurora pricing is complex, providing rough estimate
                    member_count = len(cluster.get('DBClusterMembers', []))
                    estimated_cost = member_count * 100  # Rough estimate per instance
                    
                    resources.append(Resource(
                        id=cluster.get('DBClusterIdentifier', 'Unknown'),
                        type='DB Cluster',
                        service='RDS',
                        name=cluster.get('DBClusterIdentifier'),
                        region=region,
                        created_at=cluster.get('ClusterCreateTime'),
                        state=cluster.get('Status'),
                        estimated_monthly_cost=estimated_cost if cluster.get('Status') == 'available' else 0,
                        additional_info={
                            'engine': cluster.get('Engine'),
                            'engineVersion': cluster.get('EngineVersion'),
                            'memberCount': member_count,
                            'allocatedStorage': cluster.get('AllocatedStorage'),
                            'endpoint': cluster.get('Endpoint')
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'RDS DB Clusters')
    
    def _scan_db_snapshots(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_db_snapshots')
            
            for page in paginator.paginate(SnapshotType='manual'):
                for snapshot in page.get('DBSnapshots', []):
                    # Snapshot storage: ~$0.095 per GB per month
                    storage_gb = snapshot.get('AllocatedStorage', 0)
                    estimated_cost = storage_gb * 0.095
                    
                    resources.append(Resource(
                        id=snapshot.get('DBSnapshotIdentifier', 'Unknown'),
                        type='DB Snapshot',
                        service='RDS',
                        name=snapshot.get('DBSnapshotIdentifier'),
                        region=region,
                        created_at=snapshot.get('SnapshotCreateTime'),
                        state=snapshot.get('Status'),
                        estimated_monthly_cost=estimated_cost,
                        additional_info={
                            'engine': snapshot.get('Engine'),
                            'allocatedStorage': f"{storage_gb} GB",
                            'encrypted': snapshot.get('Encrypted'),
                            'sourceDBInstance': snapshot.get('DBInstanceIdentifier')
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'RDS DB Snapshots')