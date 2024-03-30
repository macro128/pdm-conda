from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.add import Command as BaseCommand
from pdm.cli.options import ArgumentGroup, split_lists
from pdm.exceptions import RequirementError

from pdm_conda.cli.utils import remove_quotes
from pdm_conda.models.requirements import CondaRequirement, is_conda_managed, parse_requirement
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project

conda_group = ArgumentGroup("Conda Arguments")
conda_group.add_argument("--conda", dest="conda_packages", action="append", help="Specify Conda packages", default=[])

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
conda_group.add_argument(
    "--conda-as-default-manager",
    dest="conda_as_default_manager",
    default=False,
    action="store_true",
    help="Specify Conda as default manager",
)
conda_group.add_argument(
    "-ce",
    "--conda-excludes",
    dest="conda_excludes",
    metavar="PACKAGE",
    action=split_lists(","),
    default=[],
    help="Specify Conda excluded dependencies separated by comma, can be supplied multiple times",
)


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "add"
    arguments = (*BaseCommand.arguments, conda_group)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        config = project.conda_config
        if options.conda_runner:
            config.runner = options.conda_runner
        existing_channels = config.channels
        if (channel := options.conda_channel) and channel not in existing_channels:
            existing_channels.append(channel)
            config.channels = existing_channels
        if conda_excludes := options.conda_excludes:
            config.excludes = set(conda_excludes).union(config.excludes)
        if options.conda_as_default_manager:
            config.as_default_manager = True

        conda_packages = options.conda_packages
        for i, p in enumerate(conda_packages):
            if not p.startswith("conda:"):
                conda_packages[i] = f"conda:{remove_quotes(p)}"
        if config.as_default_manager:
            conda_packages += options.packages
            options.packages = []
        for package in conda_packages:
            package_channel = None
            package = remove_quotes(package)
            conda_package = package.startswith("conda:")

            if "::" in package:
                package_channel, package = package.split("conda:", maxsplit=1)[-1].split("::", maxsplit=1)
            _p = None

            try:
                _p = parse_requirement(package)
                if isinstance(_p, CondaRequirement):
                    _p = _p.as_named_requirement()
            except RequirementError:
                # if requirement error it can have an unparsable version
                pass

            # if not named we can't use Conda
            if conda_package or _p is None or is_conda_managed(_p, config):
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
