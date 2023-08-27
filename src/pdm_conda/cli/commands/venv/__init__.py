from __future__ import annotations

import argparse

from pdm.cli.commands.venv import Command as BaseCommand
from pdm_conda.cli.commands.venv.create import CreateCommand

# from pdm_conda.cli.commands.venv.list import ListCommand


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "venv"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        subparser = parser._actions[-1]
        CreateCommand.register_to(subparser, "create")
        # ListCommand.register_to(subparser, "list")
