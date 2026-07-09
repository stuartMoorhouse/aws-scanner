#!/usr/bin/env python3
"""AWS Resource Scanner - Main entry point."""
import os
import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Iterator
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
from aws_scanner.session import (
    build_session,
    describe_identity,
    list_profiles,
    prompt_for_profile,
)
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
    APIGatewayScanner,
    KMSScanner,
    SecretsManagerScanner,
    GuardDutyScanner,
    CloudTrailScanner,
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
    parser.add_argument(
        '--streaming',
        action='store_true',
        help='Use memory-efficient streaming mode (recommended for large AWS accounts)'
    )
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument(
        '--profile',
        help='AWS profile to use (from ~/.aws/config). '
             'If omitted, you will be prompted to pick one interactively.'
    )

    # One shortcut flag per discovered profile, e.g. --personal, --company.
    existing_dests = {action.dest for action in parser._actions}
    for name in list_profiles():
        flag = f'--{name}'
        dest = f'profile_shortcut_{name}'
        if name in existing_dests or dest in existing_dests:
            continue
        profile_group.add_argument(
            flag,
            dest=dest,
            action='store_const',
            const=name,
            help=f"Shortcut for --profile {name}"
        )

    parser.add_argument(
        '--list-profiles',
        action='store_true',
        help='List available AWS profiles and exit.'
    )

    args = parser.parse_args()

    # Collapse any --<profile> shortcut into args.profile
    if not args.profile:
        for key, value in vars(args).items():
            if key.startswith('profile_shortcut_') and value:
                args.profile = value
                break

    return args


@retry_with_backoff()
def get_all_regions(session: boto3.Session) -> List[str]:
    """
    Get all available AWS regions using the given session.

    Args:
        session: boto3 Session (carries profile/creds)

    Returns:
        List of region names

    Raises:
        Exception: If unable to fetch regions
    """
    try:
        client = session.client('ec2', region_name='us-east-1')
        response = client.describe_regions()
        return sorted([region['RegionName'] for region in response['Regions']])
    except Exception as e:
        logger.error(f"Error fetching regions: {e}")
        raise


def generate_markdown_report_streaming(resources: Iterator[Resource], output_file: str) -> None:
    """
    Generate a comprehensive markdown report of all resources using streaming.
    Memory-efficient version that writes incrementally.
    
    Args:
        resources: Iterator of discovered resources
        output_file: Path to output file
    """
    timestamp = datetime.now().isoformat()
    
    # Temporary storage for summary data
    service_data = defaultdict(lambda: {'count': 0, 'cost': 0.0, 'resources': []})
    total_count = 0
    total_cost = 0.0
    
    # First pass: collect resources and build summary
    all_resources = []
    for resource in resources:
        all_resources.append(resource)
        total_count += 1
        cost = resource.estimated_monthly_cost or 0
        total_cost += cost
        service_data[resource.service]['count'] += 1
        service_data[resource.service]['cost'] += cost
        service_data[resource.service]['resources'].append(resource)
    
    # Now write the report
    with open(output_file, 'w') as f:
        # Header
        f.write("# AWS Resources Report\n\n")
        f.write(f"**Generated:** {timestamp}\n")
        f.write(f"**Total Resources Found:** {total_count}\n")
        f.write(f"**Total Estimated Monthly Cost:** ${total_cost:,.2f}\n\n")
        
        if total_count == 0:
            f.write("No resources found.\n")
            return
        
        # Table of contents
        f.write("## Table of Contents\n\n")
        for service in sorted(service_data.keys()):
            anchor = service.lower().replace(' ', '-')
            f.write(f"- [{service}](#{anchor})\n")
        f.write("\n")
        
        # Summary by service
        f.write("## Summary by Service\n\n")
        f.write("| Service | Resource Count | Estimated Monthly Cost |\n")
        f.write("|---------|----------------|----------------------|\n")
        
        for service in sorted(service_data.keys()):
            data = service_data[service]
            f.write(f"| {service} | {data['count']} | ${data['cost']:,.2f} |\n")
        
        f.write("\n")
        
        # Detailed resources by service
        for service in sorted(service_data.keys()):
            f.write(f"## {service}\n\n")
            
            # Group by region
            by_region = defaultdict(list)
            for resource in service_data[service]['resources']:
                by_region[resource.region].append(resource)
            
            for region in sorted(by_region.keys()):
                f.write(f"### {region}\n\n")
                
                # Generic table for all services
                f.write("| Type | Name/ID | State | Monthly Cost | Details |\n")
                f.write("|------|---------|-------|--------------|----------|\n")
                
                for resource in by_region[region]:
                    # Extract key details
                    details = []
                    if resource.additional_info:
                        for k, v in resource.additional_info.items():
                            if v and not isinstance(v, (dict, list)) and k != 'tags':
                                details.append(f"{k}: {v}")
                                if len(details) >= 3:
                                    break
                    
                    f.write(
                        f"| {resource.type} "
                        f"| {resource.name or resource.id} "
                        f"| {resource.state or 'active'} "
                        f"| ${(resource.estimated_monthly_cost or 0):,.2f} "
                        f"| {', '.join(details) or '-'} |\n"
                    )
                
                f.write("\n")


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


def scan_services_streaming(
    scanners: List[BaseScanner], 
    show_progress: bool = True
) -> Iterator[Resource]:
    """
    Scan all services concurrently, yielding resources as they're found.
    Memory-efficient version that doesn't load all resources at once.
    
    Args:
        scanners: List of scanner instances
        show_progress: Whether to show progress bars
        
    Yields:
        Resources as they are discovered
    """
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
            overall_task = progress.add_task(
                "[cyan]Scanning AWS services...", 
                total=len(scanners)
            )
            
            with ThreadPoolExecutor(max_workers=config.max_concurrent_services) as executor:
                future_to_scanner = {
                    executor.submit(scanner.scan_all_regions): scanner
                    for scanner in scanners
                }
                
                for future in as_completed(future_to_scanner):
                    scanner = future_to_scanner[future]
                    try:
                        resources = future.result()
                        for resource in resources:
                            yield resource
                        progress.update(overall_task, advance=1)
                    except Exception as e:
                        logger.error(f"Failed to scan {scanner.service_name}: {e}")
                        progress.update(overall_task, advance=1)
    else:
        with ThreadPoolExecutor(max_workers=config.max_concurrent_services) as executor:
            future_to_scanner = {
                executor.submit(scanner.scan_all_regions): scanner
                for scanner in scanners
            }
            
            for future in as_completed(future_to_scanner):
                scanner = future_to_scanner[future]
                try:
                    resources = future.result()
                    for resource in resources:
                        yield resource
                    logger.info(f"Completed scanning {scanner.service_name}")
                except Exception as e:
                    logger.error(f"Failed to scan {scanner.service_name}: {e}")


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
    # Use the streaming version and collect all resources
    return list(scan_services_streaming(scanners, show_progress))




def display_summary(resources: List[Resource]) -> None:
    """Display a summary of discovered resources using Rich tables."""
    if not resources:
        console.print("[yellow]No resources found.[/yellow]")
        return

    # Create summary table
    table = Table(title="AWS Resources Summary", show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Region", style="blue", no_wrap=True)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Monthly Cost", justify="right", style="yellow")

    # Group by service, type, and region
    by_service_type_region = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for resource in resources:
        by_service_type_region[resource.service][resource.type][resource.region].append(resource)

    total_cost = 0
    for service in sorted(by_service_type_region.keys()):
        types = by_service_type_region[service]
        for resource_type in sorted(types.keys()):
            regions = types[resource_type]
            for region in sorted(regions.keys()):
                region_resources = regions[region]
                count = len(region_resources)
                cost = sum(r.estimated_monthly_cost or 0 for r in region_resources)
                total_cost += cost
                table.add_row(service, resource_type, region, str(count), f"${cost:,.2f}")

    table.add_section()
    table.add_row("TOTAL", "", "", str(len(resources)), f"${total_cost:,.2f}", style="bold")

    console.print(table)


def main():
    """Main entry point."""
    args = parse_arguments()

    # --list-profiles short-circuit
    if args.list_profiles:
        profiles = list_profiles()
        if not profiles:
            console.print("[yellow]No AWS profiles configured.[/yellow]")
            sys.exit(0)
        console.print("[bold cyan]Available AWS profiles:[/bold cyan]")
        for name in profiles:
            console.print(f"  - {name}")
        sys.exit(0)

    # Resolve which AWS profile to use
    profile = args.profile
    if not profile:
        profile = prompt_for_profile()

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

    # Build session and confirm identity
    session = build_session(profile)
    identity = describe_identity(session)
    console.print(
        f"[green]✓[/green] Using profile [bold]{profile}[/bold] — "
        f"account [bold]{identity['Account']}[/bold] "
        f"as [bold]{identity['Arn']}[/bold]"
    )

    try:
        # Get all regions
        console.print("\n[cyan]Fetching AWS regions...[/cyan]")
        regions = get_all_regions(session)
        console.print(f"[green]✓[/green] Found {len(regions)} regions")

        # Initialize scanners
        all_scanners = [
            EC2Scanner(regions, session),
            S3Scanner(regions, session),
            RDSScanner(regions, session),
            LambdaScanner(regions, session),
            DynamoDBScanner(regions, session),
            ELBScanner(regions, session),
            ECSScanner(regions, session),
            EKSScanner(regions, session),
            CloudFrontScanner(regions, session),
            Route53Scanner(regions, session),
            VPCScanner(regions, session),
            APIGatewayScanner(regions, session),
            KMSScanner(regions, session),
            SecretsManagerScanner(regions, session),
            GuardDutyScanner(regions, session),
            CloudTrailScanner(regions, session),
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
        
        if args.streaming:
            # Use memory-efficient streaming mode
            console.print("[cyan]Using memory-efficient streaming mode...[/cyan]\n")
            
            # Stream resources directly to file
            resources_iter = scan_services_streaming(scanners, not args.no_progress)
            
            # Generate report using streaming
            console.print(f"\n[cyan]Generating streaming {args.format} report...[/cyan]")
            if args.format != 'markdown':
                console.print(f"[yellow]Format '{args.format}' not yet implemented, using markdown[/yellow]")
            
            try:
                generate_markdown_report_streaming(resources_iter, args.output)
                duration = time.time() - start_time
                console.print(f"\n[bold green]Scan completed in {duration:.2f} seconds[/bold green]")
                console.print(f"[green]✓[/green] Report saved to: {args.output}")
            except Exception as e:
                console.print(f"[red]Error saving report: {e}[/red]")
                sys.exit(1)
        else:
            # Traditional mode - load all resources into memory
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