import functools

from pdm.models.repositories import BaseRepository
from pdm.models.specifiers import PySpecSet

from pdm_conda.models.candidates import Candidate, CondaCandidate


def wrap_get_dependencies(func):
    @functools.wraps(func)
    def wrapper(self, candidate: Candidate):
        if isinstance(candidate, CondaCandidate):
            return (
                candidate.req.package.dependencies,
                PySpecSet(candidate.requires_python),
                candidate.summary,
            )

        return func(self, candidate)

    return wrapper


if not hasattr(BaseRepository, "_patched"):
    setattr(BaseRepository, "_patched", True)
    BaseRepository.get_dependencies = wrap_get_dependencies(
        BaseRepository.get_dependencies,
    )
