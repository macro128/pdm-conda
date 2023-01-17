import functools

from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.project import Project

from pdm_conda.models.requirements import CondaRequirement

_patched = False


def wrap_save_version_specifiers(func):
    @functools.wraps(func)
    def wrapper(
        requirements: dict[str, dict[str, Requirement]],
        resolved: dict[str, Candidate],
        save_strategy: str,
    ) -> None:
        func(requirements, resolved, save_strategy)
        for reqs in requirements.values():
            for name, r in reqs.items():
                if isinstance(r, CondaRequirement):
                    r.version_mapping = resolved[name].req.version_mapping
                    r.is_python_package = resolved[name].req.is_python_package

    return wrapper


def wrap_format_lockfile(func):
    @functools.wraps(func)
    def wrapper(
        project: Project,
        mapping: dict[str, Candidate],
        fetched_dependencies: dict[tuple[str, str | None], list[Requirement]],
    ) -> dict:
        for deps in fetched_dependencies.values():
            for i, dep in enumerate(deps):
                if isinstance(dep, CondaRequirement):
                    setattr(dep, "as_line", functools.partial(dep.as_line, with_build_string=True))
        res = func(project, mapping, fetched_dependencies)
        for deps in fetched_dependencies.values():
            for i, dep in enumerate(deps):
                if isinstance(dep, CondaRequirement):
                    setattr(dep, "as_line", dep.as_line.func)  # type: ignore
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
