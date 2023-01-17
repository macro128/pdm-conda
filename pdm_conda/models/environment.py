from typing import cast

from pdm.models.environment import Environment, GlobalEnvironment
from pdm.models.working_set import WorkingSet
from pdm.project import Project

from pdm_conda.mapping import pypi_to_conda
from pdm_conda.plugin import conda_list
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name


class CondaEnvironment(Environment):
    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self.project = cast(CondaProject, project)

    def get_working_set(self) -> WorkingSet:
        working_set = super().get_working_set()
        working_set._dist_map = conda_list(self.project) | {
            normalize_name(pypi_to_conda(dist.metadata["Name"])): dist for dist in working_set._dist_map.values()
        }
        return working_set


class CondaGlobalEnvironment(GlobalEnvironment, CondaEnvironment):
    pass
