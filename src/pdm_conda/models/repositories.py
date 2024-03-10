from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from pdm import termui
from pdm.exceptions import CandidateNotFound
from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.specifiers import PySpecSet

from pdm_conda import logger
from pdm_conda.conda import (
    CondaResolutionError,
    CondaSearchError,
    conda_create,
    conda_search,
    sort_candidates,
)
from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement

if TYPE_CHECKING:
    from typing import Any, Iterable, Mapping

    from pdm.models.repositories import CandidateKey, RepositoryConfig

    from pdm_conda.environments import BaseEnvironment
    from pdm_conda.models.candidates import Candidate, FileHash
    from pdm_conda.models.requirements import Requirement


def _format_packages(packages: list[str], pretty_print=False) -> str:
    result = ""
    for i, package in enumerate(packages):
        result += f"[success]{package}[/success]" if pretty_print else package
        if i < len(packages) - 1:
            if i == len(packages) - 2:
                result += " and "
            else:
                result += ", "
    return result


class CondaRepository(BaseRepository):
    def __init__(
        self,
        sources: list[RepositoryConfig],
        environment: BaseEnvironment,
        ignore_compatibility: bool = True,
    ) -> None:
        super().__init__(sources, environment, ignore_compatibility)
        self.environment = cast(CondaEnvironment, environment)
        self._conda_resolution: dict[str, list[CondaCandidate]] = dict()
        self._compatible_requirements: set[CondaRequirement] = set()
        self._excluded_identifiers: set[str] = set()

    def is_conda_managed(self, requirement: Requirement, excluded_identifiers: set[str] | None = None) -> bool:
        """
        True if requirement is conda requirement or (not excluded and named requirement
        and conda as default manager or used by another conda requirement)

        :param requirement: requirement to evaluate
        :param excluded_identifiers: identifiers to exclude
        """
        if not isinstance(self.environment, CondaEnvironment):
            return False
        from pdm_conda.models.requirements import is_conda_managed as _is_conda_managed

        return _is_conda_managed(requirement, self.environment.project.conda_config, excluded_identifiers)

    def update_conda_resolution(
        self,
        requirements: list[Requirement] | None = None,
        resolution: dict | None = None,
        excluded_identifiers: set[str] | None = None,
    ) -> set[str]:
        """
        Updates the existing conda resolution if new requirements.

        :param requirements: list of requirements
        :param resolution: resolution to override existing
        :param excluded_identifiers: identifiers to exclude
        :return: list of excluded identifiers
        """
        if resolution is not None:
            self._conda_resolution = resolution
        if excluded_identifiers is not None:
            self._excluded_identifiers = excluded_identifiers
        return self._excluded_identifiers

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

    def get_hashes(self, candidate: Candidate) -> list[FileHash]:
        if isinstance(candidate, CondaCandidate):
            if not candidate.hashes:
                termui.logger.info("Fetching hashes for %s", candidate)
                _candidates = conda_search(self.environment.project, candidate.req)
                if not _candidates:
                    raise CondaSearchError(f"Cannot find hashes for {candidate}")

                candidate.hashes = _candidates[0].hashes
        return super().get_hashes(candidate)


class PyPICondaRepository(PyPIRepository, CondaRepository):
    def update_conda_resolution(
        self,
        requirements: list[Requirement] | None = None,
        resolution: dict | None = None,
        excluded_identifiers: set[str] | None = None,
    ) -> set[str]:
        excluded_identifiers = super().update_conda_resolution(requirements, resolution, excluded_identifiers)
        requirements = requirements or []
        requirements = [
            as_conda_requirement(req) for req in requirements if self.is_conda_managed(req, excluded_identifiers)
        ]
        update = False
        if requirements_to_test := (set(requirements) - self._compatible_requirements):
            # if any requirement not in saved candidates or incompatible candidates
            for req in requirements_to_test:
                if update:
                    break
                key = req.conda_name
                if key not in self._conda_resolution:
                    update = True
                    break
                for can in self._conda_resolution[key]:
                    if not req.is_compatible(can):
                        update = True
                        break
                self._compatible_requirements.add(req)

        if update:
            try:
                resolution = conda_create(
                    self.environment.project,
                    requirements,
                    prefix=f"/tmp/{uuid.uuid4()}",
                    dry_run=True,
                )
                _requirements = {r.conda_name: r for r in requirements}
                for name, candidates in resolution.items():
                    req = _requirements.get(name, candidates[0].req)
                    key = req.conda_name
                    self._conda_resolution[key] = candidates
                self._compatible_requirements = set(requirements)
            except CondaResolutionError as err:
                logger.info(err)
                if err.packages:
                    if self.environment.project.conda_config.auto_excludes:
                        logger.info(f"Adding {_format_packages(err.packages)} to excludes list")
                        return self.update_conda_resolution(
                            requirements,
                            resolution,
                            excluded_identifiers | set(err.packages),
                        )

                    raise CandidateNotFound(
                        f"Unable to find candidates for {_format_packages(err.packages, pretty_print=True)} "
                        f"with Conda.\n"
                        f"You should add more channels or add the packages to the excludes list.",
                    )
                raise
        return excluded_identifiers

    def _find_candidates(self, requirement: Requirement, minimal_version: bool) -> Iterable[Candidate]:
        if self.is_conda_managed(requirement, excluded_identifiers=self._excluded_identifiers):
            requirement = as_conda_requirement(requirement)
            candidates = self._conda_resolution.get(requirement.conda_name, [])
            candidates = [
                c.copy_with(requirement, merge_requirements=True) for c in candidates if requirement.is_compatible(c)
            ]
            candidates = list(sort_candidates(self.environment.project, candidates, minimal_version))
        else:
            if isinstance(requirement, CondaRequirement):
                requirement = requirement.as_named_requirement()
            candidates = super()._find_candidates(requirement, minimal_version)
        return candidates


class LockedCondaRepository(LockedRepository, CondaRepository):
    def _matching_keys(self, requirement: Requirement) -> Iterable[CandidateKey]:
        yield from super()._matching_keys(requirement)
        if self.is_conda_managed(requirement):
            req_id = as_conda_requirement(requirement).identify()

            for key, can in self.packages.items():
                if isinstance(can, CondaCandidate) and req_id == key[0]:
                    yield key

    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        packages = lockfile.get("package", [])
        conda_packages = []
        pypi_packages = []
        for package in packages:
            if package.get("conda_managed", False):
                conda_packages.append(package)
            else:
                pypi_packages.append(package)
        super()._read_lockfile({"package": pypi_packages, **{k: v for k, v in lockfile.items() if k != "package"}})

        for package in conda_packages:
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
