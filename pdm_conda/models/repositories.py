from typing import Any, Iterable, Mapping, cast

from pdm._types import Source
from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from unearth import Link

from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.environment import CondaEnvironment, Environment
from pdm_conda.models.requirements import CondaRequirement
from pdm_conda.plugin import conda_search


class CondaRepository(BaseRepository):
    def __init__(self, sources: list[Source], environment: Environment, ignore_compatibility: bool = True) -> None:
        super().__init__(sources, environment, ignore_compatibility)
        self.environment = cast(CondaEnvironment, environment)

    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        if isinstance(candidate, CondaCandidate):
            return (
                candidate.dependencies,
                PySpecSet(candidate.requires_python),
                candidate.summary,
            )
        return super().get_dependencies(candidate)

    def get_hashes(self, candidate: Candidate) -> dict[Link, str] | None:
        if isinstance(candidate, CondaCandidate):
            return None
        return super().get_hashes(candidate)


class PyPICondaRepository(PyPIRepository, CondaRepository):
    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        if isinstance(requirement, CondaRequirement):
            candidates = conda_search(requirement, self.environment.project)
        else:
            candidates = super()._find_candidates(requirement)
        if (req := self.environment.python_requirements.get(requirement.conda_name, None)) is not None:
            candidates = [c for c in candidates if req.specifier.contains(c.version)]
        return candidates


class LockedCondaRepository(LockedRepository, CondaRepository):
    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        packages = lockfile.get("package", [])
        conda_packages = [p for p in packages if p.get("conda_managed", False)]
        packages = [p for p in packages if not p.get("conda_managed", False)]
        super()._read_lockfile({"package": packages})

        for package in conda_packages:
            can = CondaCandidate.from_lock_package(package)
            can_id = self._identify_candidate(can)
            self.packages[can_id] = can
            self.candidate_info[can_id] = (
                [d.as_line(as_conda=True, with_build_string=True) for d in can.dependencies],
                package.get("requires_python", ""),
                "",
            )

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        if isinstance(candidate, CondaCandidate):
            return candidate.identify(), candidate.version, None, False
        return super()._identify_candidate(candidate)
