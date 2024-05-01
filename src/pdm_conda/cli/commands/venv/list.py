from __future__ import annotations

from typing import cast, TYPE_CHECKING

from pdm.cli.commands.venv.list import ListCommand as BaseCommand

from pdm_conda.cli.utils import ensure_logger

if TYPE_CHECKING:
    import argparse
    from pdm.project import Project


class ListCommand(BaseCommand):
    description = BaseCommand.__doc__

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        with ensure_logger(project, "venv_list"):
            super().handle(project, options)
