"""Unit tests for configuration module."""
import pytest
import os
import json
import tempfile
from unittest.mock import patch

from aws_scanner.config import (
    ScannerConfig,
    get_config,
    get_instance_cost,
    get_ebs_cost,
    get_rds_instance_cost,
    INSTANCE_PRICING,
    EBS_PRICING
)


class TestScannerConfig:
    """Test cases for ScannerConfig class."""
    
    def test_default_initialization(self):
        """Test default configuration values."""
        config = ScannerConfig()
        
        assert config.max_concurrent_regions == 10
        assert config.max_concurrent_services == 5
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.retry_backoff == 2.0
        assert config.requests_per_second == 10.0
        assert config.skip_regions == []
        assert config.skip_services == []
        assert config.only_regions == []
        assert config.only_services == []
        assert config.report_format == 'markdown'
        assert config.report_path == 'aws-resources-report.md'
        assert config.log_level == 'INFO'
        assert config.log_format == 'text'
    
    def test_custom_initialization(self):
        """Test custom configuration values."""
        config = ScannerConfig(
            max_concurrent_regions=5,
            skip_regions=['us-west-2', 'eu-west-1'],
            log_level='DEBUG'
        )
        
        assert config.max_concurrent_regions == 5
        assert config.skip_regions == ['us-west-2', 'eu-west-1']
        assert config.log_level == 'DEBUG'
    
    def test_from_file_success(self):
        """Test loading configuration from file."""
        config_data = {
            'max_concurrent_regions': 3,
            'skip_regions': ['us-west-2'],
            'log_level': 'WARNING'
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config = ScannerConfig.from_file(temp_path)
            
            assert config.max_concurrent_regions == 3
            assert config.skip_regions == ['us-west-2']
            assert config.log_level == 'WARNING'
        finally:
            os.unlink(temp_path)
    
    def test_from_file_not_found(self):
        """Test loading configuration from non-existent file."""
        config = ScannerConfig.from_file('/non/existent/path.json')
        
        # Should return default config
        assert config.max_concurrent_regions == 10
        assert config.log_level == 'INFO'
    
    def test_from_file_invalid_json(self):
        """Test loading configuration from invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('invalid json content')
            temp_path = f.name
        
        try:
            config = ScannerConfig.from_file(temp_path)
            
            # Should return default config
            assert config.max_concurrent_regions == 10
        finally:
            os.unlink(temp_path)
    
    def test_from_env(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            'AWS_SCANNER_MAX_CONCURRENT_REGIONS': '4',
            'AWS_SCANNER_SKIP_REGIONS': 'us-west-2,eu-west-1',
            'AWS_SCANNER_LOG_LEVEL': 'ERROR'
        }
        
        with patch.dict(os.environ, env_vars):
            config = ScannerConfig.from_env()
            
            assert config.max_concurrent_regions == 4
            assert config.skip_regions == ['us-west-2', 'eu-west-1']
            assert config.log_level == 'ERROR'
    
    def test_post_init_none_lists(self):
        """Test that None lists are converted to empty lists."""
        config = ScannerConfig(
            skip_regions=None,
            skip_services=None,
            only_regions=None,
            only_services=None
        )
        
        assert config.skip_regions == []
        assert config.skip_services == []
        assert config.only_regions == []
        assert config.only_services == []


class TestGetConfig:
    """Test cases for get_config function."""
    
    def test_get_config_singleton(self, reset_config):
        """Test that get_config returns singleton."""
        config1 = get_config()
        config2 = get_config()
        
        assert config1 is config2
    
    def test_get_config_from_file(self, reset_config):
        """Test get_config loads from file when available."""
        config_data = {'max_concurrent_regions': 2}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            with patch.dict(os.environ, {'AWS_SCANNER_CONFIG': temp_path}):
                config = get_config()
                assert config.max_concurrent_regions == 2
        finally:
            os.unlink(temp_path)
    
    def test_get_config_from_env(self, reset_config):
        """Test get_config loads from environment when no file."""
        with patch.dict(os.environ, {'AWS_SCANNER_LOG_LEVEL': 'DEBUG'}):
            config = get_config()
            assert config.log_level == 'DEBUG'


class TestPricingFunctions:
    """Test cases for pricing functions."""
    
    def test_get_instance_cost_running(self):
        """Test instance cost for running instance."""
        cost = get_instance_cost('t3.micro', 'running')
        assert cost == 7.50
        
        cost = get_instance_cost('m5.large', 'running')
        assert cost == 70.00
    
    def test_get_instance_cost_stopped(self):
        """Test instance cost for stopped instance."""
        cost = get_instance_cost('t3.micro', 'stopped')
        assert cost == 0.0
        
        cost = get_instance_cost('m5.large', 'terminated')
        assert cost == 0.0
    
    def test_get_instance_cost_unknown_type(self):
        """Test instance cost for unknown instance type."""
        cost = get_instance_cost('unknown.xlarge', 'running')
        assert cost == 50.0  # Default cost
    
    def test_get_ebs_cost(self):
        """Test EBS volume cost calculation."""
        cost = get_ebs_cost('gp3', 100)
        assert cost == 8.0  # 100 GB * $0.08
        
        cost = get_ebs_cost('gp2', 50)
        assert cost == 5.0  # 50 GB * $0.10
        
        cost = get_ebs_cost('io1', 200)
        assert cost == 25.0  # 200 GB * $0.125
    
    def test_get_ebs_cost_unknown_type(self):
        """Test EBS cost for unknown volume type."""
        cost = get_ebs_cost('unknown', 100)
        assert cost == 10.0  # Default to gp2 pricing
    
    def test_get_rds_instance_cost(self):
        """Test RDS instance cost."""
        cost = get_rds_instance_cost('db.t3.micro')
        assert cost == 13.00
        
        cost = get_rds_instance_cost('db.m5.large')
        assert cost == 125.00
    
    def test_get_rds_instance_cost_unknown(self):
        """Test RDS cost for unknown instance class."""
        cost = get_rds_instance_cost('db.unknown.large')
        assert cost == 100.0  # Default cost
    
    def test_pricing_constants(self):
        """Test that pricing constants are properly defined."""
        assert 't2.micro' in INSTANCE_PRICING
        assert 't3.micro' in INSTANCE_PRICING
        assert 'm5.large' in INSTANCE_PRICING
        
        assert 'gp2' in EBS_PRICING
        assert 'gp3' in EBS_PRICING
        assert 'io1' in EBS_PRICING