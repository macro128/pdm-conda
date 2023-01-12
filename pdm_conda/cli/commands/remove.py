import argparse
from typing import cast

from pdm.cli.commands.remove import Command as BaseCommand
from pdm.project import Project

from pdm_conda.models.requirements import parse_requirement


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "remove"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm_conda.project import CondaProject

        if options.group is None:
            options.group = "dev" if options.dev else "default"

        project = cast(CondaProject, project)
        conda_dependencies = project.get_conda_pyproject_dependencies(options.group, options.dev)
        dependencies, _ = project.get_pyproject_dependencies(options.group, options.dev)
        # add conda dependencies to common dependencies if going to remove it
        for i in range(len(options.packages)):
            # parse it as conda, if found add it to dependencies
            conda_package = f"conda:{options.packages[i]}"
            package = parse_requirement(conda_package)
            idx = None
            for dep_idx, dep in enumerate(conda_dependencies):
                if package.name in dep:
                    if package.name not in dependencies:
                        options.packages[i] = conda_package
                    else:
                        options.packages.append(conda_package)
                    dependencies.append(f"conda:{dep}")
                    idx = dep_idx
                    break
            if idx is not None:
                conda_dependencies.pop(idx)
        super().handle(project, options)
