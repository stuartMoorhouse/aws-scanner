import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class ECSScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'ECS'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        client = boto3.client('ecs', region_name=region)
        resources: List[Resource] = []
        
        try:
            # Get all clusters
            clusters = []
            list_clusters_paginator = client.get_paginator('list_clusters')
            for page in list_clusters_paginator.paginate():
                clusters.extend(page.get('clusterArns', []))
            
            if not clusters:
                return resources
            
            # Describe clusters in batches (max 100)
            for i in range(0, len(clusters), 100):
                batch = clusters[i:i+100]
                describe_response = client.describe_clusters(
                    clusters=batch,
                    include=['STATISTICS', 'TAGS']
                )
                
                for cluster in describe_response.get('clusters', []):
                    cluster_name = cluster.get('clusterName', 'Unknown')
                    cluster_arn = cluster.get('clusterArn', '')
                    
                    # Get tags
                    tags = {}
                    for tag in cluster.get('tags', []):
                        tags[tag.get('key', '')] = tag.get('value', '')
                    
                    # Cost estimation based on running tasks
                    # Note: Fargate tasks have their own pricing, EC2 tasks use EC2 pricing
                    running_tasks = cluster.get('runningTasksCount', 0)
                    active_services = cluster.get('activeServicesCount', 0)
                    
                    # This is a rough estimate - actual cost depends on task size and type
                    # Assuming mix of Fargate and EC2 tasks
                    estimated_cost = 0
                    if running_tasks > 0:
                        # Rough estimate: $0.04/hour per vCPU, $0.004/hour per GB for Fargate
                        # Assuming average task: 0.5 vCPU, 1GB memory
                        estimated_cost = running_tasks * (0.04 * 0.5 + 0.004 * 1) * 730  # Monthly hours
                    
                    resources.append(Resource(
                        id=cluster_arn,
                        type='Cluster',
                        service='ECS',
                        name=tags.get('Name', cluster_name),
                        region=region,
                        state='ACTIVE' if cluster.get('status') == 'ACTIVE' else cluster.get('status'),
                        estimated_monthly_cost=estimated_cost,
                        additional_info={
                            'clusterName': cluster_name,
                            'runningTasksCount': running_tasks,
                            'pendingTasksCount': cluster.get('pendingTasksCount', 0),
                            'activeServicesCount': active_services,
                            'registeredContainerInstancesCount': cluster.get('registeredContainerInstancesCount', 0),
                            'capacityProviders': cluster.get('capacityProviders', []),
                            'tags': tags
                        }
                    ))
                    
                    # Scan services in this cluster
                    self._scan_services(client, cluster_arn, region, resources)
                    
        except Exception as e:
            self.handle_error(e, 'ECS Clusters')
        
        return resources
    
    def _scan_services(self, client, cluster_arn: str, region: str, resources: List[Resource]) -> None:
        try:
            services = []
            list_services_paginator = client.get_paginator('list_services')
            
            for page in list_services_paginator.paginate(cluster=cluster_arn):
                services.extend(page.get('serviceArns', []))
            
            if not services:
                return
            
            # Describe services in batches (max 10)
            for i in range(0, len(services), 10):
                batch = services[i:i+10]
                describe_response = client.describe_services(
                    cluster=cluster_arn,
                    services=batch,
                    include=['TAGS']
                )
                
                for service in describe_response.get('services', []):
                    service_name = service.get('serviceName', 'Unknown')
                    
                    # Get tags
                    tags = {}
                    for tag in service.get('tags', []):
                        tags[tag.get('key', '')] = tag.get('value', '')
                    
                    # Cost estimation based on desired count and launch type
                    desired_count = service.get('desiredCount', 0)
                    launch_type = service.get('launchType', 'EC2')
                    
                    estimated_cost = 0
                    if desired_count > 0 and launch_type == 'FARGATE':
                        # Fargate pricing estimate
                        task_def = service.get('taskDefinition', '')
                        # Rough estimate: 0.5 vCPU, 1GB per task
                        estimated_cost = desired_count * (0.04 * 0.5 + 0.004 * 1) * 730
                    # EC2 launch type costs are included in EC2 instance costs
                    
                    resources.append(Resource(
                        id=service.get('serviceArn', ''),
                        type='Service',
                        service='ECS',
                        name=tags.get('Name', service_name),
                        region=region,
                        created_at=service.get('createdAt'),
                        state=service.get('status'),
                        estimated_monthly_cost=estimated_cost,
                        additional_info={
                            'serviceName': service_name,
                            'launchType': launch_type,
                            'desiredCount': desired_count,
                            'runningCount': service.get('runningCount', 0),
                            'pendingCount': service.get('pendingCount', 0),
                            'taskDefinition': service.get('taskDefinition', '').split('/')[-1] if service.get('taskDefinition') else '',
                            'deploymentController': service.get('deploymentController', {}).get('type'),
                            'tags': tags
                        }
                    ))
                    
        except Exception as e:
            self.handle_error(e, f'ECS Services in cluster {cluster_arn}')