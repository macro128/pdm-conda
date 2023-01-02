import functools
from pathlib import Path
from typing import Any

from pdm.models.candidates import Candidate, PreparedCandidate
from pdm.models.requirements import Requirement
from unearth import Link


class CondaCandidate(Candidate):
    def __init__(
        self,
        req: Requirement,
        name: str | None = None,
        version: str | None = None,
        link: Link | None = None,
    ):
        super().__init__(req, name, version, link)
        # extract hash from link
        if link:
            k, v = list(link.hashes.items())[0]
            self.hashes = {link: f"{k}:{v}"}

    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        result = super().as_lockfile_entry(project_root)
        result["conda_managed"] = True
        if self.req.channel is not None:
            result["channel"] = self.req.channel
        return result


def wrap_get_dependencies_from_metadata(func):
    @functools.wraps(func)
    def wrapper(self):
        # if conda candidate get already obtained dependencies
        if isinstance(self.candidate, CondaCandidate):
            return self.req.package.dependencies

        return func(self)

    return wrapper


def wrap_prepare_metadata(func):
    @functools.wraps(func)
    def wrapper(self):
        # if conda candidate get setup from package
        if isinstance(self.candidate, CondaCandidate):
            return self.candidate.req.package.distribution

        return func(self)

    return wrapper


def wrap_should_cache(func):
    @functools.wraps(func)
    def wrapper(self):
        # if conda candidate don't cache it
        if isinstance(self.candidate, CondaCandidate):
            return False

        return func(self)

    return wrapper


if not hasattr(PreparedCandidate, "_patched"):
    setattr(PreparedCandidate, "_patched", True)
    PreparedCandidate.get_dependencies_from_metadata = (
        wrap_get_dependencies_from_metadata(
            PreparedCandidate.get_dependencies_from_metadata,
        )
    )
    PreparedCandidate.should_cache = wrap_should_cache(PreparedCandidate.should_cache)
    PreparedCandidate.prepare_metadata = wrap_prepare_metadata(
        PreparedCandidate.prepare_metadata,
    )
