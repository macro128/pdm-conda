from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from findpython.providers.base import BaseProvider
from pdm.cli.commands.venv import list, utils
from pdm.models.venv import VirtualEnv

from pdm_conda.conda import conda_env_list

if TYPE_CHECKING:
    from pdm_conda.project import CondaProject
    from typing_extensions import Self
    from typing import Iterable
    from findpython.python import PythonVersion

get_venv_prefix = utils.get_venv_prefix


def find_pythons(project) -> Iterable[PythonVersion]:
    for env in conda_env_list(project):
        python_bin = env / "bin/python"
        if python_bin.exists():
            yield CondaProvider.version_maker(python_bin, _interpreter=python_bin, keep_symlink=False)


class CondaProvider(BaseProvider):
    """A provider that finds python installed with Conda."""

    def __init__(self, project: CondaProject) -> None:
        super().__init__()
        self.project = project

    @classmethod
    def create(cls) -> Self | None:
        return None

    def find_pythons(self) -> Iterable[PythonVersion]:
        yield from find_pythons(self.project)


def wrap_iter_venvs(func):
    @functools.wraps(func)
    def wrapper(project):
        envs = func(project)
        for env in envs:
            yield env
        if project.conda_config.is_initialized and project.conda_config.custom_behavior:
            for python in find_pythons(project):
                if str(path := python.executable).endswith("/bin/python"):
                    path = path.parents[1]
                venv = VirtualEnv.get(path)
                if venv.is_conda:
                    yield venv.root.name, venv

    return wrapper


for module in [utils, list]:
    module.iter_venvs = wrap_iter_venvs(module.iter_venvs)
