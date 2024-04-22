import functools
from collections import ChainMap
from copy import copy

from pdm.environments import PythonEnvironment

from pdm_conda.mapping import pypi_to_conda
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name

_patched = False


def wrap_get_working_set(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        res = func(self, *args, **kwargs)
        dist_map = {normalize_name(pypi_to_conda(dist.metadata["Name"])): dist for dist in res._dist_map.values()}
        res._dist_map = dist_map
        res._iter_map = ChainMap(dist_map, getattr(res, "_shared_map", {}))
        return res

    return wrapper


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
    PythonEnvironment.__init__ = wrap_init(PythonEnvironment.__init__)
    PythonEnvironment.get_working_set = wrap_get_working_set(PythonEnvironment.get_working_set)
    _patched = True
