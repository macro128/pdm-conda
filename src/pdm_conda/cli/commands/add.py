import argparse
from typing import cast

from pdm.cli.commands.add import Command as BaseCommand
from pdm.cli.options import ArgumentGroup
from pdm.exceptions import RequirementError

from pdm_conda.cli.utils import remove_quotes
from pdm_conda.models.requirements import CondaRequirement, parse_requirement
from pdm_conda.project import CondaProject, Project

conda_group = ArgumentGroup("Conda Arguments")
conda_group.add_argument(
    "--conda",
    dest="conda_packages",
    action="append",
    help="Specify Conda packages",
    default=[],
)

conda_group.add_argument(
    "-c",
    "--channel",
    dest="conda_channel",
    type=str,
    help="Specify Conda channel",
    default="",
)

conda_group.add_argument(
    "-r",
    "--runner",
    dest="conda_runner",
    type=str,
    help="Specify Conda runner executable",
    default="",
)


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "add"
    arguments = BaseCommand.arguments + [conda_group]

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        config = project.conda_config

        if conda_packages := options.conda_packages:
            channel = options.conda_channel

            existing_channels = config.channels
            if options.conda_runner:
                config.runner = options.conda_runner
            if channel and channel not in existing_channels:
                existing_channels.append(channel)
                config.channels = existing_channels

            for package in conda_packages:
                package_channel = None
                package = remove_quotes(package)

                if "::" in package:
                    package_channel, package = package.split("conda:", maxsplit=1)[-1].split("::", maxsplit=1)

                try:
                    _p = parse_requirement(package)
                    if isinstance(_p, CondaRequirement):
                        _p = _p.as_named_requirement()
                except RequirementError:
                    # if requirement error it can have an unparsable version
                    _p = None

                # if not named we can't use Conda
                if _p is None or (_p.is_named and _p.name not in config.excludes):
                    if package.startswith("conda:"):
                        package = package[len("conda:") :]
                    if not package_channel and channel:
                        package_channel = channel

                    if package_channel:
                        package = f"{package_channel}::{package}"
                        if package_channel not in existing_channels:
                            project.core.ui.echo(f"Detected Conda channel {package_channel}, adding it to pyproject")
                            existing_channels.append(package_channel)
                            config.channels = existing_channels

                    package = f"conda:{package}"

                options.packages.append(package)

        super().handle(project, options)
