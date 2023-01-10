import argparse

from pdm.cli.commands.add import Command as BaseCommand
from pdm.cli.options import ArgumentGroup
from pdm.project import Project

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
        channel = options.conda_channel
        confs = project.pyproject.settings.setdefault("conda", dict())
        if options.conda_runner:
            confs["runner"] = options.conda_runner
        existing_channels = confs.setdefault("channels", [])
        conda_packages = options.conda_packages

        for package in conda_packages:
            if package.startswith("conda:"):
                package = package[len("conda:") :]
            package_channel = None
            if "::" not in package:
                if channel:
                    package_channel = channel
                    package = f"{channel}::{package}"
            else:
                package_channel, _ = package.split("::", maxsplit=1)
            if package_channel and package_channel not in existing_channels:
                project.core.ui.echo(f"Detected Conda channel {package_channel}, adding it to pyproject")
                existing_channels.append(package_channel)
            package = f"conda:{package}"
            options.packages.append(package)

        super().handle(project, options)
