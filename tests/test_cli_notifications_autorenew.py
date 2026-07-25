from datetime import datetime, timedelta

from hrd_py.cli import cli
from hrd_py.config import ConfigManager
from hrd_py.exceptions import HRDError
from hrd_py.models import Domain, Owner


def _note(note_id, name="example.pl", action="renew", added="2026-01-01 10:00:00"):
    return {
        "id": note_id,
        "object": "domain",
        "objectName": name,
        "action": action,
        "added": added,
    }


# --- notifications ---------------------------------------------------------


def test_notifications_peek_shows_one_and_never_acks(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_next_notification.return_value = _note("1")

    result = runner.invoke(cli, ["notifications"])

    assert result.exit_code == 0
    assert "#1" in result.output
    assert "example.pl" in result.output
    assert "renew" in result.output
    mock_client.ack_notification.assert_not_called()
    # peek-only: must not loop past the first note
    assert mock_client.get_next_notification.call_count == 1


def test_notifications_ack_drains_until_empty(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_next_notification.side_effect = [
        _note("1", name="one.pl"),
        _note("2", name="two.pl"),
        None,
    ]

    result = runner.invoke(cli, ["notifications", "--ack"])

    assert result.exit_code == 0
    assert "one.pl" in result.output
    assert "two.pl" in result.output
    assert mock_client.ack_notification.call_count == 2
    mock_client.ack_notification.assert_any_call(1)
    mock_client.ack_notification.assert_any_call(2)
    assert mock_client.get_next_notification.call_count == 3


def test_notifications_ack_stops_at_limit(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_next_notification.side_effect = [
        _note("1", name="one.pl"),
        _note("2", name="two.pl"),
    ]

    result = runner.invoke(cli, ["notifications", "--ack", "--limit", "1"])

    assert result.exit_code == 0
    assert "one.pl" in result.output
    assert "two.pl" not in result.output
    assert mock_client.get_next_notification.call_count == 1
    mock_client.ack_notification.assert_called_once_with(1)


def test_notifications_none_pending(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_next_notification.return_value = None

    result = runner.invoke(cli, ["notifications"])

    assert result.exit_code == 0
    assert "No pending notifications." in result.output


def test_notifications_profile_error_is_caught(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.login.side_effect = HRDError("boom")

    result = runner.invoke(cli, ["notifications"])

    assert result.exit_code == 0
    assert "Error processing profile default: boom" in result.output


# --- owner-list --------------------------------------------------------


def test_owner_list_without_details_never_calls_get_owner(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_owner_ids.return_value = [100, 200]

    result = runner.invoke(cli, ["owner-list"])

    assert result.exit_code == 0
    assert "100" in result.output
    assert "200" in result.output
    mock_client.get_owner.assert_not_called()


def test_owner_list_with_details_shows_name_and_inline_error(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_owner_ids.return_value = [100, 200]

    def get_owner_side_effect(oid):
        if oid == 100:
            return Owner(name="Alice")
        raise HRDError("boom")

    mock_client.get_owner.side_effect = get_owner_side_effect

    result = runner.invoke(cli, ["owner-list", "--details"])

    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "200" in result.output
    assert "Error: boom" in result.output
    assert mock_client.get_owner.call_count == 2


def test_owner_list_no_subscribers(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_owner_ids.return_value = []

    result = runner.invoke(cli, ["owner-list"])

    assert result.exit_code == 0
    assert "No subscribers found." in result.output


# --- auto-renew --------------------------------------------------------


def test_auto_renew_dry_run_does_not_renew(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="soon.pl", status="active", expiry_date=datetime.now() + timedelta(days=5)),
    ]

    result = runner.invoke(cli, ["auto-renew", "--dry-run"])

    assert result.exit_code == 0
    assert "[DRY RUN] Would renew soon.pl" in result.output
    mock_client.renew_domain.assert_not_called()


def test_auto_renew_confirm_yes_renews(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="soon.pl", status="active", expiry_date=datetime.now() + timedelta(days=5)),
    ]
    mock_client.renew_domain.return_value = "action-123"

    result = runner.invoke(cli, ["auto-renew"], input="y\n")

    assert result.exit_code == 0
    mock_client.renew_domain.assert_called_once_with("soon.pl")
    assert "Success: action-123" in result.output


def test_auto_renew_confirm_no_skips(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="soon.pl", status="active", expiry_date=datetime.now() + timedelta(days=5)),
    ]

    result = runner.invoke(cli, ["auto-renew"], input="n\n")

    assert result.exit_code == 0
    assert "Skipping soon.pl" in result.output
    mock_client.renew_domain.assert_not_called()


def test_auto_renew_no_ask_renews_without_prompt(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="one.pl", status="active", expiry_date=datetime.now() + timedelta(days=5)),
        Domain(name="two.pl", status="active", expiry_date=datetime.now() + timedelta(days=10)),
    ]
    mock_client.renew_domain.return_value = "action-1"

    result = runner.invoke(cli, ["auto-renew", "--no-ask"])

    assert result.exit_code == 0
    assert mock_client.renew_domain.call_count == 2
    mock_client.renew_domain.assert_any_call("one.pl")
    mock_client.renew_domain.assert_any_call("two.pl")


def test_auto_renew_no_domains_expiring(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="faraway.pl", status="active", expiry_date=datetime.now() + timedelta(days=200)),
    ]

    result = runner.invoke(cli, ["auto-renew"])

    assert result.exit_code == 0
    assert "No domains found for renewal." in result.output


def test_auto_renew_failure_continues_to_next_domain(runner, mocker):
    cm = ConfigManager()
    cm.add_profile("default", "user", "pass", "aabb")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.list_domains.return_value = [
        Domain(name="bad.pl", status="active", expiry_date=datetime.now() + timedelta(days=5)),
        Domain(name="good.pl", status="active", expiry_date=datetime.now() + timedelta(days=10)),
    ]

    def renew_side_effect(name):
        if name == "bad.pl":
            raise HRDError("registry down")
        return "action-ok"

    mock_client.renew_domain.side_effect = renew_side_effect

    result = runner.invoke(cli, ["auto-renew", "--no-ask"])

    assert result.exit_code == 0
    assert "Failed: registry down" in result.output
    assert "Success: action-ok" in result.output
    assert mock_client.renew_domain.call_count == 2
