from __future__ import annotations

from typing import cast, TYPE_CHECKING

from pdm.cli.commands.venv.backends import BACKENDS, CondaBackend as BackendBase

from pdm_conda.cli.utils import ensure_logger
from pdm_conda.conda import conda_create, conda_env_remove
from pdm_conda.models.config import CondaRunner
from pdm_conda.models.requirements import parse_requirement
from pdm_conda.project import CondaProject

if TYPE_CHECKING:
    from pdm.project import Project
    from pathlib import Path


class CondaBackend(BackendBase):
    def __init__(self, project: Project, python: str | None) -> None:
        super().__init__(project, python)
        self.project = cast(CondaProject, project)

    def create(
        self,
        name: str | None = None,
        args: tuple[str, ...] = (),
        force: bool = False,
        in_project: bool = False,
        prompt: str | None = None,
        with_pip: bool = False,
    ) -> Path:
        with ensure_logger(self.project, "conda_create"):
            return super().create(name, args, force, in_project, prompt, with_pip)

    def get_location(self, name: str | None) -> Path:
        with self.project.conda_config.with_conda_venv_location() as (venv_location, _):
            if conda_name := (name is not None and name.startswith("conda:")):
                name = name[6:]
            if conda_name:
                location = venv_location / name
            else:
                location = super().get_location(name)
            return location

    def _ensure_clean(self, location: Path, force: bool = False) -> None:
        if location.is_dir() and force:
            conda_env_remove(self.project, prefix=location)
        super()._ensure_clean(location, force)

    def perform_create(self, location: Path, args: tuple[str, ...], prompt: str | None = None) -> None:
        if self.python:
            python_ver = self.python
        else:
            python = self._resolved_interpreter
            python_ver = f"{python.major}.{python.minor}"

        requirements = [parse_requirement(f"conda:python={python_ver}")]
        for arg in args:
            if arg.startswith("-"):
                break
            requirements.append(parse_requirement(f"conda:{arg}"))
        conda_create(self.project, requirements=requirements, prefix=location, fetch_candidates=False)


BACKENDS = cast(dict, BACKENDS)
for runner in CondaRunner:
    BACKENDS[runner.value] = CondaBackend
