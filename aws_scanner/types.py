from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, TypedDict, Protocol, runtime_checkable


@dataclass
class Resource:
    id: str
    type: str
    service: str
    region: str
    name: Optional[str] = None
    created_at: Optional[datetime] = None
    state: Optional[str] = None
    estimated_monthly_cost: Optional[float] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegionScanResult:
    """Result of scanning a single region."""
    region: str
    resources: List[Resource]
    error: Optional[Exception] = None
    duration: float = 0.0


@dataclass
class ScanResult:
    """Result of scanning a service across all regions."""
    service: str
    resources: List[Resource]
    errors: List[str]
    scan_duration: float


@dataclass
class ServiceSummary:
    service: str
    total_resources: int
    total_estimated_monthly_cost: Optional[float] = None
    resources_by_region: Dict[str, int] = field(default_factory=dict)


# TypedDict definitions for additional_info fields
class EC2InstanceInfo(TypedDict, total=False):
    """Type definition for EC2 instance additional info."""
    instanceType: str
    publicIp: Optional[str]
    privateIp: Optional[str]
    vpcId: Optional[str]
    subnetId: Optional[str]
    availabilityZone: Optional[str]
    platform: Optional[str]
    architecture: Optional[str]


class EBSVolumeInfo(TypedDict, total=False):
    """Type definition for EBS volume additional info."""
    volumeType: str
    size: int
    iops: Optional[int]
    throughput: Optional[int]
    encrypted: bool
    availabilityZone: str
    attachments: int


class S3BucketInfo(TypedDict, total=False):
    """Type definition for S3 bucket additional info."""
    objectCount: int
    totalSize: float
    storageClass: str
    versioning: bool
    encryption: bool
    publicAccess: bool
    lifecycleRules: int


class RDSInstanceInfo(TypedDict, total=False):
    """Type definition for RDS instance additional info."""
    engine: str
    engineVersion: str
    instanceClass: str
    allocatedStorage: int
    storageType: str
    multiAZ: bool
    publiclyAccessible: bool
    backupRetentionPeriod: int


class LambdaFunctionInfo(TypedDict, total=False):
    """Type definition for Lambda function additional info."""
    runtime: str
    memorySize: int
    timeout: int
    handler: str
    codeSize: int
    lastModified: str
    architectures: list[str]


class DynamoDBTableInfo(TypedDict, total=False):
    """Type definition for DynamoDB table additional info."""
    billingMode: str
    itemCount: int
    sizeBytes: int
    readCapacityUnits: Optional[int]
    writeCapacityUnits: Optional[int]
    globalSecondaryIndexes: int
    localSecondaryIndexes: int


# Protocol definitions for boto3 objects
@runtime_checkable
class BotoClient(Protocol):
    """Protocol for boto3 client objects."""
    
    def get_paginator(self, operation_name: str) -> Any:
        """Get a paginator for the specified operation."""
        ...
    
    def describe_regions(self, **kwargs: Any) -> Dict[str, Any]:
        """Describe AWS regions."""
        ...


@runtime_checkable
class Paginator(Protocol):
    """Protocol for boto3 paginator objects."""
    
    def paginate(self, **kwargs: Any) -> Any:
        """Paginate through results."""
        ...


# AWS API Response types
class AWSResponse(TypedDict):
    """Base AWS API response."""
    ResponseMetadata: Dict[str, Any]


class DescribeInstancesResponse(AWSResponse, total=False):
    """Response from EC2 describe_instances."""
    Reservations: list[Dict[str, Any]]
    NextToken: Optional[str]


class ListBucketsResponse(AWSResponse):
    """Response from S3 list_buckets."""
    Buckets: list[Dict[str, Any]]
    Owner: Dict[str, str]