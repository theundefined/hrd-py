from hrd_py.cli import cli
from hrd_py.config import ConfigManager
from hrd_py.exceptions import HRDError

# --- host list ---


def test_host_list_multiple_profiles(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        if login == "user1":
            client.list_hosts.return_value = ["ns1.example.com", "ns2.example.com"]
        else:
            client.list_hosts.return_value = ["ns3.example.org"]
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["host", "list"])

    assert result.exit_code == 0
    assert "Profile: alpha" in result.output
    assert "Profile: beta" in result.output
    assert "ns1.example.com" in result.output
    assert "ns2.example.com" in result.output
    assert "ns3.example.org" in result.output


def test_host_list_empty_shows_no_hosts_found(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_hosts.return_value = []

    result = runner.invoke(cli, ["host", "list"])

    assert result.exit_code == 0
    assert "No hosts found." in result.output


def test_host_list_error_in_one_profile_continues_to_next(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    def client_factory(login, password, api_hash, debug=False):
        client = mocker.MagicMock()
        if login == "user1":
            client.list_hosts.side_effect = HRDError("boom")
        else:
            client.list_hosts.return_value = ["ns.example.com"]
        return client

    mock_client_cls.side_effect = client_factory

    result = runner.invoke(cli, ["host", "list"])

    assert result.exit_code == 0
    assert "Error processing profile alpha: boom" in result.output
    assert "Profile: beta" in result.output
    assert "ns.example.com" in result.output


# --- host info ---


def test_host_info_found(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_host.return_value = {
        "name": "ns1.example.com",
        "ips": ["1.2.3.4", "::1"],
    }

    result = runner.invoke(cli, ["host", "info", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Name: ns1.example.com" in result.output
    assert "IPs:  1.2.3.4, ::1" in result.output
    mock_client.get_host.assert_called_once_with("ns1.example.com")


def test_host_info_not_found_shows_last_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_host.side_effect = HRDError("no such host")

    result = runner.invoke(cli, ["host", "info", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Error: no such host" in result.output


def test_host_info_no_profiles_configured(runner):
    result = runner.invoke(cli, ["host", "info", "ns1.example.com"])

    assert result.exit_code == 0
    assert "No profiles configured" in result.output


# --- host create ---


def test_host_create_requires_at_least_one_ip(runner, mocker):
    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    result = runner.invoke(cli, ["host", "create", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Error: provide at least one --ipv4 or --ipv6 address." in result.output
    mock_client_cls.assert_not_called()


def test_host_create_success_with_ipv4(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.create_host.return_value = 42

    result = runner.invoke(
        cli,
        [
            "host",
            "create",
            "ns1.example.com",
            "--ipv4",
            "1.2.3.4",
            "--ipv4",
            "5.6.7.8",
        ],
    )

    assert result.exit_code == 0
    assert "Host ns1.example.com created." in result.output
    assert "Action ID: 42" in result.output
    mock_client.create_host.assert_called_once_with("ns1.example.com", ["1.2.3.4", "5.6.7.8"], [])


def test_host_create_success_with_ipv6_no_action_id(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.create_host.return_value = None

    result = runner.invoke(cli, ["host", "create", "ns1.example.com", "--ipv6", "::1"])

    assert result.exit_code == 0
    assert "Host ns1.example.com created." in result.output
    assert "Action ID:" not in result.output
    mock_client.create_host.assert_called_once_with("ns1.example.com", [], ["::1"])


def test_host_create_failure_in_all_profiles(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.create_host.side_effect = HRDError("quota exceeded")

    result = runner.invoke(cli, ["host", "create", "ns1.example.com", "--ipv4", "1.2.3.4"])

    assert result.exit_code == 0
    assert "Error: quota exceeded" in result.output


# --- host update ---


def test_host_update_requires_at_least_one_ip(runner, mocker):
    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    result = runner.invoke(cli, ["host", "update", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Error: provide at least one --ipv4 or --ipv6 address." in result.output
    mock_client_cls.assert_not_called()


def test_host_update_success(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.update_host.return_value = 99

    result = runner.invoke(cli, ["host", "update", "ns1.example.com", "--ipv4", "9.9.9.9"])

    assert result.exit_code == 0
    assert "Host ns1.example.com updated." in result.output
    assert "Action ID: 99" in result.output
    mock_client.update_host.assert_called_once_with("ns1.example.com", ["9.9.9.9"], [])


def test_host_update_success_no_action_id(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.update_host.return_value = None

    result = runner.invoke(cli, ["host", "update", "ns1.example.com", "--ipv4", "9.9.9.9"])

    assert result.exit_code == 0
    assert "Host ns1.example.com updated." in result.output
    assert "Action ID:" not in result.output


def test_host_update_not_found_shows_last_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.update_host.side_effect = HRDError("no such host")

    result = runner.invoke(cli, ["host", "update", "ns1.example.com", "--ipv4", "9.9.9.9"])

    assert result.exit_code == 0
    assert "Error: no such host" in result.output


# --- host delete ---


def test_host_delete_success(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.delete_host.return_value = 7

    result = runner.invoke(cli, ["host", "delete", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Host ns1.example.com deleted." in result.output
    assert "Action ID: 7" in result.output
    mock_client.delete_host.assert_called_once_with("ns1.example.com")


def test_host_delete_success_no_action_id(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.delete_host.return_value = None

    result = runner.invoke(cli, ["host", "delete", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Host ns1.example.com deleted." in result.output
    assert "Action ID:" not in result.output


def test_host_delete_not_found_shows_last_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.delete_host.side_effect = HRDError("no such host")

    result = runner.invoke(cli, ["host", "delete", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Error: no such host" in result.output
