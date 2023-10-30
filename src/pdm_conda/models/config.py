from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
from pdm.exceptions import NoConfigError, ProjectError
from pdm.project import Config, ConfigItem

from pdm_conda import logger
from pdm_conda.mapping import (
    MAPPING_DOWNLOAD_DIR_ENV_VAR,
    MAPPING_URL,
    MAPPING_URL_ENV_VAR,
)
from pdm_conda.models.requirements import parse_requirement

if TYPE_CHECKING:
    from typing import Any

    from pdm.project import Project


class CondaRunner(str, Enum):
    CONDA = "conda"
    MAMBA = "mamba"
    MICROMAMBA = "micromamba"


class CondaSolver(str, Enum):
    CONDA = "conda"
    MAMBA = "libmamba"


CONFIGS = [
    ("runner", ConfigItem("Conda runner executable", CondaRunner.CONDA.value, env_var="PDM_CONDA_RUNNER")),
    ("solver", ConfigItem("Solver to use for Conda resolution", CondaSolver.CONDA.value, env_var="PDM_CONDA_SOLVER")),
    ("channels", ConfigItem("Conda channels to use")),
    (
        "as-default-manager",
        ConfigItem("Use Conda to install all possible requirements", False, env_var="PDM_CONDA_AS_DEFAULT_MANAGER"),
    ),
    (
        "batched-commands",
        ConfigItem("Execute batched install and remove commands", False, env_var="PDM_CONDA_BATCHED_COMMANDS"),
    ),
    (
        "installation-method",
        ConfigItem(
            "Whether to use hard-link or copy when installing",
            "hard-link",
            env_var="PDM_CONDA_INSTALLATION_METHOD",
        ),
    ),
    ("dependencies", ConfigItem("Dependencies to install with Conda")),
    ("optional-dependencies", ConfigItem("Optional dependencies to install with Conda")),
    ("dev-dependencies", ConfigItem("Development dependencies to install with Conda")),
    ("excludes", ConfigItem("Excluded dependencies from Conda")),
    (
        "pypi-mapping.download-dir",
        ConfigItem(
            "PyPI-Conda mapping download directory",
            Path().home() / ".pdm-conda/",
            env_var=MAPPING_DOWNLOAD_DIR_ENV_VAR,
        ),
    ),
    (
        "pypi-mapping.url",
        ConfigItem(
            "PyPI-Conda mapping url",
            MAPPING_URL,
            env_var=MAPPING_URL_ENV_VAR,
        ),
    ),
    ("custom-behavior", ConfigItem("Use pdm-conda custom behavior", False, env_var="PDM_CONDA_CUSTOM_BEHAVIOR")),
]

_CONFIG_MAP = {name: name.replace("-", "_") for (name, _) in CONFIGS}
_CONFIG_MAP |= {
    "pypi-mapping.download-dir": "mapping_download_dir",
    "pypi-mapping.url": "mapping_url",
}
_CONFIG_MAP |= {v: k for k, v in _CONFIG_MAP.items()}
_CONFIG_MAP["_excludes"] = "excludes"

CONFIGS = [(f"conda.{name}", config) for name, config in CONFIGS]
PDM_CONFIG = {
    "conda.runner": "venv.backend",
}


def is_decorated(func):
    return hasattr(func, "__wrapped__")


def is_conda_config_initialized(project: Project):
    return "conda" in project.pyproject.settings


@dataclass
class PluginConfig:
    _project: Project = field(repr=False, default=None)
    _initialized: bool = field(repr=False, default=False, compare=False)
    _set_project_config: bool = field(repr=False, default=False, compare=False, init=False)
    _excludes: list[str] = field(repr=False, compare=False, init=False, default_factory=list)
    _excluded_identifiers: set[str] | None = field(default=None, repr=False, init=False)

    channels: list[str] = field(default_factory=list)
    runner: str = CondaRunner.CONDA
    solver: str = CondaSolver.CONDA
    as_default_manager: bool = False
    custom_behavior: bool = False
    batched_commands: bool = False
    installation_method: str = "hard-link"
    dependencies: list[str] = field(default_factory=list, repr=False)
    optional_dependencies: dict[str, list] = field(default_factory=dict)
    dev_dependencies: dict[str, list] = field(default_factory=dict)
    mapping_download_dir: Path = field(repr=False, default=Path())
    mapping_url: str = field(repr=False, default=MAPPING_URL)

    def __post_init__(self):
        if self.runner not in list(CondaRunner):
            raise ProjectError(f"Invalid Conda runner: {self.runner}")
        if self.solver not in list(CondaSolver):
            raise ProjectError(f"Invalid Conda solver: {self.solver}")
        if self.installation_method not in ["hard-link", "copy"]:
            raise ProjectError(f"Invalid Conda installation method: {self.installation_method}")
        to_suscribe = [
            (self._project.pyproject._data, "update"),
            (self._project.pyproject, "write"),
            (self._project.pyproject, "reload"),
        ]
        for obj, name in to_suscribe:
            func = getattr(obj, name)
            if not is_decorated(func):
                setattr(obj, name, self.suscribe(self, func))
        if not self.is_initialized:
            self.is_initialized = is_conda_config_initialized(self._project)

        self._set_project_config = True

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        # if plugin config is set then maybe update pyproject settings
        if (
            ((not name.startswith("_")) or name == "_excludes")
            and not isinstance(getattr(type(self), name, None), property)
            and not callable(getattr(self, name))
        ):
            name = f"conda.{_CONFIG_MAP[name]}"
            name, config_item = next(filter(lambda n: name == n[0], CONFIGS))
            if self._set_project_config:
                name_path = name.split(".")
                name = name_path.pop(-1)
                config = self._project.pyproject.settings
                for p in name_path:
                    config = config.setdefault(p, dict())

                _value = value
                if isinstance(value, list):
                    _value = tomlkit.array()
                    for v in value:
                        _value.append(v)
                    _value.multiline(len(value) > 1)

                config[name] = _value
                self.is_initialized |= self._project.pyproject.exists()
                if (project_config := PDM_CONFIG.get(name, None)) is not None:
                    self._project.project_config[project_config] = value
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
    def with_config(self, **kwargs):
        """
        Context manager that temporarily updates configs without updating pyproject settings
        """
        configs = ["_set_project_config"] + list(kwargs)
        kwargs["_set_project_config"] = False
        old_values = {}
        for name in configs:
            old_values[name] = getattr(self, name)
            setattr(self, name, kwargs[name])
        try:
            yield
        finally:
            for name in reversed(configs):
                setattr(self, name, old_values[name])

    @contextmanager
    def omit_set_project_config(self):
        """
        Context manager that deactivates updating pyproject settings
        """
        with self.with_config():
            yield

    @property
    def excluded_identifiers(self) -> set[str]:
        if self._excluded_identifiers is None:
            self._excluded_identifiers = {parse_requirement(name).identify() for name in self._excludes}
        return self._excluded_identifiers

    @property
    def excludes(self) -> list[str]:
        return self._excludes

    @excludes.setter
    def excludes(self, value):
        excluded = getattr(self, "_excludes", set())
        if set(value) != excluded:
            self._excludes = list(value)
            self._excluded_identifiers = None

    @property
    def is_initialized(self):
        return self._initialized

    @is_initialized.setter
    def is_initialized(self, value):
        if value and not self._initialized:
            config = self._project.project_config
            config["python.use_venv"] = True
            config["python.use_pyenv"] = False
            config["venv.backend"] = self.runner
            config.setdefault("venv.in_project", False)
            os.environ.pop("PDM_IGNORE_ACTIVE_VENV", None)
        self._initialized = value

    @contextmanager
    def with_conda_venv_location(self):
        conf_name = "venv.location"
        overriden = False
        if (previous_value := self._project.config[conf_name]) == Config.get_defaults()[conf_name] and (
            venv_location := os.getenv("VIRTUAL_ENV", os.getenv("CONDA_PREFIX", None))
        ) is not None:
            venv_location = Path(venv_location)
            for parent in (venv_location, *venv_location.parents):
                if (venv_path := (parent / "envs")).is_dir():
                    logger.info(f"Using detected Conda path for environment: [success]{venv_path}[/]")
                    self._project.global_config[conf_name] = str(venv_path)
                    del self._project.config
                    overriden = True
                    break
        try:
            yield Path(self._project.config[conf_name]), overriden
        finally:
            self._project.global_config[conf_name] = previous_value
            if overriden:
                del self._project.config

    @classmethod
    def load_config(cls, project: Project, **kwargs) -> "PluginConfig":
        """
        Load plugin configs from project settings.
        :param project: Project
        :param kwargs: settings overwrites
        :return: plugin configs
        """

        def flatten_config(config, allowed_levels, parent_key="", result=None) -> dict:
            if result is None:
                result = dict()
            for key, v in config.items():
                key = ".".join(k for k in (parent_key, key) if k)
                if isinstance(v, dict) and key in allowed_levels:
                    return flatten_config(v, allowed_levels, key, result)
                else:
                    if key not in _CONFIG_MAP:
                        raise NoConfigError(key)
                    result[_CONFIG_MAP[key]] = v
            return result

        config = flatten_config(project.pyproject.settings.get("conda", {}), ["pypi-mapping"])
        for n, c in CONFIGS:
            if (prop_name := _CONFIG_MAP[n[len("conda.") :]]) not in config and c.env_var:
                value = project.config[n]
                if prop_name == "mapping_download_dir":
                    value = Path(value)
                elif prop_name in ("as_default_manager", "batched_commands", "custom_behavior"):
                    value = str(value).lower() in ("true", "1")
                config[prop_name] = value
        config |= kwargs
        excludes = config.pop("excludes", None)
        plugin_config = PluginConfig(_project=project, **config)
        if excludes is not None:
            plugin_config.excludes = excludes
        return plugin_config

    def command(self, cmd="install"):
        """
        Get runner command args
        :param cmd: command, install by default
        :return: args list
        """
        runner = self.runner
        if cmd == "remove" and runner == CondaRunner.MAMBA:
            runner = CondaRunner.CONDA
        if isinstance(runner, CondaRunner):
            runner = runner.value

        _command = [runner, *cmd.split(" ")]

        if self.runner != CondaRunner.CONDA and cmd == "search":
            _command.insert(1, "repoquery")
        if cmd in ("install", "remove", "create", "env remove"):
            _command.append("-y")
        if cmd in ("install", "create") or (cmd == "search" and self.runner == CondaRunner.MICROMAMBA):
            _command.append("--strict-channel-priority")
        if self.runner == CondaRunner.CONDA and self.solver == CondaSolver.MAMBA and cmd in ("create", "install"):
            _command.extend(["--solver", CondaSolver.MAMBA.value])
        return _command
