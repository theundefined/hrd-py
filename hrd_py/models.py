from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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
