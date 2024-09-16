from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.lock import Command as BaseCommand

from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.config import PluginConfig
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "lock"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        target_group = parser.add_argument_group("Conda Lock Target")
        target_group.add_argument(
            "--cuda",
            help="The cuda version to lock for using conda. E.g. `11.6`, use `system` for using system cuda if available",
        )
        target_group.add_argument(
            "--system",
            help="The platform system version to lock for using conda. E.g. `0`, `5.10`. If not specified, will use system platform if available or some default",
        )
        target_group.add_argument(
            "--glibc",
            help="The glibc version to lock for using conda. E.g. `2.28`. If not specified, will use system platform if available or some default",
        )
        target_group.add_argument(
            "--archspec",
        )

    @PluginConfig.check_active
    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project = cast(CondaProject, project)
        if options.cuda or options.system or options.glibc or options.archspec:
            project.conda_config.is_initialized = True
            spec_overrides = {}

            for name in ("archspec", "cuda", "system", "glibc"):
                if (value := getattr(options, name, None)) is not None:
                    spec_overrides[name] = value

            if isinstance(project.environment, CondaEnvironment):
                # this will make sure lock is made with the right specs
                project.environment.allow_all_spec_overrides = spec_overrides

        if (
            project.conda_config.is_initialized
            and project.conda_config.custom_behavior
            and options.groups
            and ":all" in options.groups
        ):
            options.groups += list(project.iter_groups(dev=True if options.dev is None else options.dev))

        super().handle(project=project, options=options)
