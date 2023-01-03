from pdm.core import Core


def main(core: Core):
    from pdm.signals import pre_lock

    from pdm_conda import project
    from pdm_conda.models import candidates, repositories, requirements
    from pdm_conda.plugin import lock_conda_dependencies
    from pdm_conda.resolver import providers

    pre_lock.connect(lock_conda_dependencies)


__version__ = "0.0.1"
