from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.venv.create import CreateCommand as BaseCommand

from pdm_conda.models.config import CondaRunner

if TYPE_CHECKING:
    import argparse
    from pdm.project import Project


class CreateCommand(BaseCommand):
    description = BaseCommand.__doc__

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "-cn",
            "--conda-name",
            help="Specify the name of the Conda environment, overrides --name and appended hash",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if conda_project := ((backend := (options.backend or project.config["venv.backend"])) in list(CondaRunner)):
            from pdm_conda.project import CondaProject

            project = cast(CondaProject, project)
            project.conda_config.runner = backend
            project.conda_config.is_initialized = True
            if options.conda_name:
                options.name = f"conda:{options.conda_name}"

        super().handle(project, options)

        # if inside a project ensure saving conda runner
        if conda_project:
            if project.pyproject.exists():
                project.pyproject.write(show_message=False)
