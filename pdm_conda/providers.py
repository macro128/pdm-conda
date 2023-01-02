import functools
from typing import Iterator, Mapping

from pdm.resolver.providers import BaseProvider

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import CondaRequirement, Requirement


def wrap_find_matches(func):
    @functools.wraps(func)
    def wrapper(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        *args,
        **kwargs
    ):
        req = next(requirements.get(identifier, []), None)  # type: ignore
        if isinstance(req, CondaRequirement):
            return [
                CondaCandidate(
                    req,
                    name=req.name,
                    version=list(req.specifier)[0].version if req.specifier else None,
                    link=req.link,
                ),
            ]
        return func(
            self, identifier=identifier, requirements=requirements, *args, **kwargs
        )

    return wrapper


if not hasattr(BaseProvider, "_patched"):
    setattr(BaseProvider, "_patched", True)
    BaseProvider.find_matches = wrap_find_matches(BaseProvider.find_matches)
