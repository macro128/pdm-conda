from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.lock import Command as BaseCommand

from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "lock"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        if project.conda_config.is_initialized:
            # conda don't produce cross-platform locks
            options.cross_platform = False
        if options.groups:
            if ":all" in options.groups:
                options.groups += list(project.iter_groups())
        super().handle(project=project, options=options)
