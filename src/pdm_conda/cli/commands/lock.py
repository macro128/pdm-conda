from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.lock import Command as BaseCommand
from pdm.project.lockfile import FLAG_CROSS_PLATFORM

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
            # conda doesn't produce cross-platform locks
            options.strategy_change = [
                s for s in (options.strategy_change or []) if not s.replace("-", "_").endswith(FLAG_CROSS_PLATFORM)
            ] + [
                f"no_{FLAG_CROSS_PLATFORM}",
            ]
            if options.groups and ":all" in options.groups:
                options.groups += list(project.iter_groups(dev=True if options.dev is None else options.dev))
        super().handle(project=project, options=options)
