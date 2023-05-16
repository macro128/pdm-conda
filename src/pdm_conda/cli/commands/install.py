import argparse
from typing import cast

from pdm.cli.commands.install import Command as BaseCommand

from pdm_conda.project import CondaProject, Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "install"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        if options.groups:
            if ":all" in options.groups:
                options.groups += list(project.iter_groups())
        super().handle(project, options)
