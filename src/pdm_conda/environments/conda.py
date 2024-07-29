from __future__ import annotations

import uuid
from collections import ChainMap
from functools import cached_property
from typing import TYPE_CHECKING

from pdm.models.in_process import get_sys_config_paths
from pdm.models.specifiers import PySpecSet

from pdm_conda.conda import conda_create, conda_info, conda_list
from pdm_conda.environments.python import PythonEnvironment
from pdm_conda.models.markers import CondaEnvSpec
from pdm_conda.project import CondaProject
from pdm_conda.utils import fix_path, get_python_dir

if TYPE_CHECKING:
    from pdm.models.working_set import WorkingSet

    from pdm_conda.models.requirements import Requirement
    from pdm_conda.project import Project


class CondaEnvironment(PythonEnvironment):
    project: CondaProject

    def __init__(self, project: Project) -> None:
        super().__init__(project)
        if self.project.conda_config.is_initialized:
            self.python_requires &= PySpecSet(f"=={self.interpreter.version}")
            self.prefix = str(get_python_dir(fix_path(self.interpreter.path)))
        self._env_dependencies: dict[str, Requirement] | None = None

        self.allow_all_spec_overrides: dict[str, str] = {}

    @cached_property
    def spec(self) -> CondaEnvSpec:
        conda_env = conda_info(self.project)
        conda_spec = {}
        for req in conda_env["virtual_packages"]:
            if req.name == "glibc":
                conda_spec["glibc"] = req.version
            elif req.name == "cuda":
                conda_spec["cuda"] = req.version
            elif req.name == "unix":
                conda_spec["unix"] = req.version
            else:
                for key in ("linux", "win", "osx"):
                    if key == req.name:
                        conda_spec["system"] = req.version
                        break

        return CondaEnvSpec.from_env_spec(super().spec, **conda_spec)

    @property
    def allow_all_spec(self) -> CondaEnvSpec:
        env_spec = CondaEnvSpec.from_env_spec(super().allow_all_spec, **self.allow_all_spec_overrides)
        # if allow_all_spec_overrides is set, override the allow_all_spec one time
        if self.allow_all_spec_overrides:
            self.allow_all_spec_overrides = {}
        return env_spec

    def get_paths(self, dist_name: str | None = None) -> dict[str, str]:
        if self.project.conda_config.is_initialized:
            paths = get_sys_config_paths(
                str(fix_path(self.interpreter.executable)),
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

            working_set = conda_list(self.project)
            dependencies = ["python"]
            if (runner := self.project.conda_config.runner) in working_set:
                dependencies.append(runner)
            self._env_dependencies = conda_create(
                self.project,
                [working_set[d].req for d in dependencies],
                prefix=f"/tmp/{uuid.uuid4()}",
                dry_run=True,
            )

        return self._env_dependencies  # type: ignore
