"""Base scanner class for AWS services."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import time
import logging

from ..types import Resource
from ..config import get_config
from ..utils import handle_aws_error, RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of scanning a single region."""
    region: str
    resources: List[Resource]
    error: Optional[Exception] = None
    duration: float = 0.0


class BaseScanner(ABC):
    """Base class for AWS service scanners."""
    
    def __init__(self, regions: List[str]):
        """
        Initialize scanner.
        
        Args:
            regions: List of AWS regions to scan
        """
        self.regions = regions
        self.config = get_config()
        self.rate_limiter = RateLimiter(self.config.requests_per_second)
        
    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the name of the AWS service being scanned."""
        pass
    
    @abstractmethod
    def scan_single_region(self, region: str) -> List[Resource]:
        """
        Scan resources in a single region.
        
        Args:
            region: AWS region to scan
            
        Returns:
            List of resources found in the region
            
        Raises:
            Various AWS exceptions
        """
        pass
    
    def scan_all_regions(self) -> List[Resource]:
        """
        Scan all regions concurrently.
        
        Returns:
            List of all resources found across all regions
        """
        all_resources: List[Resource] = []
        
        # Filter regions based on config
        regions_to_scan = self._filter_regions(self.regions)
        
        if not regions_to_scan:
            logger.info(f"No regions to scan for {self.service_name}")
            return all_resources
            
        logger.info(f"Scanning {self.service_name} across {len(regions_to_scan)} regions")
        
        # Scan regions concurrently
        with ThreadPoolExecutor(max_workers=self.config.max_concurrent_regions) as executor:
            # Submit all scan tasks
            future_to_region = {
                executor.submit(self._scan_region_with_error_handling, region): region
                for region in regions_to_scan
            }
            
            # Process completed scans
            for future in as_completed(future_to_region):
                region = future_to_region[future]
                result = future.result()
                
                if result.error:
                    logger.error(
                        f"Failed to scan {self.service_name} in {region}: {result.error}",
                        extra={'region': region, 'service': self.service_name}
                    )
                else:
                    if result.resources:
                        logger.info(
                            f"Found {len(result.resources)} {self.service_name} resources in {region}",
                            extra={
                                'region': region,
                                'service': self.service_name,
                                'resource_count': len(result.resources),
                                'duration': result.duration
                            }
                        )
                        all_resources.extend(result.resources)
                    else:
                        logger.debug(f"No {self.service_name} resources found in {region}")
        
        logger.info(
            f"Completed scanning {self.service_name}: found {len(all_resources)} total resources",
            extra={'service': self.service_name, 'total_resources': len(all_resources)}
        )
        
        return all_resources
    
    def _scan_region_with_error_handling(self, region: str) -> ScanResult:
        """
        Scan a region with proper error handling.
        
        Args:
            region: AWS region to scan
            
        Returns:
            ScanResult object
        """
        start_time = time.time()
        
        try:
            # Apply rate limiting
            self.rate_limiter.acquire()
            
            # Scan the region
            resources = self.scan_single_region(region)
            
            return ScanResult(
                region=region,
                resources=resources,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            return ScanResult(
                region=region,
                resources=[],
                error=e,
                duration=time.time() - start_time
            )
    
    def _filter_regions(self, regions: List[str]) -> List[str]:
        """
        Filter regions based on configuration.
        
        Args:
            regions: List of all regions
            
        Returns:
            Filtered list of regions to scan
        """
        filtered = regions.copy()
        
        # Apply skip_regions filter
        if self.config.skip_regions:
            filtered = [r for r in filtered if r not in self.config.skip_regions]
            
        # Apply only_regions filter
        if self.config.only_regions:
            filtered = [r for r in filtered if r in self.config.only_regions]
            
        return filtered
    
    def handle_error(self, error: Exception, context: str) -> None:
        """
        Handle errors during scanning.
        
        Args:
            error: The exception that occurred
            context: Context string for logging
        """
        try:
            handle_aws_error(error, context)
        except Exception:
            # Error is already logged in handle_aws_error
            pass