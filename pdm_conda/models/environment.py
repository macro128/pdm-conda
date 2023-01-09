import functools

from pdm.models.environment import Environment

from pdm_conda.plugin import conda_list

_patched = False


def wrap_get_working_set(func):
    @functools.wraps(func)
    def wrapper(self: Environment):
        working_set = func(self)
        working_set._dist_map.update(conda_list(self.project))
        return working_set

    return wrapper


if not _patched:
    setattr(Environment, "get_working_set", wrap_get_working_set(Environment.get_working_set))
    _patched = True
