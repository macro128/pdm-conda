from typing import Callable, Iterator, Mapping, Sequence

from pdm._types import Comparable
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.resolver.providers import BaseProvider, EagerUpdateProvider, ReusePinProvider
from pdm.resolver.python import find_python_matches
from resolvelib.resolvers import RequirementInformation

from pdm_conda.models.requirements import CondaRequirement


class CondaBaseProvider(BaseProvider):
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
            reqs = sorted(requirements[identifier], key=self.requirement_preference)
            # iterates over requirements
            candidates = []
            for req in reqs:
                candidates = self._find_candidates(req)
                candidates = [
                    can for can in candidates if can not in incompat and all(self.is_satisfied_by(r, can) for r in reqs)
                ]
                if candidates:
                    break
            return iter(candidates)

        return matches_gen


class CondaReusePinProvider(ReusePinProvider, CondaBaseProvider):
    pass


class CondaEagerUpdateProvider(EagerUpdateProvider, CondaBaseProvider):
    pass
