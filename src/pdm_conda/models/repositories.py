from typing import Any, Iterable, Mapping, cast

from pdm._types import Source
from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from unearth import Link

from pdm_conda.conda import conda_search
from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.environment import CondaEnvironment, Environment
from pdm_conda.models.requirements import (
    CondaRequirement,
    NamedRequirement,
    as_conda_requirement,
)


class CondaRepository(BaseRepository):
    def __init__(self, sources: list[Source], environment: Environment, ignore_compatibility: bool = True) -> None:
        super().__init__(sources, environment, ignore_compatibility)
        self.environment = cast(CondaEnvironment, environment)

    def _uses_conda(self, requirement: Requirement) -> bool:
        """
        True if requirement is conda requirement or (not excluded and named requirement
        and conda as default manager or used by another conda requirement)
        :param requirement: requirement to evaluate
        """
        if not isinstance(self.environment, CondaEnvironment):
            return False
        conda_config = self.environment.project.conda_config
        return isinstance(requirement, CondaRequirement) or (
            isinstance(requirement, NamedRequirement)
            and conda_config.as_default_manager
            and requirement.name not in conda_config.excludes
        )

    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        if isinstance(candidate, CondaCandidate):
            dependencies = list(candidate.dependencies)
            # if dep in constrains use constrain
            if candidate.constrains:
                for i, dep in enumerate(dependencies):
                    if (constrain := candidate.constrains.get(dep.identify(), None)) is not None:
                        dependencies[i] = constrain
            requires_python = PySpecSet(candidate.requires_python)
            summary = candidate.summary
        else:
            dependencies, requires_python, summary = super().get_dependencies(candidate)
        return dependencies, requires_python, summary

    def get_hashes(self, candidate: Candidate) -> dict[Link, str] | None:
        if isinstance(candidate, CondaCandidate):
            return None
        return super().get_hashes(candidate)


class PyPICondaRepository(PyPIRepository, CondaRepository):
    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        if self._uses_conda(requirement):
            requirement = as_conda_requirement(requirement)
            candidates = conda_search(requirement, self.environment.project)
        else:
            candidates = super()._find_candidates(requirement)
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
            self.candidate_info[can_id] = (can.dependencies_lines, package.get("requires_python", ""), "")

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        if isinstance(candidate, CondaCandidate):
            return candidate.identify(), candidate.version, None, False
        return super()._identify_candidate(candidate)
