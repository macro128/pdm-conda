from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.init import Command as BaseCommand
from pdm.cli.options import ArgumentGroup

from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "init"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        conda_group = ArgumentGroup("Conda Options")
        conda_group.add_argument(
            "-cr",
            "--runner",
            dest="conda_runner",
            type=str,
            help="Specify Conda runner executable",
            default="",
        )
        conda_group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        config = project.conda_config
        if runner := options.conda_runner:
            config.runner = runner
            config.is_initialized = True

        super().handle(project, options)
        if runner:
            config.runner = runner
            project.pyproject.write(show_message=False)
