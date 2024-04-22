from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, cast

from pdm.models.repositories import BaseRepository
from pdm.models.requirements import strip_extras
from pdm.resolver.providers import (
    BaseProvider,
    EagerUpdateProvider,
    ReuseInstalledProvider,
    ReusePinProvider,
    register_provider,
)
from pdm.utils import is_url
from unearth.utils import LazySequence

from pdm_conda.conda import CondaResolutionError
from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.repositories import CondaRepository
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement, parse_requirement

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement
    from pdm.resolver.providers import Comparable
    from resolvelib.resolvers import RequirementInformation


@register_provider("all")
class CondaBaseProvider(BaseProvider):
    def __init__(
        self,
        repository: BaseRepository,
        allow_prereleases: bool | None = None,
        overrides: dict[str, str] | None = None,
        direct_minimal_versions: bool = False,
        locked_candidates: dict[str, Candidate] | None = None,
    ) -> None:
        super().__init__(repository, allow_prereleases, overrides, direct_minimal_versions, locked_candidates)
        self._overrides_requirements: dict | None = None
        environment = repository.environment
        self.is_conda_initialized = (
            isinstance(environment, CondaEnvironment) and environment.project.conda_config.is_initialized
        )
        if self.is_conda_initialized:
            self.excludes = {
                parse_requirement(name).identify()
                for name in environment.project.pyproject.resolution.get("excludes", [])
            }
        python_version = str(environment.interpreter.version)
        self.python_candidate = CondaCandidate(
            parse_requirement(f"conda:python=={python_version}"),
            "python",
            python_version,
        )

    @property
    def overrides_requirements(self) -> dict[str, Requirement]:
        """Identifier and requirement mapping for overrides.

        :return: mapping
        """
        if self._overrides_requirements is None:
            self._overrides_requirements = {}
            if self.overrides:
                for identifier, requested in self.overrides.items():
                    if is_url(requested):
                        requirement = parse_requirement(f"{identifier} @ {requested}")
                    else:
                        # first parse as conda to ensure no version error
                        requirement = cast(CondaRequirement, parse_requirement(f"conda:{identifier} {requested}"))
                        if not isinstance(self.repository, CondaRepository) or not self.repository.is_conda_managed(
                            requirement,
                        ):
                            requirement.name = identifier
                            requirement = parse_requirement(requirement.as_line())
                    self._overrides_requirements[self.identify(requirement)] = requirement

        return self._overrides_requirements

    def get_preference(
        self,
        identifier: str,
        resolutions: dict[str, Candidate],
        candidates: dict[str, Iterator[Candidate]],
        information: dict[str, Iterator[RequirementInformation]],
        backtrack_causes: Sequence[RequirementInformation],
    ) -> tuple[Comparable, ...]:
        preference = super().get_preference(identifier, resolutions, candidates, information, backtrack_causes)
        if self.is_conda_initialized:
            return (
                preference[:3],
                (
                    isinstance(self.repository, CondaRepository)
                    and self.repository.is_conda_managed(next(information[identifier]).requirement)
                ),
                *preference[3:],
            )
        return preference

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Callable[[], Iterator[Candidate]]:
        super_find_matches = super().find_matches(identifier, requirements, incompatibilities)
        if not self.is_conda_initialized:
            return super_find_matches

        def matches_gen() -> Iterator[Candidate]:
            incompat = list(incompatibilities[identifier])
            bare_name, extras = strip_extras(identifier)
            if identifier == "python" or any(name in self.overrides for name in (identifier, bare_name)):
                return super_find_matches()
            reqs = sorted(requirements[identifier], key=self.requirement_preference)
            if not reqs:
                return iter(())
            original_req = reqs[0]
            if extras and bare_name in requirements:
                # We should consider the requirements for both foo and foo[extra]
                reqs.extend(requirements[bare_name])
                reqs.sort(key=self.requirement_preference)
            # iterates over requirements
            candidates = []
            for req in reqs:
                candidates = self._find_candidates(req)
                candidates = LazySequence(
                    # In some cases we will use candidates from the bare requirement,
                    # this will miss the extra dependencies if any. So we associate the original
                    # requirement back with the candidate since it is used by `get_dependencies()`.
                    (
                        (
                            can.copy_with(original_req, merge_requirements=True)
                            if isinstance(can, CondaCandidate)
                            else can.copy_with(original_req)
                        )
                        if extras
                        else can
                    )
                    for can in candidates
                    if can not in incompat and all(self.is_satisfied_by(r, can) for r in reqs)
                )
                if candidates:
                    break
            return iter(candidates)

        return matches_gen

    def get_requirement_from_overrides(self, requirement: Requirement) -> Requirement:
        _req = copy(self.overrides_requirements.get(self.identify(requirement), requirement))
        if not requirement.groups:
            _req.groups = requirement.groups
        if isinstance(requirement, CondaRequirement):
            _req = as_conda_requirement(_req)
        return _req

    def get_override_candidates(self, identifier: str) -> Iterable[Candidate]:
        if self.is_conda_initialized:
            return self._find_candidates(self.overrides_requirements[identifier])
        return super().get_override_candidates(identifier)

    def compatible_with_resolution(
        self,
        requirements: list[Requirement],
        resolution: dict,
        excluded_identifiers: set[str],
    ) -> bool:
        """True if all requirements are compatible with the resolution.

        :param requirements: list of requirements
        :param resolution: resolution to check
        :param excluded_identifiers: identifiers to exclude
        :return: True if all requirements are compatible with the resolution
        """
        return self.repository.compatible_with_resolution(
            [self.get_requirement_from_overrides(req) for req in requirements],
            resolution,
            excluded_identifiers,
        )

    def update_conda_resolution(
        self,
        new_requirements: list[Requirement] | None = None,
        requirements: list[Requirement] | None = None,
        resolution: dict | None = None,
        excluded_identifiers: set[str] | None = None,
    ) -> set[str]:
        """Updates the existing conda resolution if new requirements.

        :param new_requirements: new requirements to add
        :param requirements: list of requirements
        :param resolution: resolution to override existing
        :param excluded_identifiers: identifiers to exclude
        :return: list of excluded identifiers
        """
        return self.repository.update_conda_resolution(
            [self.get_requirement_from_overrides(req) for req in new_requirements] if new_requirements else None,
            [self.get_requirement_from_overrides(req) for req in requirements] if requirements else None,
            resolution,
            excluded_identifiers,
        )


@register_provider("reuse")
class CondaReusePinProvider(ReusePinProvider, CondaBaseProvider):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for name in self.tracked_names:
            self.locked_candidates.pop(name, None)

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Callable[[], Iterator[Candidate]]:
        super_find = super(CondaBaseProvider, self).find_matches(identifier, requirements, incompatibilities)

        def matches_gen() -> Iterator[Candidate]:
            requested_req = next(filter(lambda r: r.is_named, requirements[identifier]), None)
            pin = self.get_reuse_candidate(identifier, requested_req)
            if pin is not None:
                incompat = list(incompatibilities[identifier])
                pin._preferred = True  # type: ignore[attr-defined]
                if pin not in incompat and all(self.is_satisfied_by(r, pin) for r in requirements[identifier]):
                    yield pin
            yield from super_find()

        return matches_gen

    def _merge_requirements(
        self,
        requirements: list[Requirement] | None,
        excluded=None,
        include_all: bool = False,
    ) -> list[Requirement]:
        _requirements = []
        excluded = set(excluded or set())
        requirements = requirements or []
        for req in requirements:
            ident = self.identify(req)
            if (
                self.repository.is_conda_managed(req, excluded)
                and ident in self.locked_candidates
                and as_conda_requirement(req).is_compatible(can := self.locked_candidates[ident])
            ):
                _requirements.append(can.req)
            else:
                _requirements.append(req)
            excluded.add(ident)
        if include_all:
            for can in self.locked_candidates.values():
                if self.identify(can.req) not in excluded:
                    _requirements.append(can.req)

        return _requirements

    def update_conda_resolution(
        self,
        new_requirements: list[Requirement] | None = None,
        requirements: list[Requirement] | None = None,
        resolution: dict | None = None,
        excluded_identifiers: set[str] | None = None,
    ) -> set[str]:
        """Updates the existing conda resolution if new requirements, keeping the pinned versions if possible.

        :param new_requirements: new requirements to add
        :param requirements: list of requirements
        :param resolution: resolution to override existing
        :param excluded_identifiers: identifiers to exclude
        :return: list of excluded identifiers
        """
        # try to reuse the pinned versions
        new_requirements = new_requirements or []
        excluded_identifiers = excluded_identifiers or set()
        try:
            return super().update_conda_resolution(
                self._merge_requirements(new_requirements, excluded_identifiers),
                self._merge_requirements(
                    requirements,
                    excluded_identifiers | {req.key for req in new_requirements},
                    include_all=True,
                ),
                resolution,
                excluded_identifiers,
            )
        except CondaResolutionError:
            return super().update_conda_resolution(
                new_requirements,
                requirements,
                resolution,
                excluded_identifiers,
            )


@register_provider("eager")
class CondaEagerUpdateProvider(EagerUpdateProvider, CondaBaseProvider):
    pass


@register_provider("reuse-installed")
class CondaReuseInstalledProvider(ReuseInstalledProvider, CondaBaseProvider):
    pass
