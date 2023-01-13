from typing import cast

from pdm.models.environment import Environment, GlobalEnvironment
from pdm.models.working_set import WorkingSet
from pdm.project import Project

from pdm_conda.plugin import conda_list
from pdm_conda.project import CondaProject


class CondaEnvironment(Environment):
    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self.project = cast(CondaProject, project)

    def get_working_set(self) -> WorkingSet:
        working_set = super().get_working_set()
        working_set._dist_map.update(conda_list(self.project))
        return working_set


class CondaGlobalEnvironment(GlobalEnvironment, CondaEnvironment):
    pass
