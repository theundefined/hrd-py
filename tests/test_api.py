import pytest
import struct
import hashlib
from hrd_py.api import HRDApi
from hrd_py.exceptions import HRDCommunicationError

def test_api_send_receives_correct_framing(mocker):
    # Mocking socket and ssl
    mock_socket = mocker.patch("socket.create_connection")
    mock_context = mocker.patch("ssl.create_default_context")
    mock_ssl_sock = mock_context.return_value.wrap_socket.return_value
    
    api = HRDApi("login", "pass", "deadbeef", verify_peer=False)
    
    # Mock response
    xml_response = '<api xmlns="http://api.hrd.pl/api/"><status>ok</status><token>test_token</token></api>'
    resp_bytes = xml_response.encode("utf-8")
    mock_ssl_sock.recv.side_effect = [
        struct.pack(">I", len(resp_bytes)),
        resp_bytes
    ]
    
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
    resp_xml = '<api><partner><getBalance><balance>100.50</balance><restrictedBalance>10.00</restrictedBalance></getBalance></partner></api>'
    mock_request.return_value = ET.fromstring(resp_xml)
    
    balance = api.partner_get_balance()
    
    assert balance["balance"] == 100.50
    assert balance["restricted_balance"] == 10.00
    mock_request.assert_called_once_with("partner", "getBalance")
