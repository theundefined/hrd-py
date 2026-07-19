import struct
import hashlib
from hrd_py.api import HRDApi


def test_api_send_receives_correct_framing(mocker):
    # Mocking socket and ssl
    mocker.patch("socket.create_connection")
    mock_context = mocker.patch("ssl.create_default_context")
    mock_ssl_sock = mock_context.return_value.wrap_socket.return_value

    api = HRDApi("login", "pass", "deadbeef", verify_peer=False)

    # Mock response
    xml_response = '<api xmlns="http://api.hrd.pl/api/"><status>ok</status><token>test_token</token></api>'
    resp_bytes = xml_response.encode("utf-8")
    mock_ssl_sock.recv.side_effect = [struct.pack(">I", len(resp_bytes)), resp_bytes]

    token = api.login()

    assert token == "test_token"
    assert api.token == "test_token"

    # Verify what was sent
    sent_data = mock_ssl_sock.sendall.call_args[0][0]
    length = struct.unpack(">I", sent_data[:4])[0]
    hash_sent = sent_data[4:68]
    xml_sent = sent_data[68:].decode("utf-8")

    assert length == len(sent_data) - 4
    assert "<login>" in xml_sent

    # Verify hash: SHA512(XML + binary_api_hash)
    h = hashlib.sha512()
    h.update(xml_sent.encode("utf-8"))
    h.update(bytes.fromhex("deadbeef"))
    assert h.digest() == hash_sent


def test_partner_get_balance(mocker):
    api = HRDApi("login", "pass", "deadbeef")
    api.token = "test_token"

    mock_request = mocker.patch.object(HRDApi, "_request")

    import xml.etree.ElementTree as ET

    resp_xml = "<api><partner><getBalance><balance>100.50</balance><restrictedBalance>10.00</restrictedBalance></getBalance></partner></api>"
    mock_request.return_value = ET.fromstring(resp_xml)

    balance = api.partner_get_balance()

    assert balance["balance"] == 100.50
    assert balance["restricted_balance"] == 10.00
    mock_request.assert_called_once_with("partner", "getBalance")


def test_domain_update_builds_nested_ns_and_requires_no_minimum_in_api_layer(mocker):
    # The API itself doesn't enforce the >=2 nameserver minimum (that's the CLI's job to check
    # before calling); here we just verify the nested <ns><ns><ns><name/></ns>...</ns></ns> shape.
    import xml.etree.ElementTree as ET

    api = HRDApi("login", "pass", "deadbeef")
    mock_execute = mocker.patch.object(HRDApi, "_execute")
    mock_execute.return_value = ET.fromstring("<api><domain><update><actionId>42</actionId></update></domain></api>")

    action_id = api.domain_update("example.com", ["ns1.example.com", "ns2.example.com"])

    assert action_id == 42
    sent_root = mock_execute.call_args[0][0]
    xml_str = ET.tostring(sent_root, encoding="unicode")
    assert xml_str == (
        '<api xmlns="http://api.hrd.pl/api/"><domain><update>'
        "<name>example.com</name>"
        "<ns><ns><ns><name>ns1.example.com</name></ns><ns><name>ns2.example.com</name></ns></ns></ns>"
        "</update></domain></api>"
    )


def test_domain_update_returns_none_without_action_id(mocker):
    import xml.etree.ElementTree as ET

    api = HRDApi("login", "pass", "deadbeef")
    mocker.patch.object(HRDApi, "_execute", return_value=ET.fromstring("<api><domain><update/></domain></api>"))

    assert api.domain_update("example.com", ["ns1.example.com", "ns2.example.com"]) is None


def test_domain_host_create_appends_repeated_ips(mocker):
    import xml.etree.ElementTree as ET

    api = HRDApi("login", "pass", "deadbeef")
    mock_execute = mocker.patch.object(HRDApi, "_execute")
    mock_execute.return_value = ET.fromstring(
        "<api><domain><hostCreate><actionId>7</actionId></hostCreate></domain></api>"
    )

    action_id = api.domain_host_create("ns1.example.com", ipv4=["1.2.3.4", "1.2.3.5"])

    assert action_id == 7
    sent_root = mock_execute.call_args[0][0]
    xml_str = ET.tostring(sent_root, encoding="unicode")
    assert "<name>ns1.example.com</name><ipv4>1.2.3.4</ipv4><ipv4>1.2.3.5</ipv4>" in xml_str


def test_poll_get_returns_none_when_queue_empty(mocker):
    import xml.etree.ElementTree as ET

    api = HRDApi("login", "pass", "deadbeef")
    mock_request = mocker.patch.object(HRDApi, "_request")
    mock_request.return_value = ET.fromstring("<api><poll><get/></poll></api>")

    assert api.poll_get() is None


def test_poll_get_returns_notification_dict(mocker):
    import xml.etree.ElementTree as ET

    api = HRDApi("login", "pass", "deadbeef")
    mock_request = mocker.patch.object(HRDApi, "_request")
    mock_request.return_value = ET.fromstring(
        "<api><poll><get>"
        "<id>1</id><object>domain</object><objectName>example.com</objectName>"
        "<action>expire</action><added>2026-01-01 00:00:00</added>"
        "</get></poll></api>"
    )

    note = api.poll_get()

    assert note == {
        "id": "1",
        "object": "domain",
        "objectName": "example.com",
        "action": "expire",
        "added": "2026-01-01 00:00:00",
    }


def test_user_list_pages_ids(mocker):
    import xml.etree.ElementTree as ET

    api = HRDApi("login", "pass", "deadbeef")
    mock_request = mocker.patch.object(HRDApi, "_request")
    mock_request.return_value = ET.fromstring("<api><user><list><id>1</id><id>2</id></list></user></api>")

    assert api.user_list() == [1, 2]
    mock_request.assert_called_once_with("user", "list", {})
