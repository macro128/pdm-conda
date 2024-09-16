from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterable
from typing import TYPE_CHECKING

from pdm.cli import actions, utils
from pdm.models.specifiers import get_specifier

from pdm_conda import logger
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.repositories import CondaRepository
from pdm_conda.models.requirements import as_conda_requirement, comparable_version

if TYPE_CHECKING:
    from pdm_conda.models.candidates import Candidate
    from pdm_conda.models.requirements import Requirement


@contextlib.contextmanager
def ensure_logger(project, logger_name: str):
    if len(logger.handlers) == 1:
        with project.core.ui.logging(logger_name):
            yield
    else:
        yield


def remove_quotes(req: str) -> str:
    for quote in ("'", '"'):
        if req.startswith(quote) and req.endswith(quote):
            req = req[1:-1]
    return req


def wrap_fetch_hashes(func):
    @functools.wraps(func)
    def wrapper(repository, candidates: Iterable[Candidate]) -> None:
        conda_candidates = []
        python_candidates = []
        for can in candidates:
            if isinstance(can, CondaCandidate):
                conda_candidates.append(can)
            else:
                python_candidates.append(can)
        if isinstance(repository, CondaRepository):
            repository.update_hashes(conda_candidates)

        return func(repository, python_candidates)

    return wrapper


def wrap_save_version_specifiers(func):
    @functools.wraps(func)
    def wrapper(
        requirements: list[Requirement],
        resolved: dict[str, list[Candidate]],
        save_strategy: str,
    ) -> None:
        func(requirements, resolved, save_strategy)
        for i, r in enumerate(requirements):
            name = r.identify()
            candidates = resolved[name]
            if len(candidates) > 1:
                continue
            can = candidates[0]
            if save_strategy == "compatible" and r.is_named and (version := comparable_version(can.version)).epoch:
                if version.is_prerelease or version.is_devrelease:
                    r.specifier = get_specifier(
                        f">={version.epoch}!{version},<{version.epoch}!{version.major + 1}",
                    )
                else:
                    r.specifier = get_specifier(f"~={version.epoch}!{version.major}.{version.minor}")
            if isinstance(can, CondaCandidate):
                r = as_conda_requirement(r)
                r.version_mapping.update(can.req.version_mapping)
                r.is_python_package = can.req.is_python_package
                r.marker = can.req.marker
                requirements[i] = r

    return wrapper


save_version_specifiers = wrap_save_version_specifiers(utils.save_version_specifiers)
wrap_fetch_hashes = wrap_fetch_hashes(actions.fetch_hashes)
for m in [utils, actions]:
    m.save_version_specifiers = save_version_specifiers
    m.fetch_hashes = wrap_fetch_hashes
