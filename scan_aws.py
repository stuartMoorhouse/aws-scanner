#!/usr/bin/env python3
"""AWS Resource Scanner - Main entry point."""
import os
import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict
from itertools import groupby
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import boto3
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from aws_scanner.types import Resource, ServiceSummary
from aws_scanner.logger import setup_logging, get_logger
from aws_scanner.config import get_config
from aws_scanner.utils import retry_with_backoff
from aws_scanner.scanners import (
    EC2Scanner,
    S3Scanner,
    RDSScanner,
    LambdaScanner,
    DynamoDBScanner,
    ELBScanner,
    ECSScanner,
    EKSScanner,
    CloudFrontScanner,
    Route53Scanner,
    VPCScanner,
    APIGatewayScanner
)
from aws_scanner.scanners.base_scanner import BaseScanner

logger = get_logger(__name__)
console = Console()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Scan AWS resources across all regions and services',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Scan all regions and services
  %(prog)s --regions us-east-1       # Scan only us-east-1
  %(prog)s --skip-services EC2       # Skip EC2 scanning
  %(prog)s --output report.md        # Save report to specific file
  %(prog)s --format json             # Output in JSON format
        """
    )
    
    parser.add_argument(
        '--regions', 
        nargs='+',
        help='Specific regions to scan (default: all regions)'
    )
    parser.add_argument(
        '--skip-regions',
        nargs='+',
        help='Regions to skip'
    )
    parser.add_argument(
        '--services',
        nargs='+',
        help='Specific services to scan (default: all services)'
    )
    parser.add_argument(
        '--skip-services',
        nargs='+',
        help='Services to skip'
    )
    parser.add_argument(
        '--output',
        default='aws-resources-report.md',
        help='Output file path (default: aws-resources-report.md)'
    )
    parser.add_argument(
        '--format',
        choices=['markdown', 'json', 'csv'],
        default='markdown',
        help='Output format (default: markdown)'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    parser.add_argument(
        '--config',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    
    return parser.parse_args()


@retry_with_backoff()
def get_all_regions() -> List[str]:
    """
    Get all available AWS regions.
    
    Returns:
        List of region names
        
    Raises:
        Exception: If unable to fetch regions
    """
    try:
        client = boto3.client('ec2', region_name='us-east-1')
        response = client.describe_regions()
        return sorted([region['RegionName'] for region in response['Regions']])
    except Exception as e:
        logger.error(f"Error fetching regions: {e}")
        raise


def generate_markdown_report(resources: List[Resource]) -> str:
    """
    Generate a comprehensive markdown report of all resources.
    
    Args:
        resources: List of all discovered resources
        
    Returns:
        Markdown formatted report
    """
    timestamp = datetime.now().isoformat()
    report_lines = [
        "# AWS Resources Report",
        "",
        f"**Generated:** {timestamp}",
        f"**Total Resources Found:** {len(resources)}",
        ""
    ]
    
    if not resources:
        report_lines.append("No resources found.")
        return '\n'.join(report_lines)
    
    # Calculate total estimated monthly cost
    total_cost = sum(r.estimated_monthly_cost or 0 for r in resources)
    report_lines.append(f"**Total Estimated Monthly Cost:** ${total_cost:,.2f}")
    report_lines.append("")
    
    # Group resources by service using groupby
    resources_by_service = defaultdict(list)
    sorted_resources = sorted(resources, key=lambda r: r.service)
    for service, group in groupby(sorted_resources, key=lambda r: r.service):
        resources_by_service[service] = list(group)
    
    # Table of contents
    report_lines.extend([
        "## Table of Contents",
        ""
    ])
    for service in sorted(resources_by_service.keys()):
        anchor = service.lower().replace(' ', '-')
        report_lines.append(f"- [{service}](#{anchor})")
    report_lines.append("")
    
    # Summary by service
    report_lines.extend([
        "## Summary by Service",
        "",
        "| Service | Resource Count | Estimated Monthly Cost |",
        "|---------|----------------|----------------------|"
    ])
    
    service_summaries = []
    for service, service_resources in resources_by_service.items():
        service_cost = sum(r.estimated_monthly_cost or 0 for r in service_resources)
        report_lines.append(f"| {service} | {len(service_resources)} | ${service_cost:,.2f} |")
        
        # Calculate resources by region
        resources_by_region = defaultdict(int)
        for resource in service_resources:
            resources_by_region[resource.region] += 1
        
        service_summaries.append(ServiceSummary(
            service=service,
            total_resources=len(service_resources),
            total_estimated_monthly_cost=service_cost,
            resources_by_region=dict(resources_by_region)
        ))
    report_lines.append("")
    
    # Detailed resources by service
    for service, service_resources in sorted(resources_by_service.items()):
        report_lines.append(f"## {service}")
        report_lines.append("")
        
        # Group by region within service
        by_region = defaultdict(list)
        sorted_by_region = sorted(service_resources, key=lambda r: r.region)
        for region, group in groupby(sorted_by_region, key=lambda r: r.region):
            by_region[region] = list(group)
        
        for region, region_resources in sorted(by_region.items()):
            report_lines.extend([
                f"### {region}",
                ""
            ])
            
            # Different table format based on service
            if service == 'EC2':
                report_lines.extend([
                    "| Type | ID | Name | State | Monthly Cost | Details |",
                    "|------|-----|------|-------|--------------|----------|"
                ])
                
                for resource in region_resources:
                    details = []
                    info = resource.additional_info
                    if info.get('instanceType'):
                        details.append(info['instanceType'])
                    if info.get('size'):
                        details.append(f"{info['size']} GB")
                    if info.get('publicIp'):
                        details.append(f"IP: {info['publicIp']}")
                    
                    report_lines.append(
                        f"| {resource.type} "
                        f"| {resource.id} "
                        f"| {resource.name or '-'} "
                        f"| {resource.state or '-'} "
                        f"| ${(resource.estimated_monthly_cost or 0):,.2f} "
                        f"| {', '.join(details) or '-'} |"
                    )
            else:
                # Generic table for other services
                report_lines.extend([
                    "| Type | Name/ID | State | Monthly Cost | Details |",
                    "|------|---------|-------|--------------|----------|"
                ])
                
                for resource in region_resources:
                    # Extract key details from additional_info
                    details = [
                        f"{k}: {v}" for k, v in (resource.additional_info or {}).items()
                        if v and not isinstance(v, (dict, list))
                    ][:3]  # Limit to 3 details
                    
                    report_lines.append(
                        f"| {resource.type} "
                        f"| {resource.name or resource.id} "
                        f"| {resource.state or 'active'} "
                        f"| ${(resource.estimated_monthly_cost or 0):,.2f} "
                        f"| {', '.join(details) or '-'} |"
                    )
            report_lines.append("")
    
    # Cost breakdown
    report_lines.extend([
        "## Cost Breakdown",
        "",
        "### Top 10 Most Expensive Resources",
        "",
        "| Service | Type | Name/ID | Region | Monthly Cost |",
        "|---------|------|---------|--------|-------------|"
    ])
    
    # Sort by cost and get top 10
    expensive_resources = sorted(
        (r for r in resources if r.estimated_monthly_cost and r.estimated_monthly_cost > 0),
        key=lambda x: x.estimated_monthly_cost,
        reverse=True
    )[:10]
    
    for resource in expensive_resources:
        report_lines.append(
            f"| {resource.service} "
            f"| {resource.type} "
            f"| {resource.name or resource.id} "
            f"| {resource.region} "
            f"| ${resource.estimated_monthly_cost:,.2f} |"
        )
    
    return '\n'.join(report_lines)


def scan_services_concurrently(
    scanners: List[BaseScanner], 
    show_progress: bool = True
) -> List[Resource]:
    """
    Scan all services concurrently.
    
    Args:
        scanners: List of scanner instances
        show_progress: Whether to show progress bars
        
    Returns:
        List of all discovered resources
    """
    all_resources: List[Resource] = []
    config = get_config()
    
    if show_progress:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            # Create overall progress task
            overall_task = progress.add_task(
                "[cyan]Scanning AWS services...", 
                total=len(scanners)
            )
            
            # Scan services concurrently
            with ThreadPoolExecutor(max_workers=config.max_concurrent_services) as executor:
                # Submit all scan tasks
                future_to_scanner = {
                    executor.submit(scanner.scan_all_regions): scanner
                    for scanner in scanners
                }
                
                # Process completed scans
                for future in as_completed(future_to_scanner):
                    scanner = future_to_scanner[future]
                    try:
                        resources = future.result()
                        all_resources.extend(resources)
                        progress.update(overall_task, advance=1)
                    except Exception as e:
                        logger.error(f"Failed to scan {scanner.service_name}: {e}")
                        progress.update(overall_task, advance=1)
    else:
        # No progress bars
        with ThreadPoolExecutor(max_workers=config.max_concurrent_services) as executor:
            future_to_scanner = {
                executor.submit(scanner.scan_all_regions): scanner
                for scanner in scanners
            }
            
            for future in as_completed(future_to_scanner):
                scanner = future_to_scanner[future]
                try:
                    resources = future.result()
                    all_resources.extend(resources)
                    logger.info(f"Completed scanning {scanner.service_name}")
                except Exception as e:
                    logger.error(f"Failed to scan {scanner.service_name}: {e}")
    
    return all_resources


def display_summary(resources: List[Resource]) -> None:
    """Display a summary of discovered resources using Rich tables."""
    if not resources:
        console.print("[yellow]No resources found.[/yellow]")
        return
    
    # Create summary table
    table = Table(title="AWS Resources Summary", show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Monthly Cost", justify="right", style="yellow")
    
    # Group by service
    by_service = defaultdict(list)
    for resource in resources:
        by_service[resource.service].append(resource)
    
    total_cost = 0
    for service, service_resources in sorted(by_service.items()):
        count = len(service_resources)
        cost = sum(r.estimated_monthly_cost or 0 for r in service_resources)
        total_cost += cost
        table.add_row(service, str(count), f"${cost:,.2f}")
    
    table.add_section()
    table.add_row("TOTAL", str(len(resources)), f"${total_cost:,.2f}", style="bold")
    
    console.print(table)


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Set up configuration
    if args.config:
        os.environ['AWS_SCANNER_CONFIG'] = args.config
    
    config = get_config()
    
    # Override config with command line args
    if args.regions:
        config.only_regions = args.regions
    if args.skip_regions:
        config.skip_regions = args.skip_regions
    if args.services:
        config.only_services = args.services
    if args.skip_services:
        config.skip_services = args.skip_services
    
    # Set up logging
    setup_logging(args.log_level, config.log_format)
    
    console.print("[bold cyan]AWS Resource Scanner[/bold cyan]")
    console.print("=" * 50)
    
    # Check for AWS credentials
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        console.print("[bold red]Error:[/bold red] AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables must be set")
        sys.exit(1)
    
    console.print("[green]✓[/green] Using AWS credentials from environment variables")
    
    try:
        # Get all regions
        console.print("\n[cyan]Fetching AWS regions...[/cyan]")
        regions = get_all_regions()
        console.print(f"[green]✓[/green] Found {len(regions)} regions")
        
        # Initialize scanners
        all_scanners = [
            EC2Scanner(regions),
            S3Scanner(regions),
            RDSScanner(regions),
            LambdaScanner(regions),
            DynamoDBScanner(regions),
            ELBScanner(regions),
            ECSScanner(regions),
            EKSScanner(regions),
            CloudFrontScanner(regions),
            Route53Scanner(regions),
            VPCScanner(regions),
            APIGatewayScanner(regions)
        ]
        
        # Filter scanners based on config
        scanners = all_scanners
        if config.only_services:
            scanners = [s for s in scanners if s.service_name in config.only_services]
        if config.skip_services:
            scanners = [s for s in scanners if s.service_name not in config.skip_services]
        
        console.print(f"\n[cyan]Scanning {len(scanners)} services across {len(regions)} regions...[/cyan]\n")
        
        # Run scanners
        start_time = time.time()
        all_resources = scan_services_concurrently(scanners, not args.no_progress)
        duration = time.time() - start_time
        
        # Display summary
        console.print(f"\n[bold green]Scan completed in {duration:.2f} seconds[/bold green]\n")
        display_summary(all_resources)
        
        # Generate and save report
        if all_resources:
            console.print(f"\n[cyan]Generating {args.format} report...[/cyan]")
            
            if args.format == 'markdown':
                report = generate_markdown_report(all_resources)
            else:
                console.print(f"[yellow]Format '{args.format}' not yet implemented, using markdown[/yellow]")
                report = generate_markdown_report(all_resources)
            
            try:
                with open(args.output, 'w') as f:
                    f.write(report)
                console.print(f"[green]✓[/green] Report saved to: {args.output}")
            except Exception as e:
                console.print(f"[red]Error saving report: {e}[/red]")
                sys.exit(1)
        else:
            console.print("\n[yellow]No resources found to report.[/yellow]")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Scan interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        logger.exception("Unhandled exception in main")
        sys.exit(1)


if __name__ == "__main__":
    main()