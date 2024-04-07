from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from pdm.formats.base import array_of_inline_tables, make_array

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.repositories import CondaRepository
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pdm.project import Project

    from pdm_conda.models.candidates import Candidate
    from pdm_conda.models.requirements import Requirement

_patched = False


def remove_quotes(req: str) -> str:
    for quote in ("'", '"'):
        if req.startswith(quote) and req.endswith(quote):
            req = req[1:-1]
    return req


def wrap_fetch_hashes(func):
    @functools.wraps(func)
    def wrapper(repository, mapping: Mapping[str, Candidate]) -> None:
        conda_candidates = {}
        if isinstance(repository, CondaRepository):
            conda_candidates = {name: can for name, can in mapping.items() if isinstance(can, CondaCandidate)}
            repository.update_hashes(conda_candidates)

        return func(repository, {name: can for name, can in mapping.items() if name not in conda_candidates})

    return wrapper


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
        # ensure no duplicated groups in metadata
        if groups := res.get("metadata", {}).get("groups"):
            res["metadata"]["groups"] = list({group: None for group in groups}.keys())

        assert len(res["package"]) == len(mapping)
        # fix conda packages
        for package, (_, can) in zip(res["package"], sorted(mapping.items()), strict=False):
            # only static-url allowed for conda packages
            if isinstance(can, CondaCandidate):
                package["files"] = array_of_inline_tables(
                    [{"url": item["url"], "hash": item["hash"]} for item in can.hashes],
                    multiline=True,
                )

            # fix conda dependencies to include build string
            dependencies = []
            include_dependencies = False
            for dep in fetched_dependencies.get(can.dep_key, []):
                kwargs = {}
                if isinstance(dep, CondaRequirement):
                    kwargs["with_build_string"] = True
                    include_dependencies = True
                dependencies.append(dep.as_line(**kwargs))
            if include_dependencies:
                package["dependencies"] = make_array(sorted(set(dependencies)), True)

        res["package"] = sorted(res["package"], key=lambda x: x["name"])
        return res

    return wrapper


if not _patched:
    from pdm.cli import actions, utils

    save_version_specifiers = wrap_save_version_specifiers(utils.save_version_specifiers)
    format_lockfile = wrap_format_lockfile(utils.format_lockfile)
    wrap_fetch_hashes = wrap_fetch_hashes(actions.fetch_hashes)
    for m in [utils, actions]:
        m.save_version_specifiers = save_version_specifiers
        m.format_lockfile = format_lockfile
        m.fetch_hashes = wrap_fetch_hashes
    _patched = True
