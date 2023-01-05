import functools
from typing import Iterator, Mapping

from pdm.models.candidates import Candidate
from pdm.resolver.providers import BaseProvider

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import CondaRequirement, Requirement

_patched = False


def wrap_find_matches(func):
    @functools.wraps(func)
    def wrapper(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ):
        req = next(requirements.get(identifier, []), None)  # type: ignore
        if isinstance(req, CondaRequirement):
            return lambda: [CondaCandidate.from_conda_requirement(req)]
        return func(self, identifier, requirements, incompatibilities)

    return wrapper


if not _patched:
    setattr(BaseProvider, "find_matches", wrap_find_matches(BaseProvider.find_matches))
    _patched = True
