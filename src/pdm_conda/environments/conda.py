from __future__ import annotations

import os
import sysconfig
import uuid
from collections import ChainMap
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pdm.environments import PythonEnvironment
from pdm.exceptions import ProjectError
from pdm.models.specifiers import PySpecSet

from pdm_conda.conda import conda_create, conda_list, conda_search
from pdm_conda.mapping import pypi_to_conda
from pdm_conda.models.config import CondaRunner, CondaSolver
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name

if TYPE_CHECKING:
    from pdm.models.working_set import WorkingSet

    from pdm_conda.models.requirements import Requirement
    from pdm_conda.project import Project


def ensure_conda_env():
    if (packages_path := os.getenv("CONDA_PREFIX", None)) is None:
        raise ProjectError("Conda environment not detected.")
    return packages_path


class CondaEnvironment(PythonEnvironment):
    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self.project = cast(CondaProject, project)
        self._env_dependencies: dict[str, Requirement] | None = None
        self.python_requires &= PySpecSet(f"=={self.interpreter.version}")

    @property
    def packages_path(self) -> Path:
        return Path(ensure_conda_env())

    def get_paths(self) -> dict[str, str]:
        prefix = ensure_conda_env()
        paths = sysconfig.get_paths(vars={k: prefix for k in ("base", "platbase", "installed_base")}, expand=True)
        paths.setdefault("prefix", prefix)
        return paths

    def get_working_set(self) -> WorkingSet:
        """
        Get the working set based on local packages directory, include Conda managed packages.
        """
        working_set = super().get_working_set()
        if self.project.conda_config.is_initialized:
            dist_map = conda_list(self.project) | {
                normalize_name(pypi_to_conda(dist.metadata["Name"])): dist
                for dist in getattr(working_set, "_dist_map").values()
            }
            setattr(working_set, "_dist_map", dist_map)
            shared_map = getattr(working_set, "_shared_map", {})
            setattr(working_set, "_iter_map", ChainMap(dist_map, shared_map))
        return working_set

    @property
    def env_dependencies(self) -> dict[str, Requirement]:
        if self._env_dependencies is None:
            self._env_dependencies = dict()

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
