import uuid
from copy import copy
from typing import Any, Iterable, Mapping, cast

from pdm._types import Source
from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver.python import PythonRequirement

from pdm_conda.conda import conda_create, sort_candidates
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
        self._conda_resolution: dict[str, list[CondaCandidate]] = dict()

    def _uses_conda(self, requirement: Requirement) -> bool:
        """
        True if requirement is conda requirement or (not excluded and named requirement
        and conda as default manager or used by another conda requirement)
        :param requirement: requirement to evaluate
        """
        if not isinstance(self.environment, CondaEnvironment):
            return False
        conda_config = self.environment.project.conda_config
        return isinstance(requirement, (CondaRequirement, PythonRequirement)) or (
            isinstance(requirement, NamedRequirement)
            and conda_config.as_default_manager
            and requirement.name not in conda_config.excludes
        )

    def update_conda_resolution(
        self,
        requirements: list[Requirement] | None = None,
        resolution: dict | None = None,
    ) -> list[CondaRequirement]:
        """
        Updates the existing conda resolution if new requirements.
        :param requirements: list of requirements
        :param resolution: resolution to override existing
        :return: list of changed requirements
        """
        if resolution is not None:
            self._conda_resolution = resolution
        return []

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


class PyPICondaRepository(PyPIRepository, CondaRepository):
    def update_conda_resolution(
        self,
        requirements: list[Requirement] | None = None,
        resolution: dict | None = None,
    ) -> list[CondaRequirement]:
        super().update_conda_resolution(requirements, resolution)
        changed = []
        requirements = requirements or []
        requirements = [as_conda_requirement(req) for req in requirements if self._uses_conda(req)]
        update = False
        # if any requirement not in saved candidates or incompatible candidates
        for req in requirements:
            if update:
                break
            key = req.identify()
            if key not in self._conda_resolution:
                update = True
                break
            for can in self._conda_resolution[key]:
                if not req.is_compatible(can):
                    update = True
                    break

        if update:
            resolution = conda_create(
                self.environment.project,
                requirements,
                prefix=f"/tmp/{uuid.uuid4()}",
                dry_run=True,
            )
            _requirements = {r.conda_name: r for r in requirements}
            for name, candidates in resolution.items():
                req = _requirements.get(name, candidates[0].req)
                key = req.identify()
                cans = self._conda_resolution.get(key, [])
                # add non-existing candidates
                if any(True for can in candidates if can not in cans):
                    # add requirement to changed if didn't exist
                    if key in self._conda_resolution:
                        changed.append(req)
                    self._conda_resolution[key] = candidates

        return changed

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        if self._uses_conda(requirement):
            requirement = as_conda_requirement(requirement)
            candidates = self._conda_resolution.get(requirement.identify(), [])
            candidates = [copy(c) for c in candidates if requirement.is_compatible(c)]
            candidates = list(sort_candidates(self.environment.project, candidates))
            for can in candidates:
                can.req = requirement
        else:
            candidates = super()._find_candidates(requirement)
        return candidates


class LockedCondaRepository(LockedRepository, CondaRepository):
    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        packages = lockfile.get("package", [])
        conda_packages = [copy(p) for p in packages if p.get("conda_managed", False)]
        packages = [p for p in packages if not p.get("conda_managed", False)]
        super()._read_lockfile({"package": packages, "metadata": lockfile.get("metadata", {})})

        for package in conda_packages:
            link, _hash = list(self.file_hashes[(package["name"], package["version"])].items())[0]
            name, value = _hash.split(":", maxsplit=1)
            package[name] = value
            package["url"] = link.url_without_fragment
            can = CondaCandidate.from_lock_package(package)
            can_id = self._identify_candidate(can)
            self.packages[can_id] = can
            self.candidate_info[can_id] = (
                can.dependencies_lines,
                package.get("requires_python", ""),
                package.get("summary", ""),
            )

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        if isinstance(candidate, CondaCandidate):
            return candidate.identify(), candidate.version, None, False
        return super()._identify_candidate(candidate)
