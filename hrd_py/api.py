import socket
import ssl
import hashlib
import struct
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from .exceptions import HRDCommunicationError, HRDAPIError, HRDAuthError


class HRDApi:
    def __init__(
        self,
        api_login: str,
        api_pass: str,
        api_hash: str,
        host: str = "api.hrd.pl",
        port: int = 9999,
        timeout: int = 10,
        verify_peer: bool = True,
        debug: bool = False,
    ):
        self.api_login = api_login
        self.api_pass = api_pass
        self.api_hash = bytes.fromhex(api_hash)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.verify_peer = verify_peer
        self.debug = debug

        self.token: Optional[str] = None
        self._sock: Optional[socket.socket] = None
        self._ssl_sock: Optional[ssl.SSLSocket] = None

    def _connect(self):
        if self._ssl_sock:
            return

        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            context = ssl.create_default_context()
            if not self.verify_peer:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            self._ssl_sock = context.wrap_socket(self._sock, server_hostname=self.host)
        except Exception as e:
            raise HRDCommunicationError(f"Failed to connect to {self.host}:{self.port}: {e}")

    def _disconnect(self):
        if self._ssl_sock:
            self._ssl_sock.close()
            self._ssl_sock = None
        if self._sock:
            self._sock.close()
            self._sock = None

    def _send(self, xml_data: str):
        self._connect()
        assert self._ssl_sock is not None

        # Calculate hash: SHA512(XML + binary_api_hash)
        # Note: XML must be the exact string, including any whitespace or lack thereof
        payload_bytes = xml_data.encode("utf-8")
        h = hashlib.sha512()
        h.update(payload_bytes)
        h.update(self.api_hash)
        hash_bytes = h.digest()

        full_payload = hash_bytes + payload_bytes
        length_prefix = struct.pack(">I", len(full_payload))

        try:
            self._ssl_sock.sendall(length_prefix + full_payload)
        except Exception as e:
            self._disconnect()
            raise HRDCommunicationError(f"Failed to send data: {e}")

    def _read(self) -> str:
        assert self._ssl_sock is not None
        try:
            length_data = self._ssl_sock.recv(4)
            if len(length_data) < 4:
                raise HRDCommunicationError("Failed to read response length")

            length = struct.unpack(">I", length_data)[0]
            response_data = b""
            while len(response_data) < length:
                chunk = self._ssl_sock.recv(length - len(response_data))
                if not chunk:
                    break
                response_data += chunk

            if len(response_data) != length:
                raise HRDCommunicationError(f"Expected {length} bytes, got {len(response_data)}")

            return response_data.decode("utf-8")
        except Exception as e:
            self._disconnect()
            raise HRDCommunicationError(f"Failed to read response: {e}")

    def _request(self, module: str, method: str = "", params: Optional[Dict[str, Any]] = None) -> ET.Element:
        # Construct XML - mirror PHP DOMDocument behavior
        # PHP: $dom = new \DOMDocument('1.0', 'utf-8');
        # PHP: $api = $dom->createElementNS('http://api.hrd.pl/api/', 'api');

        # We'll use a manual XML string to be safe about formatting, or carefully use ET
        root = ET.Element("api", xmlns="http://api.hrd.pl/api/")

        # NOTE: Token is NOT included in normal requests in PHP library!
        # It's only used in loginByToken method which sends <api><token>...</token></api>

        module_elem = ET.SubElement(root, module)
        if method:
            target_elem = ET.SubElement(module_elem, method)
        else:
            target_elem = module_elem

        if params:
            self._dict_to_xml(target_elem, params)

        return self._execute(root, module, method)

    def _request_custom(self, module: str, method: str, build_fn) -> ET.Element:
        """Like _request, but lets the caller populate the target element directly
        (via ElementTree calls) instead of through the flat-dict _dict_to_xml helper,
        for requests with nested/repeated elements (e.g. nameserver lists)."""
        root = ET.Element("api", xmlns="http://api.hrd.pl/api/")
        module_elem = ET.SubElement(root, module)
        target_elem = ET.SubElement(module_elem, method) if method else module_elem
        build_fn(target_elem)
        return self._execute(root, module, method)

    def _execute(self, root: ET.Element, module: str, method: str) -> ET.Element:
        # PHP's saveXML() usually includes the XML declaration and some whitespace
        # but the schema validation might depend on it.
        # Let's try without declaration first as we did before, but with encoding="utf-8"
        xml_str = ET.tostring(root, encoding="unicode")

        if self.debug:
            print(f">>> REQUEST  {module}/{method}\n{xml_str}\n")

        self._send(xml_str)

        response_xml = self._read()

        if self.debug:
            print(f"<<< RESPONSE {module}/{method}\n{response_xml}\n")

        # The PHP code removes the xmlns before parsing
        response_xml = response_xml.replace('xmlns="http://api.hrd.pl/api/"', "")

        resp_root = ET.fromstring(response_xml)

        # Check for error
        error_msg = resp_root.find("message")
        if error_msg is not None:
            raise HRDAPIError(error_msg.text)

        status = resp_root.find("status")
        if status is not None and status.text == "error":
            raise HRDAPIError("API returned error status")

        return resp_root

    def _dict_to_xml(self, parent, data: Dict[str, Any]):
        for key, value in data.items():
            child = ET.SubElement(parent, key)
            if isinstance(value, dict):
                self._dict_to_xml(child, value)
            elif isinstance(value, list):
                pass
            else:
                child.text = str(value)

    def login(self, login_type: str = "partnerApi"):
        params = {"login": self.api_login, "pass": self.api_pass, "type": login_type}
        resp = self._request("login", "", params)

        token = resp.find("token")
        if token is not None:
            self.token = token.text
            return self.token
        raise HRDAuthError("Login failed, no token received")

    def partner_get_balance(self) -> Dict[str, float]:
        resp = self._request("partner", "getBalance")
        balance_elem = resp.find(".//getBalance")
        if balance_elem is None:
            balance_elem = resp.find(".//partner/getBalance")

        if balance_elem is not None:
            balance_child = balance_elem.find("balance")
            restricted_child = balance_elem.find("restrictedBalance")
            if balance_child is not None and balance_child.text is not None:
                if restricted_child is not None and restricted_child.text is not None:
                    return {
                        "balance": float(balance_child.text),
                        "restricted_balance": float(restricted_child.text),
                    }
        raise HRDAPIError("Could not find balance information in response")

    def domain_list(self, last_name: Optional[str] = None) -> List[str]:
        params = {}
        if last_name:
            params["lastName"] = last_name

        resp = self._request("domain", "list", params)
        names = resp.findall(".//domain/list/name")
        return [n.text for n in names if n.text is not None]

    def domain_info(self, domain_name: str) -> Dict[str, Any]:
        params = {"name": domain_name}
        resp = self._request("domain", "info", params)
        info_elem = resp.find(".//domain/info")

        if info_elem is None:
            raise HRDAPIError(f"Could not find info for domain {domain_name}")

        info: Dict[str, Any] = {"host": [], "dnssec": []}
        for child in info_elem:
            if child.tag == "ns":
                info["ns"] = self._parse_ns_element(child)
            elif child.tag == "host":
                info["host"].append(self._parse_host_element(child))
            elif child.tag == "dnssec":
                info["dnssec"].append({dc.tag: dc.text for dc in child})
            elif child.tag == "actions":
                info["actions"] = [int(i.text) for i in child.findall("id") if i.text is not None]
            else:
                info[child.tag] = child.text
        return info

    def _parse_ns_element(self, ns_elem: ET.Element) -> List[str]:
        # <ns> is a choice of either a nameserver group id, or an explicit <ns><ns><name>...
        servers = []
        ns_list_elem = ns_elem.find("ns")
        if ns_list_elem is not None:
            for ns_child in ns_list_elem.findall("ns"):
                name_el = ns_child.find("name")
                if name_el is not None and name_el.text:
                    servers.append(name_el.text)
        return servers

    def _parse_host_element(self, host_elem: ET.Element) -> Dict[str, Any]:
        name_el = host_elem.find("name")
        ips = [ip.text for ip in host_elem if ip.tag in ("ipv4", "ipv6") and ip.text is not None]
        return {"name": name_el.text if name_el is not None else None, "ips": ips}

    def domain_renew(self, domain_name: str, current_expiry_date: str, period: int = 1) -> int:
        params = {"name": domain_name, "currentExpirationDate": current_expiry_date, "period": period}
        resp = self._request("domain", "renew", params)
        action_id = resp.find(".//domain/renew/actionId")
        if action_id is not None and action_id.text is not None:
            return int(action_id.text)
        raise HRDAPIError(f"Renewal failed for domain {domain_name}")

    def action_list(self, last_id: Optional[int] = None) -> List[int]:
        params = {}
        if last_id is not None:
            params["lastId"] = last_id

        resp = self._request("action", "list", params)
        ids = resp.findall(".//action/list/id")
        return [int(i.text) for i in ids if i.text is not None]

    def action_info(self, action_id: int) -> Dict[str, Any]:
        params = {"id": action_id}
        resp = self._request("action", "info", params)
        info_elem = resp.find(".//action/info")

        if info_elem is not None:
            info = {}
            for child in info_elem:
                info[child.tag] = child.text
            return info
        raise HRDAPIError(f"Could not find info for action {action_id}")

    def user_info(self, user_id: int) -> Dict[str, Any]:
        params = {"id": user_id}
        resp = self._request("user", "info", params)
        info_elem = resp.find(".//user/info")

        if info_elem is not None:
            info = {}
            for child in info_elem:
                info[child.tag] = child.text
            return info
        raise HRDAPIError(f"Could not find info for user {user_id}")

    def user_list(self, last_id: Optional[int] = None) -> List[int]:
        params: Dict[str, Any] = {}
        if last_id is not None:
            params["lastId"] = last_id
        resp = self._request("user", "list", params)
        ids = resp.findall(".//user/list/id")
        return [int(i.text) for i in ids if i.text is not None]

    def domain_update(self, domain_name: str, nameservers: List[str]) -> Optional[int]:
        # nsOrGroupType (simple form): <name/><ns><ns><ns><name/></ns>...</ns></ns>
        # The API requires between 2 and 16 nameservers here.
        def build(target: ET.Element) -> None:
            ET.SubElement(target, "name").text = domain_name
            ns_choice = ET.SubElement(target, "ns")
            ns_list = ET.SubElement(ns_choice, "ns")
            for server in nameservers:
                ns_item = ET.SubElement(ns_list, "ns")
                ET.SubElement(ns_item, "name").text = server

        resp = self._request_custom("domain", "update", build)
        action_id = resp.find(".//domain/update/actionId")
        if action_id is not None and action_id.text is not None:
            return int(action_id.text)
        return None

    def _domain_host_action(
        self, method: str, name: str, ipv4: Optional[List[str]], ipv6: Optional[List[str]]
    ) -> Optional[int]:
        def build(target: ET.Element) -> None:
            ET.SubElement(target, "name").text = name
            for ip in ipv4 or []:
                ET.SubElement(target, "ipv4").text = ip
            for ip in ipv6 or []:
                ET.SubElement(target, "ipv6").text = ip

        resp = self._request_custom("domain", method, build)
        action_id = resp.find(f".//domain/{method}/actionId")
        if action_id is not None and action_id.text is not None:
            return int(action_id.text)
        return None

    def domain_host_create(
        self, name: str, ipv4: Optional[List[str]] = None, ipv6: Optional[List[str]] = None
    ) -> Optional[int]:
        return self._domain_host_action("hostCreate", name, ipv4, ipv6)

    def domain_host_update(
        self, name: str, ipv4: Optional[List[str]] = None, ipv6: Optional[List[str]] = None
    ) -> Optional[int]:
        return self._domain_host_action("hostUpdate", name, ipv4, ipv6)

    def domain_host_delete(self, name: str) -> Optional[int]:
        params = {"name": name}
        resp = self._request("domain", "hostDelete", params)
        action_id = resp.find(".//domain/hostDelete/actionId")
        if action_id is not None and action_id.text is not None:
            return int(action_id.text)
        return None

    def domain_host_info(self, name: str) -> Dict[str, Any]:
        params = {"name": name}
        resp = self._request("domain", "hostInfo", params)
        info_elem = resp.find(".//domain/hostInfo")
        if info_elem is None:
            raise HRDAPIError(f"Could not find host info for {name}")

        info: Dict[str, Any] = {"ips": []}
        for child in info_elem:
            if child.tag in ("ipv4", "ipv6") and child.text is not None:
                info["ips"].append(child.text)
            else:
                info[child.tag] = child.text
        return info

    def domain_host_list(self, last_name: Optional[str] = None) -> List[str]:
        params: Dict[str, Any] = {}
        if last_name:
            params["lastName"] = last_name
        resp = self._request("domain", "hostList", params)
        names = resp.findall(".//domain/hostList/name")
        return [n.text for n in names if n.text is not None]

    def poll_get(self) -> Optional[Dict[str, Any]]:
        resp = self._request("poll", "get")
        get_elem = resp.find(".//poll/get")
        if get_elem is None or len(get_elem) == 0:
            return None
        return {child.tag: child.text for child in get_elem}

    def poll_ack(self, poll_id: int) -> None:
        params = {"id": poll_id}
        self._request("poll", "ack", params)
