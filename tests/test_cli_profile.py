from hrd_py.cli import cli
from hrd_py.config import ConfigManager
from hrd_py.models import Balance


def test_profile_add_and_list_shows_default_marker(runner):
    result = runner.invoke(
        cli,
        [
            "profile",
            "add",
            "myprofile",
            "--login",
            "user1",
            "--password",
            "secret",
            "--hash",
            "aabbcc",
        ],
    )
    assert result.exit_code == 0
    assert "Profile 'myprofile' added successfully." in result.output

    result = runner.invoke(cli, ["profile", "list"])
    assert result.exit_code == 0
    assert "* myprofile" in result.output


def test_profile_list_empty(runner):
    result = runner.invoke(cli, ["profile", "list"])
    assert result.exit_code == 0
    assert "No profiles configured." in result.output


def test_profile_set_default_existing(runner):
    cm = ConfigManager()
    cm.add_profile("one", "u1", "p1", "h1")
    cm.add_profile("two", "u2", "p2", "h2")

    result = runner.invoke(cli, ["profile", "set-default", "two"])
    assert result.exit_code == 0
    assert "Default profile set to 'two'." in result.output

    result = runner.invoke(cli, ["profile", "list"])
    assert "* two" in result.output
    assert "  one" in result.output


def test_profile_set_default_nonexistent(runner):
    cm = ConfigManager()
    cm.add_profile("one", "u1", "p1", "h1")

    result = runner.invoke(cli, ["profile", "set-default", "ghost"])
    assert result.exit_code == 0
    assert "Error: Profile 'ghost' not found." in result.output


def test_get_client_prefers_config_over_env(runner, mocker, monkeypatch):
    # Env vars are set but a config profile also exists -> config must win.
    monkeypatch.setenv("HRD_LOGIN", "env-login")
    monkeypatch.setenv("HRD_PASS", "env-pass")
    monkeypatch.setenv("HRD_HASH", "env-hash")

    cm = ConfigManager()
    cm.add_profile("default", "config-login", "config-pass", "config-hash")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_balance.return_value = Balance(balance=1.0, restricted_balance=0.0)

    result = runner.invoke(cli, ["balance"])
    assert result.exit_code == 0

    mock_client_cls.assert_called_once_with("config-login", "config-pass", "config-hash", debug=False)


def test_get_client_falls_back_to_env_when_no_profile(runner, mocker, monkeypatch):
    monkeypatch.setenv("HRD_LOGIN", "env-login")
    monkeypatch.setenv("HRD_PASS", "env-pass")
    monkeypatch.setenv("HRD_HASH", "env-hash")

    mock_client_cls = mocker.patch("hrd_py.cli.HRDClient")
    mock_client = mock_client_cls.return_value
    mock_client.get_balance.return_value = Balance(balance=2.0, restricted_balance=0.0)

    result = runner.invoke(cli, ["balance"])
    assert result.exit_code == 0

    mock_client_cls.assert_called_once_with("env-login", "env-pass", "env-hash", debug=False)


def test_get_client_missing_config_and_env_exits_nonzero(runner):
    # Pin to an explicit, unconfigured profile via the global --profile option so the
    # `balance` command doesn't short-circuit on an empty get_profiles_to_process()
    # list (which would happen for the bare default case with nothing configured) and
    # instead actually reaches CLIContext.get_client()'s missing-config branch.
    result = runner.invoke(cli, ["--profile", "ghost", "balance"])
    assert result.exit_code == 1
    assert "Error: Missing configuration for profile 'ghost'." in result.output
    assert "Use 'hrd profile add' to set up credentials." in result.output
