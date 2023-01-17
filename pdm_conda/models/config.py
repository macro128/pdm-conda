import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any

from pdm.exceptions import ProjectError
from pdm.project import ConfigItem, Project

from pdm_conda.mapping import DOWNLOAD_DIR_ENV_VAR

_CONFIG_MAP = {"mapping_download_dir": "pypi-mapping.download-dir"}
CONFIGS = [
    ("runner", ConfigItem("Conda runner executable", "conda")),
    ("channels", ConfigItem("Conda channels to use")),
    ("as-default-manager", ConfigItem("Use Conda to install all possible requirements", False)),
    ("dependencies", ConfigItem("Dependencies to install with Conda")),
    ("optional-dependencies", ConfigItem("Optional dependencies to install with Conda")),
    ("dev-dependencies", ConfigItem("Development dependencies to install with Conda")),
    (
        "pypi-mapping.download-dir",
        ConfigItem(
            "PyPI-Conda mapping download directory",
            Path().home() / ".pdm-conda/",
            env_var=DOWNLOAD_DIR_ENV_VAR,
        ),
    ),
]
CONFIGS = [(f"conda.{name}", config) for name, config in CONFIGS]


def is_decorated(func):
    return hasattr(func, "__wrapped__")


def is_conda_config_initialized(project: Project):
    return "conda" in project.pyproject.settings


@dataclass
class PluginConfig:
    _project: Project = field(repr=False, default=None)
    _initialized: bool = field(repr=False, default=False, compare=False)
    _set_project_config: bool = field(repr=False, default=False, compare=False)

    channels: list[str] = field(default_factory=list)
    runner: str = "conda"
    as_default_manager: bool = False
    dependencies: list[str] = field(default_factory=list, repr=False)
    optional_dependencies: dict[str, list] = field(default_factory=dict)
    dev_dependencies: dict[str, list] = field(default_factory=dict)
    mapping_download_dir: Path = field(repr=False, default=Path())

    def __post_init__(self):

        with self.omit_set_project_config():
            if self.runner not in ["conda", "micromamba", "mamba"]:
                raise ProjectError(f"Invalid Conda runner: {self.runner}")

        to_suscribe = [(self._project.pyproject._data, "update"), (self._project.pyproject, "reload")]
        for obj, name in to_suscribe:
            func = getattr(obj, name)
            if not is_decorated(func):
                setattr(obj, name, self.suscribe(self, func))
        self._set_project_config = True

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        # if plugin config is set then maybe update pyproject settings
        if not name.startswith("_") and not callable(getattr(self, name)):
            name = f"conda.{_CONFIG_MAP.get(name, name)}".replace("_", "-")
            name, config_item = next(filter(lambda n: name == n[0], CONFIGS))
            if self._set_project_config:
                name_path = name.split(".")
                name = name_path.pop(-1)
                config = self._project.pyproject.settings
                for p in name_path:
                    config = config.setdefault(p, dict())
                config[name] = value
                self._initialized = True
            if config_item.env_var:
                os.environ.setdefault(config_item.env_var, str(value))

    def reload(self):
        _conf = self.load_config(self._project)
        with self.omit_set_project_config():
            for k, v in _conf.__dict__.items():
                if not callable(v) and k not in ("_project", "_set_project_config") and getattr(self, k) != v:
                    setattr(self, k, v)

    @staticmethod
    def suscribe(config, func):
        """
        Suscribe to function call and after executed refresh config
        :param config: PluginConfig to refresh
        :param func: function to decorate
        """

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            config.reload()
            return result

        return wrapper

    @contextmanager
    def omit_set_project_config(self):
        """
        Context manager that deactivates updating pyproject settings
        :return:
        """
        old_value = self._set_project_config
        self._set_project_config = False
        yield
        self._set_project_config = old_value

    @property
    def is_initialized(self):
        return self._initialized

    @classmethod
    def load_config(cls, project: Project, **kwargs) -> "PluginConfig":
        """
        Load plugin configs from project settings.
        :param project: Project
        :param kwargs: settings overwrites
        :return: plugin configs
        """
        config = {k.replace("-", "_"): v for k, v in project.pyproject.settings.get("conda", {}).items()}
        kwargs["_initialized"] = is_conda_config_initialized(project)
        name = "mapping_download_dir"
        config[name] = Path(project.config[f"conda.{_CONFIG_MAP.get(name, name)}"])
        return PluginConfig(_project=project, **(config | kwargs))

    def command(self, cmd="install"):
        """
        Get runner command args
        :param cmd: command, install by default
        :return: args list
        """
        _command = [self.runner, cmd, "-y"]
        if cmd in ("install", "create", "search"):
            _command.append("--strict-channel-priority")
        return _command
