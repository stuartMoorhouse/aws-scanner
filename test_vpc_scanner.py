#!/usr/bin/env python3
"""Test script to run only the VPC scanner and display results."""
import os
import sys
import boto3
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aws_scanner.scanners.vpc_scanner import VPCScanner
from aws_scanner.types import Resource

console = Console()

def get_all_regions():
    """Get all available AWS regions."""
    try:
        client = boto3.client('ec2', region_name='us-east-1')
        response = client.describe_regions()
        return sorted([region['RegionName'] for region in response['Regions']])
    except Exception as e:
        console.print(f"[red]Error fetching regions: {e}[/red]")
        return []

def display_resources(resources: list[Resource]):
    """Display resources in a formatted table."""
    if not resources:
        console.print("[yellow]No VPC resources found (excluding default VPCs).[/yellow]")
        return
    
    # Group resources by type
    by_type = {}
    for resource in resources:
        if resource.type not in by_type:
            by_type[resource.type] = []
        by_type[resource.type].append(resource)
    
    # Create a tree view
    tree = Tree("[bold cyan]VPC Resources Found[/bold cyan]")
    
    for resource_type, type_resources in sorted(by_type.items()):
        type_node = tree.add(f"[green]{resource_type}[/green] ({len(type_resources)} items)")
        
        # Create table for this resource type
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Region", style="cyan")
        table.add_column("ID", style="yellow")
        table.add_column("Name", style="green")
        table.add_column("State", style="blue")
        table.add_column("Monthly Cost", justify="right", style="red")
        
        # Add additional info columns based on resource type
        if resource_type == 'VPC':
            table.add_column("CIDR Block", style="white")
            table.add_column("DNS Support", style="white")
        elif resource_type == 'Transit Gateway':
            table.add_column("ASN", style="white")
            table.add_column("DNS Support", style="white")
        elif 'VPC Endpoint' in resource_type:
            table.add_column("Service", style="white")
            table.add_column("VPC ID", style="white")
        
        for resource in sorted(type_resources, key=lambda r: (r.region, r.name or r.id)):
            row = [
                resource.region,
                resource.id,
                resource.name or "-",
                resource.state or "active",
                f"${resource.estimated_monthly_cost:,.2f}"
            ]
            
            # Add additional info based on type
            if resource_type == 'VPC':
                info = resource.additional_info or {}
                row.extend([
                    info.get('cidrBlock', '-'),
                    str(info.get('enableDnsSupport', '-'))
                ])
            elif resource_type == 'Transit Gateway':
                info = resource.additional_info or {}
                row.extend([
                    str(info.get('amazonSideAsn', '-')),
                    str(info.get('dnsSupport', '-'))
                ])
            elif 'VPC Endpoint' in resource_type:
                info = resource.additional_info or {}
                row.extend([
                    info.get('serviceName', '-'),
                    info.get('vpcId', '-')
                ])
            
            table.add_row(*row)
        
        console.print(table)
        console.print()

def main():
    """Main function to test VPC scanner."""
    console.print("[bold cyan]VPC Scanner Test[/bold cyan]")
    console.print("=" * 50)
    
    # Check for AWS credentials
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        console.print("[bold red]Error:[/bold red] AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables must be set")
        sys.exit(1)
    
    console.print("[green]✓[/green] Using AWS credentials from environment variables\n")
    
    try:
        # Get regions
        console.print("[cyan]Fetching AWS regions...[/cyan]")
        regions = get_all_regions()
        console.print(f"[green]✓[/green] Found {len(regions)} regions\n")
        
        # Create VPC scanner
        scanner = VPCScanner(regions)
        
        # Scan all regions
        console.print("[cyan]Scanning VPC resources across all regions...[/cyan]")
        all_resources = scanner.scan_all_regions()
        
        console.print(f"\n[bold green]Scan complete![/bold green] Found {len(all_resources)} resources\n")
        
        # Display detailed results
        display_resources(all_resources)
        
        # Summary
        total_cost = sum(r.estimated_monthly_cost or 0 for r in all_resources)
        console.print(f"\n[bold]Total Estimated Monthly Cost:[/bold] [yellow]${total_cost:,.2f}[/yellow]")
        
        # Count by region
        by_region = {}
        for resource in all_resources:
            if resource.region not in by_region:
                by_region[resource.region] = 0
            by_region[resource.region] += 1
        
        if by_region:
            console.print("\n[bold]Resources by Region:[/bold]")
            for region, count in sorted(by_region.items()):
                console.print(f"  {region}: {count}")
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()