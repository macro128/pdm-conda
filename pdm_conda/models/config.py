from dataclasses import dataclass, field

from pdm.exceptions import ProjectError
from pdm.project import ConfigItem, Project


@dataclass
class PluginConfig:
    channels: list[str] = field(default_factory=list)
    runner: str = "conda"
    as_default_manager: bool = False
    dependencies: list[str] = field(default_factory=list, repr=False)
    optional_dependencies: dict[str, list] = field(default_factory=dict)
    dev_dependencies: dict[str, list] = field(default_factory=dict)
    _initialized: bool = field(repr=False, default=False)

    def __post_init__(self):
        if not self.channels:
            self.channels = ["defaults"]
        if self.runner not in ["conda", "micromamba", "mamba"]:
            raise ProjectError(f"Invalid Conda runner: {self.runner}")

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
        kwargs["_initialized"] = "conda" in project.pyproject.settings
        return PluginConfig(**(config | kwargs))

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

    @classmethod
    def configs(cls):
        _configs = [
            ("runner", ConfigItem("Conda runner executable", "conda")),
            ("channels", ConfigItem("Conda channels to use", ["defaults"])),
            ("as_default_manager", ConfigItem("Use Conda to install all possible requirements", False)),
            ("dependencies", ConfigItem("Dependencies to install with Conda", [])),
            ("optional-dependencies", ConfigItem("Optional dependencies to install with Conda", [])),
            ("dev-dependencies", ConfigItem("Development dependencies to install with Conda", [])),
        ]
        return [(f"conda.{name}", config) for name, config in _configs]
