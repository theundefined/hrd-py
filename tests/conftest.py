import pytest
from click.testing import CliRunner

from hrd_py.config import ConfigManager


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Keep CLI tests from touching the real ~/.config/hrd/config.yaml or picking up
    real credentials that hrd_py.cli's module-level load_dotenv() may have already
    loaded from this repo's .env file into the process environment."""
    monkeypatch.setattr(ConfigManager, "DEFAULT_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.delenv("HRD_LOGIN", raising=False)
    monkeypatch.delenv("HRD_PASS", raising=False)
    monkeypatch.delenv("HRD_HASH", raising=False)


@pytest.fixture
def runner():
    return CliRunner()
