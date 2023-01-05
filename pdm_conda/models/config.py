from dataclasses import dataclass, field

from pdm.exceptions import ProjectError
from pdm.project import ConfigItem, Project


@dataclass
class PluginConfig:
    channels: list[str] = field(default_factory=lambda: [])
    runner: str = "conda"
    dependencies: list[str] = field(default_factory=lambda: [], repr=False)
    optional_dependencies: dict[str, list] = field(default_factory=lambda: dict())
    dev_dependencies: dict[str, list] = field(default_factory=lambda: dict())

    def __post_init__(self):
        if self.runner not in ["conda", "micromamba", "mamba"]:
            raise ProjectError(f"Invalid Conda runner: {self.runner}")

    @classmethod
    def load_config(cls, project: Project, **kwargs) -> "PluginConfig":
        config = {
            k.replace("-", "_"): v
            for k, v in project.pyproject.settings.get("conda", {}).items()
        }
        return PluginConfig(**(config | kwargs))

    def command(self, cmd=None):
        cmd = cmd or "install"
        _command = [self.runner, cmd, "-y"]
        if cmd in ("install", "create"):
            _command.append("--strict-channel-priority")
        return _command

    @classmethod
    def configs(cls):
        _configs = [
            ("runner", ConfigItem("Conda runner executable", "conda")),
            ("channels", ConfigItem("Conda channels to use", ["defaults"])),
            ("dependencies", ConfigItem("Dependencies to install with Conda", [])),
            (
                "optional-dependencies",
                ConfigItem("Optional dependencies to install with Conda", []),
            ),
            (
                "dev-dependencies",
                ConfigItem("Development dependencies to install with Conda", []),
            ),
        ]
        return [(f"conda.{name}", config) for name, config in _configs]
