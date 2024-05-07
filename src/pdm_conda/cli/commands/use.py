from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from pdm.cli.commands.use import Command as BaseCommand
from pdm.models.python import PythonInfo
from pdm.utils import is_conda_base

from pdm_conda.cli.utils import ensure_logger
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "use"

    @staticmethod
    def select_python(
        project: Project,
        python: str,
        *,
        ignore_remembered: bool,
        ignore_requires_python: bool,
        venv: str | None,
        first: bool,
    ) -> PythonInfo:
        selected_python = BaseCommand.select_python(
            project,
            python,
            ignore_remembered=ignore_remembered,
            ignore_requires_python=ignore_requires_python,
            venv=venv,
            first=first,
        )
        conda_base = is_conda_base()
        project = cast(CondaProject, project)
        if conda_base and project.conda_config.is_initialized:
            os.environ.pop("CONDA_DEFAULT_ENV", None)
        return selected_python

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        conda_base = is_conda_base()
        conda_default_env = os.environ.get("CONDA_DEFAULT_ENV", "")
        try:
            with ensure_logger(project, "use"):
                super().handle(project, options)
        finally:
            if project.conda_config.is_initialized and conda_base:
                os.environ["CONDA_DEFAULT_ENV"] = conda_default_env
