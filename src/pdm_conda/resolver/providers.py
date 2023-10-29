from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, cast

from pdm.models.repositories import BaseRepository
from pdm.models.requirements import strip_extras
from pdm.resolver.providers import BaseProvider, EagerUpdateProvider, ReusePinProvider
from pdm.resolver.python import find_python_matches
from pdm.utils import is_url
from unearth.utils import LazySequence

from pdm_conda.models.repositories import CondaRepository
from pdm_conda.models.requirements import (
    CondaRequirement,
    as_conda_requirement,
    parse_requirement,
)

if TYPE_CHECKING:
    from typing import Callable, Iterable, Iterator, Mapping, Sequence

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement
    from pdm.resolver.providers import Comparable
    from resolvelib.resolvers import RequirementInformation


class CondaBaseProvider(BaseProvider):
    def __init__(
        self,
        repository: BaseRepository,
        allow_prereleases: bool | None = None,
        overrides: dict[str, str] | None = None,
        direct_minimal_versions: bool = False,
    ) -> None:
        super().__init__(repository, allow_prereleases, overrides, direct_minimal_versions)
        self._overrides_requirements: dict | None = None

    @property
    def overrides_requirements(self) -> dict[str, Requirement]:
        """
        Identifier and requirement mapping for overrides
        :return: mapping
        """
        if self._overrides_requirements is None:
            self._overrides_requirements = dict()
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
        return (
            *preference[:3],
            not any(isinstance(i.requirement, CondaRequirement) for i in information[identifier]),
            *preference[3:],
        )

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Callable[[], Iterator[Candidate]]:
        def matches_gen() -> Iterator[Candidate]:
            incompat = list(incompatibilities[identifier])
            if identifier == "python":
                candidates = find_python_matches(identifier, requirements)
                return (c for c in candidates if c not in incompat)
            elif identifier in self.overrides:
                return iter(self.get_override_candidates(identifier))
            reqs_iter = requirements[identifier]
            bare_name, extras = strip_extras(identifier)
            if extras and bare_name in requirements:
                # We should consider the requirements for both foo and foo[extra]
                reqs_iter = itertools.chain(reqs_iter, requirements[bare_name])
            reqs = sorted(reqs_iter, key=self.requirement_preference)
            # iterates over requirements
            candidates = []
            for req in reqs:
                candidates = self._find_candidates(req)
                candidates = LazySequence(
                    can for can in candidates if can not in incompat and all(self.is_satisfied_by(r, can) for r in reqs)
                )
                if candidates:
                    break
            return iter(candidates)

        return matches_gen

    def get_requirement_from_overrides(self, requirement: Requirement) -> Requirement:
        _req = self.overrides_requirements.get(self.identify(requirement), requirement)
        if isinstance(requirement, CondaRequirement):
            _req = as_conda_requirement(_req)
        return _req

    def get_override_candidates(self, identifier: str) -> Iterable[Candidate]:
        return self._find_candidates(self.overrides_requirements[identifier])


class CondaReusePinProvider(ReusePinProvider, CondaBaseProvider):
    pass


class CondaEagerUpdateProvider(EagerUpdateProvider, CondaBaseProvider):
    pass
