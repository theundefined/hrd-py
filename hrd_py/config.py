import os
import yaml
import stat
from typing import Dict, Any, Optional, List


class ConfigManager:
    DEFAULT_PATH = os.path.expanduser("~/.config/hrd/config.yaml")

    def __init__(self, path: Optional[str] = None):
        self.path = path or self.DEFAULT_PATH
        self.config: Dict[str, Any] = {"default_profile": None, "profiles": {}}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    self.config.update(loaded)

    def save(self):
        dirname = os.path.dirname(self.path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(self.path, "w") as f:
            yaml.safe_dump(self.config, f)

        # Set secure permissions (600)
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def get_profile(self, name: Optional[str] = None) -> Optional[Dict[str, str]]:
        name = name or self.config.get("default_profile")
        if not name:
            return None
        return self.config.get("profiles", {}).get(name)

    def add_profile(self, name: str, login: str, password: str, api_hash: str):
        if "profiles" not in self.config:
            self.config["profiles"] = {}

        self.config["profiles"][name] = {"login": login, "password": password, "api_hash": api_hash}

        if not self.config.get("default_profile"):
            self.config["default_profile"] = name

        self.save()

    def set_default(self, name: str):
        if name in self.config.get("profiles", {}):
            self.config["default_profile"] = name
            self.save()
            return True
        return False

    def list_profiles(self) -> List[str]:
        return list(self.config.get("profiles", {}).keys())

    def get_all_profiles(self) -> Dict[str, Dict[str, str]]:
        return self.config.get("profiles", {})

    def get_default_profile_name(self) -> Optional[str]:
        return self.config.get("default_profile")
