from copy import copy
from dataclasses import dataclass, field

from packaging.version import Version
from resolvelib.resolvers import Resolution, Resolver, _build_result  # type: ignore

from pdm_conda.models.candidates import CondaCandidate


@dataclass
class State:
    mapping: dict
    criteria: dict
    backtrack_causes: list
    constrains: dict = field(default_factory=dict)


class CondaResolution(Resolution):
    @property
    def state(self):
        if self._states and not isinstance(state := self._states[-1], State):
            self._states[-1] = State(state.mapping, state.criteria, state.backtrack_causes)
        return super().state

    def _push_new_state(self):
        base = self.state
        state = State(
            mapping=base.mapping.copy(),
            criteria=base.criteria.copy(),
            backtrack_causes=base.backtrack_causes[:],
            constrains=base.constrains.copy(),
        )
        self._states.append(state)

    def _add_to_criteria(self, criteria, requirement, parent):
        constrains = self.state.constrains
        _req = requirement
        if (constrain := constrains.get(requirement.conda_name, None)) is not None:
            _req = copy(constrain)
            _req.specifier &= requirement.specifier
        super()._add_to_criteria(criteria, _req, parent)

    def _get_updated_criteria(self, candidate):
        criteria = super()._get_updated_criteria(candidate)
        if isinstance(candidate, CondaCandidate):
            self.state.constrains.update(candidate.constrains)
            for identifier, constrain in candidate.constrains.items():
                if identifier != "python":
                    # keep most restrictive constrain
                    if (existing_constrain := self.state.constrains.get(identifier, None)) is not None and all(
                        Version(s.version) < Version(e.version)
                        for e in existing_constrain.specifier
                        for s in constrain.specifier
                    ):
                        constrain = existing_constrain
                    self.state.constrains[identifier] = constrain
                    if identifier in criteria:
                        self._add_to_criteria(criteria, constrain, parent=candidate)

        return criteria


class CondaResolver(Resolver):
    def resolve(self, requirements, max_rounds=100):
        resolution = CondaResolution(self.provider, self.reporter)
        state = resolution.resolve(requirements, max_rounds=max_rounds)
        return _build_result(state)
