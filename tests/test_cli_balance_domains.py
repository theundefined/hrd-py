from datetime import datetime, timedelta

from hrd_py.cli import cli
from hrd_py.config import ConfigManager
from hrd_py.exceptions import HRDError
from hrd_py.models import Balance, Domain


def test_balance_no_profiles_configured(runner):
    result = runner.invoke(cli, ["balance"])

    assert result.exit_code == 0
    assert "No profiles configured" in result.output


def test_balance_single_profile(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_balance.return_value = Balance(balance=100.0, restricted_balance=5.0)

    result = runner.invoke(cli, ["balance"])

    assert result.exit_code == 0
    assert "Profile: default" in result.output
    assert "Current Balance: 100.0" in result.output
    assert "Restricted Balance: 5.0" in result.output
    mock_client.login.assert_called_once()


def test_balance_multiple_profiles(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_balance.return_value = Balance(balance=42.0, restricted_balance=1.0)

    result = runner.invoke(cli, ["balance"])

    assert result.exit_code == 0
    assert "Profile: alpha" in result.output
    assert "Profile: beta" in result.output
    assert mock_client.login.call_count == 2


def test_balance_profile_error_is_caught(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.login.side_effect = HRDError("boom")

    result = runner.invoke(cli, ["balance"])

    assert result.exit_code == 0
    assert "Error processing profile default: boom" in result.output


def test_balance_profile_error_continues_to_next_profile(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        if login == "user1":
            client.login.side_effect = HRDError("boom")
        else:
            client.get_balance.return_value = Balance(balance=7.0, restricted_balance=0.0)
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["balance"])

    assert result.exit_code == 0
    assert "Error processing profile alpha: boom" in result.output
    assert "Profile: beta" in result.output
    assert "Current Balance: 7.0" in result.output


def test_domains_all_shows_every_domain(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="soon.com", status="active", expiry_date=datetime.now() + timedelta(days=5)),
        Domain(name="later.com", status="active", expiry_date=datetime.now() + timedelta(days=200)),
    ]

    result = runner.invoke(cli, ["domains", "--all"])

    assert result.exit_code == 0
    assert "soon.com" in result.output
    assert "later.com" in result.output


def test_domains_default_only_shows_expiring_soon(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="soon.com", status="active", expiry_date=datetime.now() + timedelta(days=5)),
        Domain(name="later.com", status="active", expiry_date=datetime.now() + timedelta(days=200)),
    ]

    result = runner.invoke(cli, ["domains"])

    assert result.exit_code == 0
    assert "soon.com" in result.output
    assert "later.com" not in result.output


def test_domains_custom_days_changes_cutoff(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="later.com", status="active", expiry_date=datetime.now() + timedelta(days=200)),
    ]

    result = runner.invoke(cli, ["domains", "--days", "400"])

    assert result.exit_code == 0
    assert "later.com" in result.output


def test_domains_no_matching_domains(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="later.com", status="active", expiry_date=datetime.now() + timedelta(days=200)),
    ]

    result = runner.invoke(cli, ["domains"])

    assert result.exit_code == 0
    assert "No domains found." in result.output


def test_domains_error_is_caught(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.side_effect = HRDError("kaboom")

    result = runner.invoke(cli, ["domains"])

    assert result.exit_code == 0
    assert "Error processing profile default: kaboom" in result.output
