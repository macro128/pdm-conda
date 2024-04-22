from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.install import Command as BaseCommand

from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "install"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        if options.groups and ":all" in options.groups:
            options.groups += list(project.iter_groups())
        super().handle(project, options)
