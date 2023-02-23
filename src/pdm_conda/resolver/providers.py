from typing import Iterator, Sequence

from pdm._types import Comparable
from pdm.models.candidates import Candidate
from pdm.resolver.providers import BaseProvider, EagerUpdateProvider, ReusePinProvider
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


class CondaReusePinProvider(ReusePinProvider, CondaBaseProvider):
    pass


class CondaEagerUpdateProvider(EagerUpdateProvider, CondaBaseProvider):
    pass
