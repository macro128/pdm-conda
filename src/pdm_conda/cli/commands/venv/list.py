from __future__ import annotations

from typing import TYPE_CHECKING, cast

import rich
from pdm.cli.commands.venv.list import ListCommand as BaseCommand
from pdm.exceptions import NoPythonVersion
from pdm.termui import _err_console

from pdm_conda.cli.commands.venv.utils import get_venv_prefix

if TYPE_CHECKING:
    import argparse
    from pdm.project import Project


class ListCommand(BaseCommand):
    description = BaseCommand.__doc__

    def _get_venvs(self, project, options, console):
        with console.capture() as capture:
            super().handle(project, options)
        return [venv for venv in capture.get().splitlines() if venv]

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        console = rich.get_console()
        venvs = self._get_venvs(project, options, console)

        # add conda venvs
        if project.conda_config.is_initialized and not project.conda_config.custom_behavior:
            conda_venvs = []
            try:
                with console.capture(), _err_console.capture():
                    project_interpreter = project.resolve_interpreter()
                if (venv := project_interpreter.get_venv()) and venv.is_conda:
                    venv_prefix = get_venv_prefix(project)
                    ident = venv.root.name
                    if venv_prefix in ident:
                        ident = ident[len(venv_prefix):]
                    conda_venvs.append(f"*  [success]{ident}[/]: {venv.root}")
            except NoPythonVersion:
                pass

            with project.conda_config.with_conda_venv_location() as (_, overriden):
                if overriden:
                    conda_venvs += self._get_venvs(project, options, console)

            for venv in conda_venvs:
                if venv not in venvs:
                    venvs.append(venv)

        for venv in venvs:
            project.core.ui.echo(venv)
