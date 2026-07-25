from datetime import datetime, timedelta

from hrd_py.cli import cli
from hrd_py.config import ConfigManager
from hrd_py.exceptions import HRDError
from hrd_py.models import Domain, DomainDetails, Owner


def _full_owner():
    return Owner(
        name="Jane Doe",
        id=173216,
        type="individual",
        email="jane@example.com",
        street="Main St 1",
        city="Warsaw",
        postcode="00-001",
        country="PL",
        id_number="1234567890",
        landline_phone="+48221234567",
        mobile_phone="+48501234567",
    )


def _full_domain_details(**overrides):
    defaults = dict(
        name="example.com",
        status="active",
        create_date=datetime(2020, 1, 1),
        expiry_date=datetime(2027, 1, 1),
        privacy=True,
        privacy_protection_date=datetime(2020, 1, 2),
        nameservers=["ns1.example.com", "ns2.example.com"],
        hosts=[{"name": "ns1.example.com", "ips": ["1.2.3.4"]}],
        dnssec_records=[{"key": "value"}],
        action_ids=[1, 2, 3],
        owner_id=173216,
        owner=_full_owner(),
    )
    defaults.update(overrides)
    return DomainDetails(**defaults)


# --- domain-info ---


def test_domain_info_found_first_profile_full_details(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_domain_details.return_value = _full_domain_details()

    result = runner.invoke(cli, ["domain-info", "example.com"])

    assert result.exit_code == 0
    out = result.output
    assert "Domain:      example.com" in out
    assert "Status:      active" in out
    assert "Created:     2020-01-01" in out
    assert "Expires:     2027-01-01" in out
    assert "Privacy:     enabled (since 2020-01-02)" in out
    assert "Nameservers: ns1.example.com, ns2.example.com" in out
    assert "Glue hosts:  ns1.example.com (1.2.3.4)" in out
    assert "DNSSEC:      1 record(s)" in out
    assert "Actions:     1, 2, 3" in out
    assert "Owner:" in out
    assert "ID:      173216" in out
    assert "Name:    Jane Doe" in out
    assert "Type:    individual" in out
    assert "Tax/ID:  1234567890" in out
    assert "Email:   jane@example.com" in out
    assert "Address: Main St 1, 00-001, Warsaw, PL" in out
    assert "Phone:   +48221234567" in out
    assert "Mobile:  +48501234567" in out
    mock_client.login.assert_called_once()


def test_domain_info_optional_fields_absent(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_domain_details.return_value = DomainDetails(
        name="bare.com",
        status="active",
        privacy=False,
        owner_id=42,
        owner=None,
    )

    result = runner.invoke(cli, ["domain-info", "bare.com"])

    assert result.exit_code == 0
    out = result.output
    assert "Domain:      bare.com" in out
    assert "Created:     unknown" in out
    assert "Expires:     unknown" in out
    assert "Privacy:     disabled" in out
    assert "Nameservers:" not in out
    assert "Glue hosts:" not in out
    assert "DNSSEC:" not in out
    assert "Actions:" not in out
    assert "ID:      42" in out
    assert "  unknown" in out


def test_domain_info_second_profile_after_first_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        if login == "user1":
            client.get_domain_details.side_effect = HRDError("not on alpha")
        else:
            client.get_domain_details.return_value = _full_domain_details(name="found.com")
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["domain-info", "found.com"])

    assert result.exit_code == 0
    assert "Domain:      found.com" in result.output
    assert "not on alpha" not in result.output


def test_domain_info_not_found_in_any_profile(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        client.get_domain_details.side_effect = HRDError(f"no such domain ({login})")
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["domain-info", "missing.com"])

    assert result.exit_code == 0
    # last_error is always set here (every profile raised), so we always hit the
    # "Error: <last_error>" branch, carrying the *last* profile's error message.
    assert "Error: no such domain (user2)" in result.output
    assert "not found in any configured profile" not in result.output


# --- owner-info ---


def test_owner_info_found_first_profile_lists_only_matching_domains(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_owner.return_value = _full_owner()
    mock_client.list_domains.return_value = [
        Domain(name="mine.com", status="active", expiry_date=datetime.now() + timedelta(days=5), owner_id=173216),
        Domain(name="also-mine.com", status="expired", expiry_date=None, owner_id=173216),
        Domain(name="not-mine.com", status="active", expiry_date=datetime.now() + timedelta(days=5), owner_id=99),
    ]

    result = runner.invoke(cli, ["owner-info", "173216"])

    assert result.exit_code == 0
    out = result.output
    assert "ID:      173216" in out
    assert "Name:    Jane Doe" in out
    assert "Type:    individual" in out
    assert "Tax/ID:  1234567890" in out
    assert "Email:   jane@example.com" in out
    assert "Address: Main St 1, 00-001, Warsaw, PL" in out
    assert "Phone:   +48221234567" in out
    assert "Mobile:  +48501234567" in out
    assert "Domains (2):" in out
    assert "mine.com" in out
    assert "also-mine.com" in out
    assert "not-mine.com" not in out
    mock_client.login.assert_called_once()


def test_owner_info_second_profile_after_first_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        if login == "user1":
            client.get_owner.side_effect = HRDError("not on alpha")
        else:
            client.get_owner.return_value = Owner(name="Found Owner")
            client.list_domains.return_value = []
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["owner-info", "173216"])

    assert result.exit_code == 0
    assert "Name:    Found Owner" in result.output
    assert "not on alpha" not in result.output


def test_owner_info_not_found_in_any_profile(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        client.get_owner.side_effect = HRDError(f"no such owner ({login})")
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["owner-info", "999"])

    assert result.exit_code == 0
    assert "Error: no such owner (user2)" in result.output
    assert "not found in any configured profile" not in result.output
