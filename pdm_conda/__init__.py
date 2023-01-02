from pdm.core import Core


def main(core: Core):
    from pdm.signals import pre_lock

    from pdm_conda import project, providers, repositories
    from pdm_conda.models import candidates, requirements
    from pdm_conda.plugin import lock_conda_dependencies

    pre_lock.connect(lock_conda_dependencies)


__version__ = "0.0.1"
