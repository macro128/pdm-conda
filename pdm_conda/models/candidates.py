from importlib.metadata import Distribution
from pathlib import Path
from typing import Any, cast

from pdm.models.candidates import Candidate, PreparedCandidate
from pdm.models.candidates import make_candidate as _make_candidate
from pdm.models.environment import Environment
from unearth import Link

from pdm_conda.models.requirements import CondaRequirement, Requirement

_patched = False


class CondaPreparedCandidate(PreparedCandidate):
    def __init__(self, candidate: Candidate, environment: Environment) -> None:
        super().__init__(candidate, environment)
        self.candidate = cast(CondaCandidate, self.candidate)  # type: ignore
        self.req = cast(CondaRequirement, self.req)  # type: ignore

    def get_dependencies_from_metadata(self) -> list[str]:
        # if conda candidate return already obtained dependencies
        if not isinstance(self.req, CondaRequirement) or self.req.package is None:
            raise ValueError("Uninitialized conda requirement")
        return self.req.package.full_dependencies

    def prepare_metadata(self) -> Distribution:
        # if conda candidate get setup from package
        if not isinstance(self.req, CondaRequirement) or self.req.package is None:
            raise ValueError("Uninitialized conda requirement")
        return self.req.package.distribution

    def should_cache(self) -> bool:
        return False


class CondaCandidate(Candidate):
    def __init__(self, req: Requirement, name: str | None = None, version: str | None = None, link: Link | None = None):
        super().__init__(req, name, version, link)
        # extract hash from link
        if link and link.hash is not None:
            self.hashes = {link: link.hash}
        self._req = cast(CondaRequirement, req)  # type: ignore
        self._preferred = None
        self._prepared: CondaPreparedCandidate | None = None

    @property
    def req(self):
        return self._req

    @req.setter
    def req(self, value):
        if isinstance(value, CondaRequirement):
            self._req = value

    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        result = super().as_lockfile_entry(project_root)
        result["conda_managed"] = True
        if self.req.channel is not None:
            result["channel"] = self.req.channel
        if self.link is None:
            raise ValueError("Uninitialized conda requirement")
        result["url"] = self.link.url
        if self.link.comes_from is not None:
            result["channel_url"] = self.link.comes_from
        return result

    def prepare(self, environment: Environment) -> CondaPreparedCandidate:
        """Prepare the candidate for installation."""
        if self._prepared is None:
            self._prepared = CondaPreparedCandidate(self, environment)
        return self._prepared

    @classmethod
    def from_conda_requirement(cls, req: CondaRequirement) -> "CondaCandidate":
        """
        Create conda candidate from conda requirement.
        :param req: conda requirement
        :return: conda candidate
        """
        version: str | None
        if req.package is not None:
            version = req.package.version
        else:
            version = list(req.specifier)[0].version if req.specifier else None
        return CondaCandidate(req, name=req.name, version=version, link=req.link)


def make_candidate(
    req: Requirement,
    name: str | None = None,
    version: str | None = None,
    link: Link | None = None,
) -> Candidate:
    """Construct a candidate and cache it in memory"""
    # if conda requirement make conda candidate
    if isinstance(req, CondaRequirement):
        return CondaCandidate.from_conda_requirement(req)
    return _make_candidate(req, name, version, link)


if not _patched:
    from pdm.models import repositories
    from pdm.resolver import providers

    setattr(providers, "make_candidate", make_candidate)
    setattr(repositories, "make_candidate", make_candidate)
    _patched = True
