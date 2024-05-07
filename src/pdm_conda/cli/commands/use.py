from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from pdm.cli.commands.use import Command as BaseCommand
from pdm.utils import is_conda_base

from pdm_conda.cli.utils import ensure_logger
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "use"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        conda_base = is_conda_base()
        conda_default_env = ""
        if project.conda_config.is_initialized and conda_base:
            conda_default_env = os.environ.pop("CONDA_DEFAULT_ENV", "")
        try:
            with ensure_logger(project, "use"):
                super().handle(project, options)
        finally:
            if project.conda_config.is_initialized and conda_base:
                os.environ["CONDA_DEFAULT_ENV"] = conda_default_env
