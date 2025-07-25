from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List


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
class ScanResult:
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