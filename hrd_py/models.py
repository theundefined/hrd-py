from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Balance:
    balance: float
    restricted_balance: float


@dataclass
class Domain:
    name: str
    status: str
    expiry_date: datetime | None = None
    create_date: datetime | None = None
    owner_id: int | None = None

    def is_expiring_soon(self, days: int = 30) -> bool:
        if not self.expiry_date:
            return False
        # The HRD.pl API returns naive date strings (no timezone info), and the
        # whole domain model (client.py's _parse_date, cli.py's datetime.min
        # comparisons) is naive throughout, so this must stay naive too to
        # remain comparable with self.expiry_date.
        delta = self.expiry_date - datetime.now()  # noqa: DTZ005
        return delta.days <= days


@dataclass
class HistoryEntry:
    id: int
    type: str
    object: str
    status: str
    object_name: str | None = None
    amount: float | None = None
    date: datetime | None = None


@dataclass
class Owner:
    name: str
    id: int | None = None
    type: str | None = None
    email: str | None = None
    street: str | None = None
    city: str | None = None
    postcode: str | None = None
    country: str | None = None
    id_number: str | None = None
    landline_phone: str | None = None
    mobile_phone: str | None = None


@dataclass
class DomainDetails:
    name: str
    status: str
    create_date: datetime | None = None
    expiry_date: datetime | None = None
    privacy: bool = False
    privacy_protection_date: datetime | None = None
    nameservers: list[str] = field(default_factory=list)
    hosts: list[dict[str, Any]] = field(default_factory=list)
    dnssec_records: list[dict[str, Any]] = field(default_factory=list)
    action_ids: list[int] = field(default_factory=list)
    owner_id: int | None = None
    owner: Owner | None = None
