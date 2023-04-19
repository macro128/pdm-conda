from dataclasses import dataclass, field

from resolvelib.resolvers import (
    RequirementInformation,
    Resolution,
    Resolver,
    _build_result,
)

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.environment import CondaEnvironment
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement

CONSTRAINS_KEY = "___constrains___"
CONDA_RESOLUTION_KEY = "___conda_resolution___"


@dataclass
class State:
    mapping: dict
    criteria: dict
    backtrack_causes: list
    constrains: dict = field(default_factory=dict)
    conda_resolution: dict = field(default_factory=dict)


class CondaResolution(Resolution):
    def __init__(
        self,
        *args,
        base_constrains: dict | None = None,
        conda_resolution: dict | None = None,
        is_conda_environment: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._is_conda_environment = is_conda_environment
        self._base_constrains = base_constrains or dict()
        self._conda_resolution = conda_resolution or dict()

    @property
    def state(self):
        if self._states and not isinstance(state := self._states[-1], State):
            self._states[-1] = State(
                state.mapping,
                state.criteria,
                state.backtrack_causes,
                self._base_constrains,
                self._conda_resolution,
            )
        return super().state

    def _push_new_state(self):
        base = self.state
        base.constrains = base.criteria.pop(CONSTRAINS_KEY, base.constrains)
        base.conda_resolution = base.criteria.pop(CONDA_RESOLUTION_KEY, base.conda_resolution)
        state = State(
            mapping=base.mapping.copy(),
            criteria=base.criteria.copy(),
            backtrack_causes=base.backtrack_causes[:],
            constrains=base.constrains.copy(),
            conda_resolution=base.conda_resolution.copy(),
        )
        # update repository conda resolution to latest
        if self._is_conda_environment:
            self._p.repository.update_conda_resolution(resolution=state.conda_resolution)
        self._states.append(state)

    def _remove_information_from_criteria(self, criteria, parents):
        state = self.state
        state.constrains = state.criteria.pop(CONSTRAINS_KEY, state.constrains)
        state.conda_resolution = state.criteria.pop(CONDA_RESOLUTION_KEY, state.conda_resolution)
        super()._remove_information_from_criteria(criteria, parents)

    def _ensure_criteria(self, criteria):
        # save temporarily constrains and conda_resolution in criteria
        for k, v in [(CONDA_RESOLUTION_KEY, self.state.conda_resolution), (CONSTRAINS_KEY, self.state.constrains)]:
            if k not in criteria:
                criteria[k] = v.copy()

    def update_constrains(self, candidate: CondaCandidate, criteria=None, merge_old: bool | set[str] = True):
        if isinstance(merge_old, bool):
            if merge_old:
                merge_old = set(candidate.constrains.keys())
            else:
                merge_old = set()
        if criteria is not None:
            self._ensure_criteria(criteria)
            constrains = criteria[CONSTRAINS_KEY]
        else:
            constrains = self._base_constrains

        for identifier, constrain in candidate.constrains.items():
            if identifier != "python":
                # keep most restrictive constrain
                if identifier in merge_old and (existing_constrain := constrains.get(identifier, None)) is not None:
                    constrain = existing_constrain.merge(constrain)
                constrains[identifier] = constrain
                if criteria is not None and identifier in criteria:
                    # todo msg
                    self._add_to_criteria(criteria, constrain, parent=candidate)

    def _update_conda_resolution(self, criteria, parent) -> bool:
        requirements = [
            criterion.information[-1].requirement
            for i, criterion in criteria.items()
            if i not in (CONDA_RESOLUTION_KEY, CONSTRAINS_KEY) and criterion.information
        ]
        if parent is not None:
            requirements.extend(self._p.get_dependencies(candidate=parent))
        self._ensure_criteria(criteria)
        changed = self._p.repository.update_conda_resolution(requirements, criteria[CONDA_RESOLUTION_KEY])
        for req in changed:
            self._add_to_criteria(criteria, req, parent)
            identifier = self._p.identify(requirement_or_candidate=req)
            criterion = criteria.get(identifier)
            _constrains: set[str] = set()
            for can in criterion.candidates:
                if isinstance(can, CondaCandidate):
                    self.update_constrains(can, merge_old=_constrains)
                    _constrains.update(can.constrains.keys())
        return bool(changed)

    def _add_to_criteria(self, criteria, requirement, parent):
        _req = requirement
        if self._is_conda_environment:
            # merge with constrain if exists
            self._ensure_criteria(criteria)
            constrains = criteria[CONSTRAINS_KEY]
            if (constrain := constrains.get(requirement.conda_name, None)) is not None:
                _req = constrain.merge(requirement)

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
            if self._update_conda_resolution(criteria, parent):
                self._add_to_criteria(criteria, _req, parent)
        super()._add_to_criteria(criteria, _req, parent)

    def _get_updated_criteria(self, candidate):
        criteria = super()._get_updated_criteria(candidate)
        # merge with previous constrain if exists
        if isinstance(candidate, CondaCandidate) and self._is_conda_environment:
            self.update_constrains(candidate, criteria)
        return criteria

    def initialize_conda_resolution(self, requirements):
        # update conda resolution
        self._p.repository.update_conda_resolution(list(requirements), self._conda_resolution)
        # update constrains
        for candidates in self._conda_resolution.values():
            for can in candidates:
                self.update_constrains(candidate=can)


class CondaResolver(Resolver):
    def resolve(self, requirements, max_rounds=100):
        is_conda_environment = isinstance(self.provider.repository.environment, CondaEnvironment)
        resolution = CondaResolution(self.provider, self.reporter, is_conda_environment=is_conda_environment)
        if is_conda_environment:
            resolution.initialize_conda_resolution(requirements)
        else:
            assert not any(isinstance(r, CondaRequirement) for r in requirements)

        state = resolution.resolve(requirements, max_rounds=max_rounds)
        return _build_result(state)
