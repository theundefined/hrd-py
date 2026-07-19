from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Balance:
    balance: float
    restricted_balance: float


@dataclass
class Domain:
    name: str
    status: str
    expiry_date: Optional[datetime] = None
    create_date: Optional[datetime] = None

    def is_expiring_soon(self, days: int = 30) -> bool:
        if not self.expiry_date:
            return False
        delta = self.expiry_date - datetime.now()
        return delta.days <= days


@dataclass
class HistoryEntry:
    id: int
    type: str
    object: str
    status: str
    object_name: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[datetime] = None


@dataclass
class Owner:
    name: str
    type: Optional[str] = None
    email: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = None
    id_number: Optional[str] = None
    landline_phone: Optional[str] = None
    mobile_phone: Optional[str] = None


@dataclass
class DomainDetails:
    name: str
    status: str
    create_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    privacy: bool = False
    privacy_protection_date: Optional[datetime] = None
    nameservers: List[str] = field(default_factory=list)
    hosts: List[Dict[str, Any]] = field(default_factory=list)
    dnssec_records: List[Dict[str, Any]] = field(default_factory=list)
    action_ids: List[int] = field(default_factory=list)
    owner: Optional[Owner] = None
