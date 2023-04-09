from copy import copy
from dataclasses import dataclass, field

from packaging.version import Version
from resolvelib.resolvers import _build_result  # type: ignore
from resolvelib.resolvers import RequirementInformation, Resolution, Resolver

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.environment import CondaEnvironment
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement


@dataclass
class State:
    mapping: dict
    criteria: dict
    backtrack_causes: list
    constrains: dict = field(default_factory=dict)


class CondaResolution(Resolution):
    def __init__(self, *args, base_constrains: dict | None, is_conda_environment: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._is_conda_environment = is_conda_environment
        self._base_constrains = base_constrains or dict()

    @property
    def state(self):
        if self._states and not isinstance(state := self._states[-1], State):
            self._states[-1] = State(state.mapping, state.criteria, state.backtrack_causes, self._base_constrains)
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
        _req = requirement
        if self._is_conda_environment:
            constrains = self.state.constrains
            if (constrain := constrains.get(requirement.conda_name, None)) is not None:
                _req = copy(constrain)
                _req.specifier &= requirement.specifier
                _req.version_mapping.update(getattr(requirement, "version_mapping", dict()))
                if isinstance(requirement, CondaRequirement):
                    _req.channel = requirement.channel
            identifier = self._p.identify(_req)
            if criterion := criteria.get(identifier):
                excluded = self._p.repository.environment.project.conda_config.excludes
                if isinstance(_req, CondaRequirement):
                    # if conda requirement but other not conda requirement and excluded
                    # then transform to named requirement
                    if any(
                        not isinstance(i.requirement, CondaRequirement) and i.requirement.name in excluded
                        for i in criterion.information
                    ):
                        _req = _req.as_named_requirement()
                    # else any other to conda
                    else:
                        criterion.information = [
                            RequirementInformation(as_conda_requirement(i.requirement), i.parent)
                            for i in criterion.information
                        ]

                # if excluded then delete conda related information else if other conda requirement transform to conda
                else:
                    if requirement.name in excluded:
                        criterion.information = [
                            RequirementInformation(i.requirement.as_named_requirement(), i.parent)
                            if isinstance(
                                i.requirement,
                                CondaRequirement,
                            )
                            else i
                            for i in criterion.information
                        ]
                    elif any(isinstance(i.requirement, CondaRequirement) for i in criterion.information):
                        _req = as_conda_requirement(requirement)
        super()._add_to_criteria(criteria, _req, parent)

    def _get_updated_criteria(self, candidate):
        criteria = super()._get_updated_criteria(candidate)
        # update previous constrain if exists
        if isinstance(candidate, CondaCandidate) and self._is_conda_environment:
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
        base_constrains = dict()

        if is_conda_environment := isinstance(environment := self.provider.repository.environment, CondaEnvironment):
            # add installed python constrains
            if (can := environment.python_candidate) is not None:
                base_constrains |= can.constrains
                base_constrains |= {d.conda_name: d for d in can.dependencies}
        else:
            assert not any(isinstance(r, CondaRequirement) for r in requirements)

        resolution = CondaResolution(
            self.provider,
            self.reporter,
            base_constrains=base_constrains,
            is_conda_environment=is_conda_environment,
        )
        state = resolution.resolve(requirements, max_rounds=max_rounds)
        return _build_result(state)
