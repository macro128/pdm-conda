from __future__ import annotations

from typing import cast, TYPE_CHECKING

from pdm.cli.commands.venv.create import CreateCommand as BaseCommand
from pdm.cli.options import ArgumentGroup, split_lists

from pdm_conda.models.config import CondaRunner

if TYPE_CHECKING:
    import argparse
    from pdm.project import Project


class CreateCommand(BaseCommand):
    description = BaseCommand.__doc__

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        conda_group = ArgumentGroup("Conda Options")
        conda_group.add_argument(
            "-c",
            "--channel",
            dest="conda_channels",
            metavar="CHANNEL",
            action=split_lists(","),
            help="Specify Conda channels separated by comma, can be supplied multiple times",
            default=[],
        )
        conda_group.add_argument(
            "-cn",
            "--conda-name",
            help="Specify the name of the Conda environment, overrides --name and appended hash",
        )
        conda_group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm_conda.project import CondaProject

        default_backend = project.config["venv.backend"]
        project = cast(CondaProject, project)
        conda_config = project.conda_config
        backend = options.backend or default_backend
        if conda_config.is_initialized and backend == default_backend and conda_config.custom_behavior:
            backend = options.backend = conda_config.runner

        overridden_configs = {}
        if conda_project := (backend in list(CondaRunner)):
            overridden_configs["is_initialized"] = True
            overridden_configs["runner"] = backend
            conda_config.runner = backend
            conda_config.is_initialized = True
            if options.conda_name:
                options.name = f"conda:{options.conda_name}"
            channels = options.conda_channels
            for channel in channels:
                if channel not in conda_config.channels:
                    conda_config.channels.append(channel)
            overridden_configs["channels"] = conda_config.channels

        conda_config.check_active(super().handle)(project, options)

        # if inside a project ensure saving conda runner
        if conda_project and project.pyproject.exists():
            with conda_config.write_project_config():
                for key, value in overridden_configs.items():
                    setattr(conda_config, key, value)
