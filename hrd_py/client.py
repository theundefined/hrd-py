from typing import List, Optional, Dict, Any
from datetime import datetime
from .api import HRDApi
from .models import Balance, Domain, DomainDetails, HistoryEntry, Owner
from .exceptions import HRDError


class HRDClient:
    def __init__(self, api_login: str, api_pass: str, api_hash: str, **kwargs):
        self.api = HRDApi(api_login, api_pass, api_hash, **kwargs)

    def login(self) -> str:
        return self.api.login()

    def get_balance(self) -> Balance:
        data = self.api.partner_get_balance()
        return Balance(balance=data["balance"], restricted_balance=data["restricted_balance"])

    def list_domains(self) -> List[Domain]:
        domain_names = []
        last_name = None
        while True:
            batch = self.api.domain_list(last_name=last_name)
            if not batch:
                break
            domain_names.extend(batch)
            last_name = batch[-1]
            # HRD API doesn't seem to have a defined limit per page in PHP code,
            # but usually it's limited. If we get the same last_name, we break to avoid infinite loop.
            if len(batch) < 2:  # Very simple check for small batch
                break

        domains = []
        for name in domain_names:
            try:
                info = self.api.domain_info(name)
                domains.append(self._parse_domain_info(name, info))
            except HRDError:
                # If info fails for one domain, we might still want to continue
                domains.append(Domain(name=name, status="unknown"))

        return domains

    def _parse_domain_info(self, name: str, info: Dict[str, Any]) -> Domain:
        expiry_date = None
        if info.get("exDate"):
            expiry_date = self._parse_date(info["exDate"])

        create_date = None
        if info.get("crDate"):
            create_date = self._parse_date(info["crDate"])

        owner_id = int(info["user"]) if info.get("user") else None

        return Domain(
            name=name,
            status=info.get("status", "unknown"),
            expiry_date=expiry_date,
            create_date=create_date,
            owner_id=owner_id,
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def renew_domain(self, domain_name: str, period: int = 1) -> int:
        info = self.api.domain_info(domain_name)
        if not info.get("exDate"):
            raise HRDError(f"Cannot renew domain {domain_name}: expiry date unknown")

        expiry_date = self._parse_date(info["exDate"])
        if not expiry_date:
            raise HRDError(f"Cannot renew domain {domain_name}: unparseable expiry date '{info['exDate']}'")

        # API requires currentExpirationDate as a plain YYYY-MM-DD date (no time component)
        return self.api.domain_renew(domain_name, expiry_date.strftime("%Y-%m-%d"), period)

    def get_history(self, limit: int = 20) -> List[HistoryEntry]:
        action_ids: List[int] = []
        last_id = None
        while True:
            batch = self.api.action_list(last_id=last_id)
            if not batch:
                break
            action_ids.extend(batch)
            last_id = batch[-1]
            if len(batch) < 2:  # Very simple check for small batch
                break

        # Actions are listed oldest-first; only fetch details for the most recent `limit`
        # entries, since action_info is one request per id.
        recent_ids = action_ids[-limit:] if limit else action_ids
        recent_ids.reverse()

        entries = []
        for action_id in recent_ids:
            try:
                info = self.api.action_info(action_id)
                entries.append(self._parse_history_entry(action_id, info))
            except HRDError:
                continue

        return entries

    def _parse_history_entry(self, action_id: int, info: Dict[str, Any]) -> HistoryEntry:
        date = None
        if info.get("added"):
            date = self._parse_date(info["added"])

        amount = None
        if info.get("amount"):
            amount = float(info["amount"])

        return HistoryEntry(
            id=action_id,
            type=info.get("type", "unknown"),
            object=info.get("object", "unknown"),
            object_name=info.get("objectName"),
            status=info.get("status", "unknown"),
            amount=amount,
            date=date,
        )

    def get_domain_details(self, domain_name: str) -> DomainDetails:
        info = self.api.domain_info(domain_name)

        owner_id = int(info["user"]) if info.get("user") else None
        owner = None
        if owner_id is not None:
            try:
                owner = self.get_owner(owner_id)
            except HRDError:
                owner = None

        return DomainDetails(
            name=domain_name,
            status=info.get("status", "unknown"),
            create_date=self._parse_date(info["crDate"]) if info.get("crDate") else None,
            expiry_date=self._parse_date(info["exDate"]) if info.get("exDate") else None,
            privacy=info.get("privacy") == "true",
            privacy_protection_date=self._parse_date(info["ppDate"]) if info.get("ppDate") else None,
            nameservers=info.get("ns", []),
            hosts=info.get("host", []),
            dnssec_records=info.get("dnssec", []),
            action_ids=info.get("actions", []),
            owner_id=owner_id,
            owner=owner,
        )

    def get_owner(self, owner_id: int) -> Owner:
        data = self.api.user_info(owner_id)
        return self._parse_owner(data, owner_id)

    def _parse_owner(self, data: Dict[str, Any], owner_id: Optional[int] = None) -> Owner:
        return Owner(
            name=data.get("name", "unknown"),
            id=owner_id,
            type=data.get("type"),
            email=data.get("email"),
            street=data.get("street"),
            city=data.get("city"),
            postcode=data.get("postcode"),
            country=data.get("country"),
            id_number=data.get("idNumber"),
            landline_phone=data.get("landlinePhone"),
            mobile_phone=data.get("mobilePhone"),
        )

    def update_nameservers(self, domain_name: str, nameservers: List[str]) -> Optional[int]:
        return self.api.domain_update(domain_name, nameservers)

    def list_hosts(self) -> List[str]:
        names: List[str] = []
        last_name = None
        while True:
            batch = self.api.domain_host_list(last_name=last_name)
            if not batch:
                break
            names.extend(batch)
            last_name = batch[-1]
            if len(batch) < 2:
                break
        return names

    def get_host(self, name: str) -> Dict[str, Any]:
        return self.api.domain_host_info(name)

    def create_host(
        self, name: str, ipv4: Optional[List[str]] = None, ipv6: Optional[List[str]] = None
    ) -> Optional[int]:
        return self.api.domain_host_create(name, ipv4, ipv6)

    def update_host(
        self, name: str, ipv4: Optional[List[str]] = None, ipv6: Optional[List[str]] = None
    ) -> Optional[int]:
        return self.api.domain_host_update(name, ipv4, ipv6)

    def delete_host(self, name: str) -> Optional[int]:
        return self.api.domain_host_delete(name)

    def get_next_notification(self) -> Optional[Dict[str, Any]]:
        return self.api.poll_get()

    def ack_notification(self, notification_id: int) -> None:
        self.api.poll_ack(notification_id)

    def list_owner_ids(self) -> List[int]:
        ids: List[int] = []
        last_id = None
        while True:
            batch = self.api.user_list(last_id=last_id)
            if not batch:
                break
            ids.extend(batch)
            last_id = batch[-1]
            if len(batch) < 2:
                break
        return ids

    def renew_all_expiring(self, days: int = 30) -> Dict[str, int]:
        domains = self.list_domains()
        results = {}
        for domain in domains:
            if domain.is_expiring_soon(days):
                try:
                    action_id = self.renew_domain(domain.name)
                    results[domain.name] = action_id
                except HRDError:
                    results[domain.name] = -1  # or error message
        return results
