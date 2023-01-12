from typing import Any, Iterable, Mapping

from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet

from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.requirements import CondaRequirement


class CondaRepository(BaseRepository):
    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        if isinstance(candidate, CondaCandidate):
            return (
                candidate.dependencies,
                PySpecSet(candidate.requires_python),
                candidate.summary,
            )
        return super().get_dependencies(candidate)


class PyPICondaRepository(CondaRepository, PyPIRepository):
    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        if isinstance(requirement, CondaRequirement):
            from pdm_conda.plugin import conda_search

            return conda_search(requirement, self.environment.project)
        return super()._find_candidates(requirement)


class LockedCondaRepository(CondaRepository, LockedRepository):
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
                [d.as_line() for d in can.dependencies],
                package.get("requires_python", ""),
                "",
            )

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        if isinstance(candidate, CondaCandidate):
            return candidate.identify(), candidate.version, None, False
        return super()._identify_candidate(candidate)
