from __future__ import annotations

from typing import TYPE_CHECKING

from pdm.cli.commands.list import Command as BaseCommand

from pdm_conda.cli.utils import ensure_logger
from pdm_conda.models.config import PluginConfig

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "list"

    @PluginConfig.check_active
    def handle(self, project: Project, options: argparse.Namespace) -> None:
        with ensure_logger(project, "list"):
            super().handle(project, options)
