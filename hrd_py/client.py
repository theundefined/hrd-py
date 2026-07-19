from typing import List, Optional, Dict, Any
from datetime import datetime
from .api import HRDApi
from .models import Balance, Domain
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

        return Domain(name=name, status=info.get("status", "unknown"), expiry_date=expiry_date, create_date=create_date)

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
