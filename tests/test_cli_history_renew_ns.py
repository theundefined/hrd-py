from datetime import datetime

from hrd_py.cli import cli
from hrd_py.config import ConfigManager
from hrd_py.exceptions import HRDError
from hrd_py.models import HistoryEntry


def _client_factory(mocker, by_login):
    """Build a mocker.patch side_effect for hrd_py.cli.HRDClient that returns a
    distinct MagicMock per login, so each configured profile can be scripted
    independently (mirrors the pattern in test_cli_balance_domains.py)."""

    def factory(login, password, api_hash, debug=False):
        return by_login[login]

    return factory


def test_history_merges_two_profiles_sorted_newest_first(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    alpha_client = mocker.MagicMock()
    alpha_client.get_history.return_value = [
        HistoryEntry(
            id=1,
            type="renew",
            object="domain",
            object_name="old.com",
            status="done",
            amount=10.0,
            date=datetime(2024, 1, 1, 10, 0, 0),
        ),
        HistoryEntry(
            id=2,
            type="renew",
            object="domain",
            object_name="newest.com",
            status="done",
            amount=20.0,
            date=datetime(2024, 3, 1, 10, 0, 0),
        ),
    ]

    beta_client = mocker.MagicMock()
    beta_client.get_history.return_value = [
        HistoryEntry(
            id=3,
            type="create",
            object="domain",
            object_name="middle.com",
            status="done",
            amount=30.0,
            date=datetime(2024, 2, 1, 10, 0, 0),
        ),
    ]

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client_cls.side_effect = _client_factory(mocker, {"user1": alpha_client, "user2": beta_client})

    result = runner.invoke(cli, ["history"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if "|" in line]
    # header + 3 rows
    assert len(lines) == 4
    header, row_newest, row_middle, row_oldest = lines

    assert header == f"{'DATE':19} | {'PROFILE':12} | {'TYPE':10} | {'OBJECT':30} | {'COST':>10} | STATUS"

    assert row_newest == (
        f"{'2024-03-01 10:00:00':19} | {'alpha':12} | {'renew':10} | " f"{'newest.com':30} | {'20.00':>10} | done"
    )
    assert row_middle == (
        f"{'2024-02-01 10:00:00':19} | {'beta':12} | {'create':10} | " f"{'middle.com':30} | {'30.00':>10} | done"
    )
    assert row_oldest == (
        f"{'2024-01-01 10:00:00':19} | {'alpha':12} | {'renew':10} | " f"{'old.com':30} | {'10.00':>10} | done"
    )

    alpha_client.get_history.assert_called_once_with(limit=20)
    beta_client.get_history.assert_called_once_with(limit=20)


def test_history_respects_limit_option(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_history.return_value = []

    result = runner.invoke(cli, ["history", "--limit", "5"])

    assert result.exit_code == 0
    mock_client.get_history.assert_called_once_with(limit=5)


def test_history_entry_with_none_date_sorts_last(runner, mocker):
    # rows.sort(key=lambda r: r[1].date or datetime.min, reverse=True) - datetime.min
    # is the smallest possible key, so with reverse=True (descending) it ends up
    # last, not first.
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_history.return_value = [
        HistoryEntry(
            id=1,
            type="renew",
            object="domain",
            object_name="dated.com",
            status="done",
            amount=1.0,
            date=datetime(2024, 1, 1),
        ),
        HistoryEntry(
            id=2,
            type="renew",
            object="domain",
            object_name="undated.com",
            status="done",
            amount=2.0,
            date=None,
        ),
    ]

    result = runner.invoke(cli, ["history"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if "|" in line]
    assert len(lines) == 3
    _header, row_dated, row_undated = lines
    assert "dated.com" in row_dated
    assert "undated.com" in row_undated
    assert row_undated.startswith(f"{'unknown':19}")


def test_history_no_entries_shows_message(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_history.return_value = []

    result = runner.invoke(cli, ["history"])

    assert result.exit_code == 0
    assert "No history found." in result.output


def test_history_profile_error_is_caught_others_still_show(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    alpha_client = mocker.MagicMock()
    alpha_client.get_history.side_effect = HRDError("boom")

    beta_client = mocker.MagicMock()
    beta_client.get_history.return_value = [
        HistoryEntry(
            id=1,
            type="renew",
            object="domain",
            object_name="ok.com",
            status="done",
            amount=5.0,
            date=datetime(2024, 5, 1),
        ),
    ]

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client_cls.side_effect = _client_factory(mocker, {"user1": alpha_client, "user2": beta_client})

    result = runner.invoke(cli, ["history"])

    assert result.exit_code == 0
    assert "Error processing profile alpha: boom" in result.output
    assert "ok.com" in result.output


def test_renew_success_first_profile(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.renew_domain.return_value = 987

    result = runner.invoke(cli, ["renew", "example.com", "--period", "2"])

    assert result.exit_code == 0
    assert "Success! Action ID: 987" in result.output
    mock_client.renew_domain.assert_called_once_with("example.com", 2)


def test_renew_default_period_is_one(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.renew_domain.return_value = 1

    result = runner.invoke(cli, ["renew", "example.com"])

    assert result.exit_code == 0
    mock_client.renew_domain.assert_called_once_with("example.com", 1)


def test_renew_fails_in_all_profiles_shows_last_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("alpha", "user1", "pass1", "aabb")
    cm.add_profile("beta", "user2", "pass2", "ccdd")

    alpha_client = mocker.MagicMock()
    alpha_client.renew_domain.side_effect = HRDError("not found in alpha")

    beta_client = mocker.MagicMock()
    beta_client.renew_domain.side_effect = HRDError("not found in beta")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client_cls.side_effect = _client_factory(mocker, {"user1": alpha_client, "user2": beta_client})

    result = runner.invoke(cli, ["renew", "example.com"])

    assert result.exit_code == 0
    assert "Error: not found in beta" in result.output


def test_nameservers_fewer_than_two_errors_before_any_client_use(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")

    result = runner.invoke(cli, ["nameservers", "example.com", "ns1.example.com"])

    assert result.exit_code == 0
    assert "Error: at least 2 nameservers are required." in result.output
    mock_client_cls.assert_not_called()


def test_nameservers_success_with_action_id(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.update_nameservers.return_value = 42

    result = runner.invoke(cli, ["nameservers", "example.com", "ns1.example.com", "ns2.example.com"])

    assert result.exit_code == 0
    assert "Nameservers for example.com updated to: ns1.example.com, ns2.example.com" in result.output
    assert "Action ID: 42" in result.output
    mock_client.update_nameservers.assert_called_once_with("example.com", ["ns1.example.com", "ns2.example.com"])


def test_nameservers_success_without_action_id(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.update_nameservers.return_value = None

    result = runner.invoke(cli, ["nameservers", "example.com", "ns1.example.com", "ns2.example.com"])

    assert result.exit_code == 0
    assert "Nameservers for example.com updated to: ns1.example.com, ns2.example.com" in result.output
    assert "Action ID:" not in result.output
