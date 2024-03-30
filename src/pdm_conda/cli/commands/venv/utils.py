from __future__ import annotations

from typing import TYPE_CHECKING

from findpython.providers.base import BaseProvider

from pdm_conda.conda import conda_env_list

if TYPE_CHECKING:
    from pdm_conda.project import CondaProject
    from typing_extensions import Self
    from typing import Iterable
    from findpython.python import PythonVersion


class CondaProvider(BaseProvider):
    """A provider that finds python installed with Conda."""

    def __init__(self, project: CondaProject) -> None:
        super().__init__()
        self.project = project

    @classmethod
    def create(cls) -> Self | None:
        return None

    def find_pythons(self) -> Iterable[PythonVersion]:
        for env in conda_env_list(self.project):
            python_bin = env / "bin/python"
            if python_bin.exists():
                yield self.version_maker(python_bin, _interpreter=python_bin, keep_symlink=False)
