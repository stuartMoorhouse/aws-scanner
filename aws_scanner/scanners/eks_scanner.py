import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class EKSScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'EKS'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        client = boto3.client('eks', region_name=region)
        resources: List[Resource] = []
        
        try:
            # List all EKS clusters
            clusters = []
            list_clusters_paginator = client.get_paginator('list_clusters')
            
            for page in list_clusters_paginator.paginate():
                clusters.extend(page.get('clusters', []))
            
            # Describe each cluster
            for cluster_name in clusters:
                try:
                    cluster_response = client.describe_cluster(name=cluster_name)
                    cluster = cluster_response.get('cluster', {})
                    
                    # EKS Control Plane costs $0.10 per hour = ~$73/month
                    control_plane_cost = 73
                    
                    # Get node groups for this cluster
                    node_groups = []
                    nodegroup_cost = 0
                    try:
                        ng_response = client.list_nodegroups(clusterName=cluster_name)
                        node_groups = ng_response.get('nodegroups', [])
                        
                        # Get node group details for cost estimation
                        for ng_name in node_groups:
                            ng_detail = client.describe_nodegroup(
                                clusterName=cluster_name,
                                nodegroupName=ng_name
                            )
                            nodegroup = ng_detail.get('nodegroup', {})
                            
                            # Estimate based on desired size and instance type
                            desired_size = nodegroup.get('scalingConfig', {}).get('desiredSize', 0)
                            instance_types = nodegroup.get('instanceTypes', ['t3.medium'])
                            
                            # Rough cost per instance (t3.medium as default)
                            cost_per_instance = 30  # ~$30/month for t3.medium
                            if instance_types:
                                instance_type = instance_types[0]
                                if 't3.small' in instance_type:
                                    cost_per_instance = 15
                                elif 't3.large' in instance_type:
                                    cost_per_instance = 60
                                elif 'm5.large' in instance_type:
                                    cost_per_instance = 70
                                elif 'm5.xlarge' in instance_type:
                                    cost_per_instance = 140
                            
                            nodegroup_cost += desired_size * cost_per_instance
                            
                    except Exception as e:
                        self.handle_error(e, f'EKS Node Groups for {cluster_name}')
                    
                    total_cost = control_plane_cost + nodegroup_cost
                    
                    resources.append(Resource(
                        id=cluster.get('arn', ''),
                        type='Cluster',
                        service='EKS',
                        name=cluster_name,
                        region=region,
                        created_at=cluster.get('createdAt'),
                        state=cluster.get('status'),
                        estimated_monthly_cost=total_cost if cluster.get('status') == 'ACTIVE' else 0,
                        additional_info={
                            'version': cluster.get('version'),
                            'platformVersion': cluster.get('platformVersion'),
                            'endpoint': cluster.get('endpoint'),
                            'nodeGroupCount': len(node_groups),
                            'nodeGroups': node_groups,
                            'controlPlaneCost': control_plane_cost,
                            'nodeGroupCost': nodegroup_cost,
                            'logging': cluster.get('logging', {}).get('clusterLogging', []),
                            'tags': cluster.get('tags', {})
                        }
                    ))
                    
                    # Add node groups as separate resources
                    self._scan_node_groups(client, cluster_name, region, resources)
                    
                except Exception as e:
                    self.handle_error(e, f'EKS Cluster {cluster_name}')
                    
        except Exception as e:
            self.handle_error(e, 'EKS Clusters')
        
        return resources
    
    def _scan_node_groups(self, client, cluster_name: str, region: str, resources: List[Resource]) -> None:
        try:
            response = client.list_nodegroups(clusterName=cluster_name)
            node_groups = response.get('nodegroups', [])
            
            for ng_name in node_groups:
                try:
                    ng_response = client.describe_nodegroup(
                        clusterName=cluster_name,
                        nodegroupName=ng_name
                    )
                    nodegroup = ng_response.get('nodegroup', {})
                    
                    # Calculate node group cost
                    scaling_config = nodegroup.get('scalingConfig', {})
                    desired_size = scaling_config.get('desiredSize', 0)
                    instance_types = nodegroup.get('instanceTypes', ['t3.medium'])
                    
                    # Estimate cost based on instance type
                    cost_per_instance = 30  # Default for t3.medium
                    if instance_types:
                        instance_type = instance_types[0]
                        if 't3.micro' in instance_type:
                            cost_per_instance = 7.5
                        elif 't3.small' in instance_type:
                            cost_per_instance = 15
                        elif 't3.large' in instance_type:
                            cost_per_instance = 60
                        elif 'm5.large' in instance_type:
                            cost_per_instance = 70
                        elif 'm5.xlarge' in instance_type:
                            cost_per_instance = 140
                        elif 'm5.2xlarge' in instance_type:
                            cost_per_instance = 280
                    
                    total_cost = desired_size * cost_per_instance
                    
                    resources.append(Resource(
                        id=nodegroup.get('nodegroupArn', ''),
                        type='Node Group',
                        service='EKS',
                        name=ng_name,
                        region=region,
                        created_at=nodegroup.get('createdAt'),
                        state=nodegroup.get('status'),
                        estimated_monthly_cost=total_cost if nodegroup.get('status') == 'ACTIVE' else 0,
                        additional_info={
                            'clusterName': cluster_name,
                            'instanceTypes': instance_types,
                            'desiredSize': desired_size,
                            'minSize': scaling_config.get('minSize', 0),
                            'maxSize': scaling_config.get('maxSize', 0),
                            'diskSize': nodegroup.get('diskSize'),
                            'amiType': nodegroup.get('amiType'),
                            'capacityType': nodegroup.get('capacityType', 'ON_DEMAND'),
                            'tags': nodegroup.get('tags', {})
                        }
                    ))
                    
                except Exception as e:
                    self.handle_error(e, f'EKS Node Group {ng_name}')
                    
        except Exception as e:
            self.handle_error(e, f'EKS Node Groups for cluster {cluster_name}')