import boto3
from typing import List
from .base_scanner import BaseScanner
from ..types import Resource


class VPCScanner(BaseScanner):
    @property
    def service_name(self) -> str:
        return 'VPC'
    
    
    def scan_single_region(self, region: str) -> List[Resource]:
        ec2_client = boto3.client('ec2', region_name=region)
        resources: List[Resource] = []
        
        # Scan VPCs (excluding default VPCs)
        self._scan_vpcs(ec2_client, region, resources)
        
        # Scan Transit Gateways
        self._scan_transit_gateways(ec2_client, region, resources)
        
        # Scan Transit Gateway Attachments
        self._scan_transit_gateway_attachments(ec2_client, region, resources)
        
        # Scan VPC Endpoints
        self._scan_vpc_endpoints(ec2_client, region, resources)
        
        # Scan VPN Connections
        self._scan_vpn_connections(ec2_client, region, resources)
        
        # Scan Direct Connect Virtual Interfaces
        self._scan_direct_connect(region, resources)
        
        return resources
    
    def _scan_vpcs(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_vpcs')
            
            for page in paginator.paginate():
                for vpc in page.get('Vpcs', []):
                    # Skip default VPCs
                    if vpc.get('IsDefault', False):
                        continue
                        
                    tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
                    
                    resources.append(Resource(
                        id=vpc.get('VpcId', 'Unknown'),
                        type='VPC',
                        service='VPC',
                        name=tags.get('Name', vpc.get('VpcId')),
                        region=region,
                        state=vpc.get('State'),
                        estimated_monthly_cost=0,  # VPCs themselves are free
                        additional_info={
                            'cidrBlock': vpc.get('CidrBlock'),
                            'isDefault': vpc.get('IsDefault'),
                            'enableDnsHostnames': vpc.get('EnableDnsHostnames'),
                            'enableDnsSupport': vpc.get('EnableDnsSupport'),
                            'tags': tags
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'VPCs')
    
    def _scan_transit_gateways(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_transit_gateways')
            
            for page in paginator.paginate():
                for tgw in page.get('TransitGateways', []):
                    if tgw.get('State') not in ['deleted', 'deleting']:
                        tags = {tag['Key']: tag['Value'] for tag in tgw.get('Tags', [])}
                        
                        # Transit Gateway pricing: $0.05 per hour = ~$36.50/month
                        # Plus $0.02 per GB data processed
                        base_cost = 36.50 if tgw.get('State') == 'available' else 0
                        
                        resources.append(Resource(
                            id=tgw.get('TransitGatewayId', 'Unknown'),
                            type='Transit Gateway',
                            service='VPC',
                            name=tags.get('Name', tgw.get('TransitGatewayId')),
                            region=region,
                            created_at=tgw.get('CreationTime'),
                            state=tgw.get('State'),
                            estimated_monthly_cost=base_cost,
                            additional_info={
                                'description': tgw.get('Description'),
                                'amazonSideAsn': tgw.get('Options', {}).get('AmazonSideAsn'),
                                'dnsSupport': tgw.get('Options', {}).get('DnsSupport'),
                                'vpnEcmpSupport': tgw.get('Options', {}).get('VpnEcmpSupport'),
                                'defaultRouteTableId': tgw.get('Options', {}).get('AssociationDefaultRouteTableId'),
                                'tags': tags
                            }
                        ))
        except Exception as e:
            self.handle_error(e, 'Transit Gateways')
    
    def _scan_transit_gateway_attachments(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_transit_gateway_attachments')
            
            for page in paginator.paginate():
                for attachment in page.get('TransitGatewayAttachments', []):
                    if attachment.get('State') not in ['deleted', 'deleting']:
                        tags = {tag['Key']: tag['Value'] for tag in attachment.get('Tags', [])}
                        
                        # Transit Gateway attachment pricing: $0.05 per hour = ~$36.50/month
                        # Only for VPN attachments; VPC attachments are free
                        attachment_type = attachment.get('ResourceType')
                        base_cost = 0
                        if attachment_type == 'vpn' and attachment.get('State') == 'available':
                            base_cost = 36.50
                        
                        resources.append(Resource(
                            id=attachment.get('TransitGatewayAttachmentId', 'Unknown'),
                            type=f'Transit Gateway {attachment_type} Attachment',
                            service='VPC',
                            name=tags.get('Name', attachment.get('TransitGatewayAttachmentId')),
                            region=region,
                            created_at=attachment.get('CreationTime'),
                            state=attachment.get('State'),
                            estimated_monthly_cost=base_cost,
                            additional_info={
                                'transitGatewayId': attachment.get('TransitGatewayId'),
                                'resourceType': attachment_type,
                                'resourceId': attachment.get('ResourceId'),
                                'resourceOwnerId': attachment.get('ResourceOwnerId'),
                                'tags': tags
                            }
                        ))
        except Exception as e:
            self.handle_error(e, 'Transit Gateway Attachments')
    
    def _scan_vpc_endpoints(self, client, region: str, resources: List[Resource]) -> None:
        try:
            paginator = client.get_paginator('describe_vpc_endpoints')
            
            for page in paginator.paginate():
                for endpoint in page.get('VpcEndpoints', []):
                    if endpoint.get('State') not in ['deleted', 'deleting']:
                        tags = {tag['Key']: tag['Value'] for tag in endpoint.get('Tags', [])}
                        
                        # VPC Endpoint pricing
                        endpoint_type = endpoint.get('VpcEndpointType')
                        base_cost = 0
                        
                        if endpoint_type == 'Interface':
                            # Interface endpoints: $0.01 per hour = ~$7.30/month
                            # Plus $0.01 per GB data processed
                            base_cost = 7.30 if endpoint.get('State') == 'available' else 0
                        # Gateway endpoints (S3, DynamoDB) are free
                        
                        resources.append(Resource(
                            id=endpoint.get('VpcEndpointId', 'Unknown'),
                            type=f'{endpoint_type} VPC Endpoint',
                            service='VPC',
                            name=tags.get('Name', endpoint.get('VpcEndpointId')),
                            region=region,
                            created_at=endpoint.get('CreationTimestamp'),
                            state=endpoint.get('State'),
                            estimated_monthly_cost=base_cost,
                            additional_info={
                                'serviceName': endpoint.get('ServiceName'),
                                'vpcId': endpoint.get('VpcId'),
                                'routeTableIds': endpoint.get('RouteTableIds', []),
                                'subnetIds': endpoint.get('SubnetIds', []),
                                'securityGroupIds': [sg.get('GroupId') for sg in endpoint.get('Groups', [])],
                                'privateDnsEnabled': endpoint.get('PrivateDnsEnabled'),
                                'tags': tags
                            }
                        ))
        except Exception as e:
            self.handle_error(e, 'VPC Endpoints')
    
    def _scan_vpn_connections(self, client, region: str, resources: List[Resource]) -> None:
        try:
            response = client.describe_vpn_connections()
            
            for vpn in response.get('VpnConnections', []):
                if vpn.get('State') not in ['deleted', 'deleting']:
                    tags = {tag['Key']: tag['Value'] for tag in vpn.get('Tags', [])}
                    
                    # VPN Connection pricing: $0.05 per hour = ~$36.50/month
                    base_cost = 36.50 if vpn.get('State') == 'available' else 0
                    
                    resources.append(Resource(
                        id=vpn.get('VpnConnectionId', 'Unknown'),
                        type='VPN Connection',
                        service='VPC',
                        name=tags.get('Name', vpn.get('VpnConnectionId')),
                        region=region,
                        state=vpn.get('State'),
                        estimated_monthly_cost=base_cost,
                        additional_info={
                            'type': vpn.get('Type'),
                            'customerGatewayId': vpn.get('CustomerGatewayId'),
                            'vpnGatewayId': vpn.get('VpnGatewayId'),
                            'transitGatewayId': vpn.get('TransitGatewayId'),
                            'category': vpn.get('Category'),
                            'tags': tags
                        }
                    ))
        except Exception as e:
            self.handle_error(e, 'VPN Connections')
    
    def _scan_direct_connect(self, region: str, resources: List[Resource]) -> None:
        try:
            dx_client = boto3.client('directconnect', region_name=region)
            
            # Virtual Interfaces
            response = dx_client.describe_virtual_interfaces()
            
            for vif in response.get('virtualInterfaces', []):
                if vif.get('virtualInterfaceState') not in ['deleted', 'deleting']:
                    # Direct Connect virtual interface pricing varies by port speed
                    # This is a rough estimate - actual costs depend on port speed and data transfer
                    base_cost = 30 if vif.get('virtualInterfaceState') == 'available' else 0
                    
                    resources.append(Resource(
                        id=vif.get('virtualInterfaceId', 'Unknown'),
                        type='Direct Connect Virtual Interface',
                        service='VPC',
                        name=vif.get('virtualInterfaceName', vif.get('virtualInterfaceId')),
                        region=region,
                        state=vif.get('virtualInterfaceState'),
                        estimated_monthly_cost=base_cost,
                        additional_info={
                            'connectionId': vif.get('connectionId'),
                            'vlan': vif.get('vlan'),
                            'asn': vif.get('asn'),
                            'amazonSideAsn': vif.get('amazonSideAsn'),
                            'virtualInterfaceType': vif.get('virtualInterfaceType'),
                            'bandwidth': vif.get('bandwidth')
                        }
                    ))
                    
        except Exception as e:
            self.handle_error(e, 'Direct Connect')