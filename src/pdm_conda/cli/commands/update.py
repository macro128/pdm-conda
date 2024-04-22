from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.cli.commands.update import Command as BaseCommand
from pdm.models.specifiers import get_specifier

from pdm_conda.models.requirements import CondaRequirement
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    import argparse

    from pdm_conda.project import Project


class Command(BaseCommand):
    description = BaseCommand.__doc__
    name = "update"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        super().handle(project=project, options=options)
        project = cast(CondaProject, project)
        if (
            project.conda_config.is_initialized
            and project.conda_config.custom_behavior
            and not options.dry_run
            and options.save_strategy
        ):
            groups = set(project.iter_groups(dev=False))
            dev_groups = set(project.iter_groups(dev=True)) - groups
            candidates = project.locked_repository.all_candidates
            requirements = {}
            for i, group in enumerate(groups | dev_groups):
                group_requirements = {}
                for identifier, req in project.get_dependencies(group).items():
                    can = candidates.get(identifier, None)
                    if can is None:
                        continue
                    updated_req = can.req

                    if req.is_named:
                        version = next(s.version for s in updated_req.specifier)
                        if options.save_strategy == "minimum":
                            req.specifier = get_specifier(f">={version}")
                        elif options.save_strategy == "compatible":
                            req.specifier = get_specifier(f"~={version}")
                        elif options.save_strategy == "exact":
                            req.specifier = get_specifier(f"=={version}")
                        if isinstance(req, CondaRequirement) and isinstance(updated_req, CondaRequirement):
                            req.is_python_package = updated_req.is_python_package

                        group_requirements[identifier] = req
                    elif options.save_strategy == "exact":
                        group_requirements[identifier] = updated_req
                if group_requirements:
                    requirements[(group, i >= len(groups))] = group_requirements

            num_groups = len(requirements)
            for i, ((group, is_dev), group_requirements) in enumerate(requirements.items()):
                project.add_dependencies(
                    group_requirements,
                    to_group=group,
                    dev=is_dev,
                    show_message=i == num_groups - 1,
                )
