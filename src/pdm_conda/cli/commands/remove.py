from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.remove import Command as BaseCommand

from pdm_conda.cli.utils import remove_quotes
from pdm_conda.models.requirements import parse_requirement
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "remove"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.group is None:
            options.group = "dev" if options.dev else "default"

        project = cast(CondaProject, project)
        conda_dependencies = project.get_conda_pyproject_dependencies(options.group, options.dev)
        dependencies, _ = project.use_pyproject_dependencies(options.group, options.dev)
        _dependencies = [parse_requirement(d).conda_name for d in dependencies]
        # add conda dependencies to common dependencies if going to remove it
        for i, pkg in enumerate(options.packages):
            # parse it as conda, if found add it to dependencies
            conda_package = f"conda:{remove_quotes(pkg)}"
            package = parse_requirement(conda_package)
            idx = None
            for dep_idx, dep in enumerate(conda_dependencies):
                dep = parse_requirement(f"conda:{dep}")
                if package.name == dep.name:
                    if package.name not in _dependencies:
                        dependencies.append(conda_package)
                    options.packages[i] = conda_package
                    idx = dep_idx
                    break
            if idx is not None:
                conda_dependencies.pop(idx)
        super().handle(project, options)
