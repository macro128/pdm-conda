import functools
from copy import copy

from pdm.environments import PythonEnvironment

from pdm_conda.project import CondaProject

_patched = False


def wrap_init(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        res = func(self, *args, **kwargs)
        if isinstance(self.project, CondaProject):
            self.project = copy(self.project)
            self.project.environment = self
        return res

    return wrapper


if not _patched:
    setattr(PythonEnvironment, "__init__", wrap_init(PythonEnvironment.__init__))
    _patched = True
