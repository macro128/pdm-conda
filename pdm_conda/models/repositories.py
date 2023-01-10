from typing import Any, Mapping

from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from unearth import Link

from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.requirements import CondaPackage, CondaRequirement


class CondaRepository(BaseRepository):
    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        if isinstance(candidate, CondaCandidate):
            req = candidate.req
            if not isinstance(req, CondaRequirement) or req.package is None:
                raise ValueError(f"Uninitialized conda requirement {candidate}")
            return (
                req.package.dependencies,
                PySpecSet(candidate.requires_python),
                candidate.summary,
            )
        return super().get_dependencies(candidate)


class PyPICondaRepository(CondaRepository, PyPIRepository):
    pass


class LockedCondaRepository(CondaRepository, LockedRepository):
    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        self._locked_packages = dict()

        packages = lockfile.get("package", [])
        conda_packages = [p for p in packages if p.get("conda_managed", False)]
        packages = [p for p in packages if not p.get("conda_managed", False)]
        super()._read_lockfile({"package": packages})

        _conda_packages = dict()
        for package in conda_packages:
            requires_python = package.get("requires_python", None)
            _p = CondaPackage(
                name=package["name"],
                version=package["version"],
                link=Link(
                    package["url"],
                    comes_from=package.get("channel_url", None),
                    requires_python=requires_python,
                ),
                full_dependencies=package.get("dependencies", []),
                requires_python=requires_python,
            )
            _conda_packages[_p.name] = _p
            req = _p.req
            can = CondaCandidate.from_conda_requirement(req)
            can_id = self._identify_candidate(can)
            self.packages[can_id] = can
            self._locked_packages[can_id] = CondaCandidate.from_conda_requirement(req)
            self.candidate_info[can_id] = (_p.full_dependencies, _p.requires_python or "", "")
        for p in _conda_packages.values():
            p.load_dependencies(_conda_packages)

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        if isinstance(candidate, CondaCandidate):
            return candidate.identify(), None, None, False
        return super()._identify_candidate(candidate)

    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        if isinstance(candidate, CondaCandidate):
            can_id = self._identify_candidate(candidate)
            if (package := self._locked_packages.get(can_id, None)) is not None:
                for k in package.__slots__:
                    setattr(candidate, k, getattr(package, k))
        return super().get_dependencies(candidate)
