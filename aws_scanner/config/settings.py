"""Scanner configuration settings."""
from dataclasses import dataclass
from typing import Optional, List
import os
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ScannerConfig:
    """Configuration for AWS Scanner."""
    
    # Concurrency settings
    max_concurrent_regions: int = 10
    max_concurrent_services: int = 5
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    
    # Rate limiting
    requests_per_second: float = 10.0
    
    # Scanning settings
    skip_regions: List[str] = None
    skip_services: List[str] = None
    only_regions: List[str] = None
    only_services: List[str] = None
    
    # Output settings
    report_format: str = 'markdown'
    report_path: str = 'aws-resources-report.md'
    
    # Logging
    log_level: str = 'INFO'
    log_format: str = 'text'  # 'text' or 'json'
    
    def __post_init__(self):
        """Initialize empty lists for None values."""
        if self.skip_regions is None:
            self.skip_regions = []
        if self.skip_services is None:
            self.skip_services = []
        if self.only_regions is None:
            self.only_regions = []
        if self.only_services is None:
            self.only_services = []
    
    @classmethod
    def from_file(cls, config_path: str) -> 'ScannerConfig':
        """Load configuration from a JSON file."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            return cls(**config_data)
        except FileNotFoundError:
            logger.info(f"Config file {config_path} not found, using defaults")
            return cls()
        except Exception as e:
            logger.error(f"Error loading config file: {e}, using defaults")
            return cls()
    
    @classmethod
    def from_env(cls) -> 'ScannerConfig':
        """Load configuration from environment variables."""
        config = cls()
        
        # Override with environment variables if present
        if os.getenv('AWS_SCANNER_MAX_CONCURRENT_REGIONS'):
            config.max_concurrent_regions = int(os.getenv('AWS_SCANNER_MAX_CONCURRENT_REGIONS'))
        
        if os.getenv('AWS_SCANNER_SKIP_REGIONS'):
            config.skip_regions = os.getenv('AWS_SCANNER_SKIP_REGIONS').split(',')
            
        if os.getenv('AWS_SCANNER_LOG_LEVEL'):
            config.log_level = os.getenv('AWS_SCANNER_LOG_LEVEL')
            
        return config


_config: Optional[ScannerConfig] = None


def get_config() -> ScannerConfig:
    """Get the global scanner configuration."""
    global _config
    if _config is None:
        # Try to load from file first, then override with env vars
        config_path = os.getenv('AWS_SCANNER_CONFIG', 'aws-scanner-config.json')
        if os.path.exists(config_path):
            _config = ScannerConfig.from_file(config_path)
        else:
            _config = ScannerConfig.from_env()
    return _config