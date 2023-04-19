import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any

from pdm.exceptions import ProjectError
from pdm.project import ConfigItem, Project

from pdm_conda.mapping import DOWNLOAD_DIR_ENV_VAR


class CondaRunner(str, Enum):
    CONDA = "conda"
    MAMBA = "mamba"
    MICROMAMBA = "micromamba"


class CondaSolver(str, Enum):
    CONDA = "conda"
    MAMBA = "libmamba"


_CONFIG_MAP = {"pypi-mapping.download-dir": "mapping_download_dir"}
_CONFIG_MAP |= {v: k for k, v in _CONFIG_MAP.items()}

CONFIGS = [
    ("runner", ConfigItem("Conda runner executable", CondaRunner.CONDA.value, env_var="CONDA_RUNNER")),
    ("solver", ConfigItem("Solver to use for Conda resolution", CondaSolver.CONDA.value, env_var="CONDA_SOLVER")),
    ("channels", ConfigItem("Conda channels to use")),
    (
        "as-default-manager",
        ConfigItem("Use Conda to install all possible requirements", False, env_var="CONDA_AS_DEFAULT_MANAGER"),
    ),
    (
        "batched-commands",
        ConfigItem("Execute batched install and remove commands", False, env_var="CONDA_BATCHED_COMMANDS"),
    ),
    (
        "installation-method",
        ConfigItem(
            "Whether to use hard-link or copy when installing",
            "hard-link",
            env_var="CONDA_INSTALLATION_METHOD",
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
    runner: str = CondaRunner.CONDA
    solver: str = CondaSolver.CONDA
    as_default_manager: bool = False
    batched_commands: bool = False
    installation_method: str = "hard-link"
    excludes: list[str] = field(default_factory=list, repr=False)
    dependencies: list[str] = field(default_factory=list, repr=False)
    optional_dependencies: dict[str, list] = field(default_factory=dict)
    dev_dependencies: dict[str, list] = field(default_factory=dict)
    mapping_download_dir: Path = field(repr=False, default=Path())

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
        self._set_project_config = True
        if self.is_initialized:
            config = self._project.project_config
            config["python.use_venv"] = True
            config["python.use_pyenv"] = False
            config["venv.backend"] = self.runner
            if (venv_location := os.getenv("VIRTUAL_ENV", os.getenv("CONDA_PREFIX", None))) is not None:
                self._project.global_config["venv.location"] = str(Path(venv_location).parent)
                os.environ["PDM_IGNORE_SAVED_PYTHON"] = "true"

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
        config = {k: v for k, v in project.pyproject.settings.get("conda", {}).items()}
        kwargs["_initialized"] = is_conda_config_initialized(project)
        for n, c in CONFIGS:
            n = n[len("conda.") :]
            if (prop_name := _CONFIG_MAP.get(n, n)) not in config and c.env_var:
                value = project.config[f"conda.{n}"]
                if prop_name == "mapping_download_dir":
                    value = Path(value)
                elif prop_name in ("as-default-manager", "batched-commands"):
                    value = str(value).lower() in ("true", "1")
                config[prop_name] = value
        config = {k.replace("-", "_"): v for k, v in config.items()}
        return PluginConfig(_project=project, **(config | kwargs))

    def command(self, cmd="install"):
        """
        Get runner command args
        :param cmd: command, install by default
        :return: args list
        """
        _command = [self.runner, *cmd.split(" ")]
        if self.runner != CondaRunner.CONDA and cmd == "search":
            _command.insert(1, "repoquery")

        if cmd in ("install", "remove", "create"):
            _command.append("-y")
        if cmd in ("install", "create") or (cmd == "search" and self.runner == CondaRunner.MICROMAMBA):
            _command.append("--strict-channel-priority")
        if self.runner == CondaRunner.CONDA and self.solver == CondaSolver.MAMBA and cmd in ("create", "install"):
            _command.extend(["--solver", self.solver])
        return _command
