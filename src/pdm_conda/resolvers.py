from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from itertools import chain

from resolvelib.resolvers import RequirementInformation, Resolution, Resolver, _build_result

from pdm_conda.conda import CondaResolutionError
from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement

CONSTRAINS_KEY = "___constrains___"
CONDA_RESOLUTION_KEY = "___conda_resolution___"
CONDA_EXCLUDED_IDENTIFIERS_KEY = "___conda_excluded_identifiers___"


@dataclass
class State:
    mapping: dict
    criteria: dict
    backtrack_causes: list
    constrains: dict = field(default_factory=dict)
    conda_resolution: dict = field(default_factory=dict)
    conda_excluded_identifiers: set[str] = field(default_factory=set)


class CondaResolution(Resolution):
    def __init__(
        self,
        provider,
        reporter,
        base_constrains: dict | None = None,
        conda_resolution: dict | None = None,
        conda_excluded_identifiers: set[str] | None = None,
        is_conda_initialized: bool = True,
    ) -> None:
        super().__init__(provider, reporter)
        self._is_conda_initialized = is_conda_initialized
        self._base_constrains = base_constrains or {}
        if not conda_resolution and is_conda_initialized:
            conda_resolution = {
                can.req.conda_name: [can]
                for can in provider.locked_candidates.values()
                if isinstance(can, CondaCandidate)
            }
            conda_resolution["python"] = [provider.python_candidate]
        self._conda_resolution = conda_resolution or {}
        self._conda_excluded_identifiers = conda_excluded_identifiers or set()

    @property
    def state(self):
        if self._states and not isinstance(state := self._states[-1], State):
            self._states[-1] = State(
                state.mapping,
                state.criteria,
                state.backtrack_causes,
                self._base_constrains,
                self._conda_resolution,
                self._conda_excluded_identifiers,
            )
        return super().state

    def _push_new_state(self):
        base = self.state
        base.constrains = base.criteria.pop(CONSTRAINS_KEY, base.constrains)
        base.conda_resolution = base.criteria.pop(CONDA_RESOLUTION_KEY, base.conda_resolution)
        base.conda_excluded_identifiers = base.criteria.pop(
            CONDA_EXCLUDED_IDENTIFIERS_KEY,
            base.conda_excluded_identifiers,
        )
        state = State(
            mapping=base.mapping.copy(),
            criteria=base.criteria.copy(),
            backtrack_causes=base.backtrack_causes[:],
            constrains=base.constrains.copy(),
            conda_resolution=base.conda_resolution.copy(),
            conda_excluded_identifiers=base.conda_excluded_identifiers.copy(),
        )
        # update repository conda resolution to latest
        if self._is_conda_initialized:
            self._p.update_conda_resolution(
                resolution=state.conda_resolution,
                excluded_identifiers=state.conda_excluded_identifiers,
            )
        self._states.append(state)

    def _remove_information_from_criteria(self, criteria, parents):
        state = self.state
        state.constrains = state.criteria.pop(CONSTRAINS_KEY, state.constrains)
        state.conda_resolution = state.criteria.pop(CONDA_RESOLUTION_KEY, state.conda_resolution)
        state.conda_excluded_identifiers = state.criteria.pop(
            CONDA_EXCLUDED_IDENTIFIERS_KEY,
            state.conda_excluded_identifiers,
        )
        super()._remove_information_from_criteria(criteria, parents)

    def _ensure_criteria(self, criteria):
        # save temporarily constrains and conda_resolution in criteria
        for k, v in [
            (CONDA_RESOLUTION_KEY, self.state.conda_resolution),
            (CONSTRAINS_KEY, self.state.constrains),
            (CONDA_EXCLUDED_IDENTIFIERS_KEY, self.state.conda_excluded_identifiers),
        ]:
            if k not in criteria:
                criteria[k] = v.copy()

    def update_constrains(self, candidate: CondaCandidate, criteria=None, merge_old: bool | set[str] = True):
        if isinstance(merge_old, bool):
            merge_old = set(candidate.constrains.keys()) if merge_old else set()
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
                    self._add_to_criteria(criteria, constrain, parent=candidate)

    def _update_conda_resolution(self, criteria, new_requirements):
        # update conda resolution with new requirements
        self._ensure_criteria(criteria)
        resolution = criteria[CONDA_RESOLUTION_KEY]
        excluded_identifiers = criteria[CONDA_EXCLUDED_IDENTIFIERS_KEY]
        if not self._p.compatible_with_resolution(new_requirements, resolution, excluded_identifiers):
            requirements = list(
                chain.from_iterable(
                    (
                        [information.requirement for information in criterion.information]
                        for i, criterion in criteria.items()
                        if i not in [CONDA_RESOLUTION_KEY, CONSTRAINS_KEY, CONDA_EXCLUDED_IDENTIFIERS_KEY]
                        and criterion.information
                    ),
                ),
            )
            with contextlib.suppress(CondaResolutionError):
                criteria[CONDA_EXCLUDED_IDENTIFIERS_KEY] = self._p.update_conda_resolution(
                    new_requirements,
                    requirements,
                    resolution=resolution,
                    excluded_identifiers=excluded_identifiers,
                )

    def _add_to_criteria(self, criteria, requirement, parent):
        if self._is_conda_initialized:
            # merge with constrain if exists
            self._ensure_criteria(criteria)
            constrains = criteria[CONSTRAINS_KEY]
            if (constrain := constrains.get(requirement.conda_name, None)) is not None:
                requirement = constrain.merge(requirement)

            self._update_conda_resolution(criteria, [requirement])
            if criterion := criteria.get(self._p.identify(requirement)):
                # if excluded then delete conda related information else if other conda requirement transform to conda
                if not self._p.repository.is_conda_managed(requirement, criteria[CONDA_EXCLUDED_IDENTIFIERS_KEY]):
                    criterion.information = [
                        (
                            RequirementInformation(i.requirement.as_named_requirement(), i.parent)
                            if isinstance(i.requirement, CondaRequirement)
                            else i
                        )
                        for i in criterion.information
                    ]
                # if not excluded and conda requirement then transform related information to conda
                elif isinstance(requirement, CondaRequirement):
                    criterion.information = [
                        RequirementInformation(as_conda_requirement(i.requirement), i.parent)
                        for i in criterion.information
                    ]

        super()._add_to_criteria(criteria, requirement, parent)

    def _get_updated_criteria(self, candidate):
        criteria = self.state.criteria.copy()
        self._ensure_criteria(criteria)
        dependencies = self._p.get_dependencies(candidate=candidate)
        # update conda resolution with dependencies if parent excluded
        if self._is_conda_initialized and not self._p.repository.is_conda_managed(
            candidate.req,
            criteria[CONDA_EXCLUDED_IDENTIFIERS_KEY],
        ):
            self._update_conda_resolution(criteria, dependencies)

        for requirement in dependencies:
            self._add_to_criteria(criteria, requirement, parent=candidate)

        # merge with previous constrain if exists
        if self._is_conda_initialized and isinstance(candidate, CondaCandidate):
            self.update_constrains(candidate, criteria)
        return criteria

    def initialize_conda_resolution(self, requirements, excluded_identifiers: set[str] | None):
        # update conda resolution
        self._conda_excluded_identifiers = self._p.update_conda_resolution(
            requirements
            if not self._p.compatible_with_resolution(requirements, self._conda_resolution, excluded_identifiers)
            else None,
            resolution=self._conda_resolution,
            excluded_identifiers=excluded_identifiers,
        )

        # update constrains
        for candidates in self._conda_resolution.values():
            for can in candidates:
                self.update_constrains(candidate=can)


class CondaResolver(Resolver):
    def resolve(self, requirements, max_rounds=100):
        project = self.provider.repository.environment.project
        is_conda_initialized = (
            isinstance(self.provider.repository.environment, CondaEnvironment) and project.conda_config.is_initialized
        )
        resolution = CondaResolution(self.provider, self.reporter, is_conda_initialized=is_conda_initialized)
        if is_conda_initialized:
            conda_config = project.conda_config
            resolution.initialize_conda_resolution(requirements, conda_config.excluded_identifiers)
            if conda_config.custom_behavior:
                project.is_distribution = True
        else:
            assert not any(isinstance(r, CondaRequirement) for r in requirements)

        try:
            state = resolution.resolve(requirements, max_rounds=max_rounds)
            result = _build_result(state)
        finally:
            if is_conda_initialized:
                project.is_distribution = None

        # here we remove a self dependency we added because of the custom behavior
        if is_conda_initialized:
            if conda_config.custom_behavior and not project.is_distribution:
                for key, candidate in list(result.mapping.items()):
                    if candidate.name == conda_config.project_name:
                        del result.mapping[key]
            if conda_config.auto_excludes:
                conda_config.excludes = state.conda_excluded_identifiers
        return result
