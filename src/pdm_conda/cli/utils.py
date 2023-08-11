from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement

if TYPE_CHECKING:
    from pdm.project import Project

    from pdm_conda.models.candidates import Candidate
    from pdm_conda.models.requirements import Requirement

_patched = False


def remove_quotes(req: str) -> str:
    for quote in ("'", '"'):
        if req.startswith(quote) and req.endswith(quote):
            req = req[1:-1]
    return req


def wrap_save_version_specifiers(func):
    @functools.wraps(func)
    def wrapper(
        requirements: dict[str, dict[str, Requirement]],
        resolved: dict[str, Candidate],
        save_strategy: str,
    ) -> None:
        func(requirements, resolved, save_strategy)
        for reqs in requirements.values():
            for name in reqs:
                if isinstance(can := resolved[name], CondaCandidate):
                    req = as_conda_requirement(reqs[name])
                    req.version_mapping.update(can.req.version_mapping)
                    req.is_python_package = can.req.is_python_package
                    reqs[name] = req

    return wrapper


def wrap_format_lockfile(func):
    @functools.wraps(func)
    def wrapper(
        project: Project,
        mapping: dict[str, Candidate],
        fetched_dependencies: dict[tuple[str, str | None], list[Requirement]],
        *args,
        **kwargs,
    ) -> dict:
        res = func(project, mapping, fetched_dependencies, *args, **kwargs)
        conda_corrections = dict()
        for name, can in mapping.items():
            corrections = dict()
            if isinstance(can, CondaCandidate):
                corrections["files"] = [{"url": item["url"], "hash": item["hash"]} for item in can.hashes]

            dependencies = []
            include_dependencies = False
            for dep in fetched_dependencies[(can.name, can.version)]:
                kwargs = {}
                if isinstance(dep, CondaRequirement):
                    kwargs["with_build_string"] = True
                    include_dependencies = True
                dependencies.append(dep.as_line(**kwargs))
            if include_dependencies:
                corrections["dependencies"] = dependencies
            if corrections:
                conda_corrections[name] = corrections
        for package in res["package"]:
            package.update(conda_corrections.get(package["name"], {}))
        return res

    return wrapper


if not _patched:
    from pdm.cli import actions, utils

    save_version_specifiers = wrap_save_version_specifiers(utils.save_version_specifiers)
    format_lockfile = wrap_format_lockfile(utils.format_lockfile)
    for m in [utils, actions]:
        setattr(m, "save_version_specifiers", save_version_specifiers)
        setattr(m, "format_lockfile", format_lockfile)
    _patched = True
