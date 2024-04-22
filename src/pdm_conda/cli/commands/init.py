from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.init import Command as BaseCommand
from pdm.cli.options import ArgumentGroup, split_lists

from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "init"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        conda_group = ArgumentGroup("Conda Options")
        conda_group.add_argument(
            "-cr",
            "--runner",
            dest="conda_runner",
            type=str,
            help="Specify Conda runner executable",
            default="",
        )
        conda_group.add_argument(
            "-c",
            "--channel",
            dest="conda_channels",
            metavar="CHANNEL",
            action=split_lists(","),
            help="Specify Conda channels separated by comma, can be supplied multiple times",
            default=[],
        )
        conda_group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        config = project.conda_config
        overridden_configs = {}
        if runner := options.conda_runner:
            overridden_configs["is_initialized"] = True
            config.runner = runner
            overridden_configs["runner"] = runner
            config.is_initialized = True
            channels = options.conda_channels
            for channel in channels:
                if channel not in config.channels:
                    config.channels.append(channel)
            overridden_configs["channels"] = config.channels

        super().handle(project, options)
        with config.write_project_config():
            for key, value in overridden_configs.items():
                setattr(config, key, value)
