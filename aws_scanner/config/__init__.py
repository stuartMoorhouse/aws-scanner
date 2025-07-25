"""Configuration module for AWS Scanner."""
from .pricing import (
    INSTANCE_PRICING, 
    get_instance_cost, 
    get_ebs_cost,
    ELASTIC_IP_PRICING,
    NAT_GATEWAY_PRICING,
    SNAPSHOT_PRICING,
    EBS_PRICING,
    RDS_INSTANCE_PRICING,
    get_rds_instance_cost
)
from .settings import ScannerConfig, get_config

__all__ = [
    'INSTANCE_PRICING', 
    'get_instance_cost', 
    'get_ebs_cost',
    'ELASTIC_IP_PRICING',
    'NAT_GATEWAY_PRICING',
    'SNAPSHOT_PRICING',
    'EBS_PRICING',
    'RDS_INSTANCE_PRICING',
    'get_rds_instance_cost',
    'ScannerConfig', 
    'get_config'
]