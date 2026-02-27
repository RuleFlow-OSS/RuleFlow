from platformdirs import user_data_path as _user_data_path
import json
from pathlib import Path

# Studio Config Globals
APPNAME: str = "RuleFlow Studio"
VERSION: str = "v0.1.0"
BREAKING_VERSION: str = "v0.1.0"  # determines if a new config folder is needed
USER_DATA_DIR_PATH: Path = _user_data_path(APPNAME, None, BREAKING_VERSION, ensure_exists=True)
PROJECTS_LIST_PATH: Path = USER_DATA_DIR_PATH.joinpath('projects.json')
SUPPORTED_FILE_TYPES: list[str] = ["*.flow", "*.md", "*.py"]


class __RecentProjects:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self._load_data()

    def _load_data(self) -> None:
        try:
            self.data.update(json.loads(PROJECTS_LIST_PATH.read_text()))
        except Exception:
            with open(str(PROJECTS_LIST_PATH), 'w') as f:
                json.dump(self.data, f, indent=4)

    def _save_changes(self) -> None:
        try:
            with open(str(PROJECTS_LIST_PATH), 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception:
            pass

    def get_path(self, name: str) -> Path:
        return Path(self.data[name])

    def list(self) -> dict[str, str]:
        return self.data.copy()

    def add(self, name: str, path: str) -> None:
        self.data[name] = path
        self._save_changes()

    def remove(self, name: str) -> None:
        del self.data[name]
        self._save_changes()
RecentProjects = __RecentProjects()  # Singleton Instance
