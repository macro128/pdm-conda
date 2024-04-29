from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from pdm.resolver import core, graph
from pdm.resolver.graph import _identify_parent

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement
    from resolvelib.resolvers import Result


def wrapper_populate_groups(func):
    @functools.wraps(func)
    def wrapper(result: Result[Requirement, Candidate, str]) -> None:
        """Correct groups for cyclic dependencies."""

        func(result)
        for k, can in reversed(result.mapping.items()):
            groups = set(can.req.groups)
            for _, parent in result.criteria[k].information:
                if (
                    parent is not None
                    and (parent_can := result.mapping.get(_identify_parent(parent), None)) is not None
                ):
                    groups.update(parent_can.req.groups)
            can.req.groups = sorted(groups)

    return wrapper


populate_groups = wrapper_populate_groups(graph.populate_groups)

for module in (graph, core):
    module.populate_groups = populate_groups
