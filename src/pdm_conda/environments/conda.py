from __future__ import annotations

import uuid
from collections import ChainMap
from typing import TYPE_CHECKING

from pdm.models.in_process import get_sys_config_paths
from pdm.models.specifiers import PySpecSet

from pdm_conda.conda import conda_create, conda_info, conda_list, conda_search
from pdm_conda.environments.python import PythonEnvironment
from pdm_conda.models.config import CondaRunner, CondaSolver
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    from pdm.models.working_set import WorkingSet

    from pdm_conda.models.requirements import CondaRequirement, Requirement
    from pdm_conda.project import Project


class CondaEnvironment(PythonEnvironment):
    project: CondaProject

    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self._env_dependencies: dict[str, Requirement] | None = None
        if self.project.conda_config.is_initialized:
            self.python_requires &= PySpecSet(f"=={self.interpreter.version}")
            self.prefix = str(self.interpreter.path).replace("/bin/python", "")
        self._virtual_packages: set[CondaRequirement] | None = None
        self._platform: str | None = None
        self._default_channels: list[str] | None = None

    @property
    def virtual_packages(self) -> set[CondaRequirement]:
        self._check_update_info(self._virtual_packages)
        return self._virtual_packages  # type: ignore

    @property
    def platform(self) -> str:
        self._check_update_info(self._platform)
        return self._platform  # type: ignore

    @property
    def default_channels(self) -> list[str]:
        self._check_update_info(self._default_channels)
        return self._default_channels  # type: ignore

    def _check_update_info(self, prop):
        if prop is None:
            self._get_conda_info()

    def _get_conda_info(self):
        info = conda_info(self.project)
        self._virtual_packages = info["virtual_packages"]
        self._platform = info["platform"]
        self._default_channels = info["channels"]

    def get_paths(self, dist_name: str | None = None) -> dict[str, str]:
        if self.project.conda_config.is_initialized:
            paths = get_sys_config_paths(
                str(self.interpreter.executable),
                {k: self.prefix for k in ("base", "platbase", "installed_base")},
                kind="prefix",
            )
            paths.setdefault("prefix", self.prefix)
            paths["headers"] = paths["include"]
            return paths
        return super().get_paths(dist_name)

    def get_working_set(self) -> WorkingSet:
        """Get the working set based on local packages directory, include Conda managed packages."""
        working_set = super().get_working_set()
        if self.project.conda_config.is_initialized:
            dist_map = working_set._dist_map | conda_list(self.project)
            working_set._dist_map = dist_map
            shared_map = getattr(working_set, "_shared_map", {})
            working_set._iter_map = ChainMap(dist_map, shared_map)
        return working_set

    @property
    def env_dependencies(self) -> dict[str, Requirement]:
        if self._env_dependencies is None:
            self._env_dependencies = {}

            def load_dependencies(name: str, packages: dict, dependencies: dict):
                if name not in packages and name not in dependencies:
                    return
                candidate = conda_search(self.project, packages[name].req)[0]
                dependencies[name] = candidate.req
                for d in candidate.dependencies:
                    load_dependencies(d.name, packages, dependencies)

            working_set = conda_list(self.project)
            dependencies = ["python"]
            if (runner := self.project.conda_config.runner) in working_set:
                dependencies.append(runner)
            if (
                runner in (CondaRunner.MAMBA, CondaRunner.MICROMAMBA)
                or self.project.conda_config.solver == CondaSolver.MAMBA
            ):
                self._env_dependencies = conda_create(
                    self.project,
                    [working_set[d].req for d in dependencies],
                    prefix=f"/tmp/{uuid.uuid4()}",
                    dry_run=True,
                )
            else:
                for dep in dependencies:
                    load_dependencies(dep, working_set, self._env_dependencies)

        return self._env_dependencies
