"""AWS Pricing configuration and utilities."""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# EC2 Instance pricing (rough estimates per month in USD)
INSTANCE_PRICING: Dict[str, float] = {
    # T2 instances
    't2.nano': 4.25,
    't2.micro': 8.50,
    't2.small': 17.00,
    't2.medium': 34.00,
    't2.large': 68.00,
    't2.xlarge': 136.00,
    't2.2xlarge': 272.00,
    
    # T3 instances
    't3.nano': 3.80,
    't3.micro': 7.50,
    't3.small': 15.00,
    't3.medium': 30.00,
    't3.large': 60.00,
    't3.xlarge': 120.00,
    't3.2xlarge': 240.00,
    
    # M5 instances
    'm5.large': 70.00,
    'm5.xlarge': 140.00,
    'm5.2xlarge': 280.00,
    'm5.4xlarge': 560.00,
    'm5.8xlarge': 1120.00,
    
    # C5 instances
    'c5.large': 62.00,
    'c5.xlarge': 124.00,
    'c5.2xlarge': 248.00,
    'c5.4xlarge': 496.00,
    
    # R5 instances
    'r5.large': 92.00,
    'r5.xlarge': 184.00,
    'r5.2xlarge': 368.00,
    'r5.4xlarge': 736.00,
}

# EBS Volume pricing per GB per month
EBS_PRICING = {
    'gp3': 0.08,
    'gp2': 0.10,
    'io1': 0.125,
    'io2': 0.125,
    'st1': 0.045,
    'sc1': 0.025,
    'standard': 0.05,
}

# Snapshot pricing per GB per month
SNAPSHOT_PRICING = 0.05

# Elastic IP pricing per month (when not attached)
ELASTIC_IP_PRICING = 3.60

# NAT Gateway pricing
NAT_GATEWAY_PRICING = {
    'hourly': 0.045,
    'monthly': 45.00,  # Rough estimate
    'per_gb': 0.045,
}

# RDS Instance pricing (rough estimates)
RDS_INSTANCE_PRICING = {
    'db.t3.micro': 13.00,
    'db.t3.small': 26.00,
    'db.t3.medium': 52.00,
    'db.t3.large': 104.00,
    'db.m5.large': 125.00,
    'db.m5.xlarge': 250.00,
    'db.m5.2xlarge': 500.00,
    'db.r5.large': 180.00,
    'db.r5.xlarge': 360.00,
}


def get_instance_cost(instance_type: str, state: str = 'running') -> float:
    """
    Get estimated monthly cost for an EC2 instance.
    
    Args:
        instance_type: The EC2 instance type (e.g., 't2.micro')
        state: The instance state (only 'running' instances incur costs)
        
    Returns:
        Estimated monthly cost in USD
    """
    if state != 'running':
        return 0.0
        
    cost = INSTANCE_PRICING.get(instance_type, 50.0)  # Default to $50 if unknown
    
    if instance_type not in INSTANCE_PRICING:
        logger.warning(f"Unknown instance type: {instance_type}, using default cost estimate")
        
    return cost


def get_ebs_cost(volume_type: str, size_gb: int) -> float:
    """
    Get estimated monthly cost for an EBS volume.
    
    Args:
        volume_type: The EBS volume type (e.g., 'gp3')
        size_gb: Size of the volume in GB
        
    Returns:
        Estimated monthly cost in USD
    """
    price_per_gb = EBS_PRICING.get(volume_type, 0.10)  # Default to gp2 pricing
    return price_per_gb * size_gb


def get_rds_instance_cost(instance_class: str, engine: Optional[str] = None) -> float:
    """
    Get estimated monthly cost for an RDS instance.
    
    Args:
        instance_class: The RDS instance class (e.g., 'db.t3.micro')
        engine: Database engine (for future pricing refinements)
        
    Returns:
        Estimated monthly cost in USD
    """
    return RDS_INSTANCE_PRICING.get(instance_class, 100.0)  # Default to $100