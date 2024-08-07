from __future__ import annotations

from typing import TYPE_CHECKING

from pdm import termui

if TYPE_CHECKING:
    from pdm.core import Core

logger = termui.logger
__version__ = "0.18.3"


def main(core: Core):
    from pdm_conda import hooks, utils
    from pdm_conda.cli import utils as cli_utils
    from pdm_conda.cli.commands.add import Command as AddCommand
    from pdm_conda.cli.commands.init import Command as InitCommand
    from pdm_conda.cli.commands.install import Command as InstallCommand
    from pdm_conda.cli.commands.list import Command as ListCommand
    from pdm_conda.cli.commands.lock import Command as LockCommand
    from pdm_conda.cli.commands.remove import Command as RemoveCommand
    from pdm_conda.cli.commands.update import Command as UpdateCommand
    from pdm_conda.cli.commands.use import Command as UseCommand
    from pdm_conda.cli.commands.venv import Command as VenvCommand
    from pdm_conda.cli.commands.venv import backends
    from pdm_conda.cli.commands.venv import utils as venv_utils
    from pdm_conda.environments import python
    from pdm_conda.models.config import CONFIGS
    from pdm_conda.project import CondaProject
    from pdm_conda.resolver import graph

    core.project_class = CondaProject

    for cmd in [
        AddCommand,
        InitCommand,
        InstallCommand,
        ListCommand,
        LockCommand,
        RemoveCommand,
        VenvCommand,
        UpdateCommand,
        UseCommand,
    ]:
        core.register_command(cmd)

    for name, config in CONFIGS:
        core.add_config(name, config)
