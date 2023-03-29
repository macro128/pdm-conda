from typing import cast

from pdm.exceptions import NoPythonVersion
from pdm.models.environment import Environment
from pdm.models.requirements import Requirement
from pdm.models.working_set import WorkingSet
from pdm.project import Project

from pdm_conda.conda import conda_list, conda_search
from pdm_conda.mapping import pypi_to_conda
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name


class CondaEnvironment(Environment):
    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self.project = cast(CondaProject, project)
        self._python_dependencies: dict[str, Requirement] | None = None
        self._python_candidate: CondaCandidate | None = None

    def get_working_set(self) -> WorkingSet:
        """
        Get the working set based on local packages directory, include Conda managed packages.
        """
        working_set = super().get_working_set()
        working_set._dist_map = conda_list(self.project) | {
            normalize_name(pypi_to_conda(dist.metadata["Name"])): dist for dist in working_set._dist_map.values()
        }
        return working_set

    @property
    def python_candidate(self) -> CondaCandidate:
        if self._python_candidate is None:
            python_package = conda_list(self.project).get("python", None)
            if python_package is None:
                raise NoPythonVersion("No python found in Conda environment.")
            self._python_candidate = conda_search(python_package.as_line().replace(" ", "="), self.project)[0]
        return self._python_candidate

    @property
    def python_dependencies(self) -> dict[str, Requirement]:
        if self._python_dependencies is None:
            self._python_dependencies = dict()

            def load_dependencies(name: str, packages: dict, dependencies: dict):
                if name not in packages and name not in dependencies:
                    return
                package = packages[name].as_line().replace(" ", "=")
                candidate = conda_search(package, self.project)[0]
                dependencies[name] = candidate.req
                for d in candidate.dependencies:
                    load_dependencies(d.name, packages, dependencies)

            load_dependencies("python", conda_list(self.project), self._python_dependencies)

        return self._python_dependencies
