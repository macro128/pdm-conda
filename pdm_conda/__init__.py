from pdm.core import Core


def main(core: Core):
    from pdm.signals import pre_lock

    from pdm_conda.models.config import PluginConfig
    from pdm_conda.plugin import lock_conda_dependencies
    from pdm_conda.project import CondaProject
    from pdm_conda.resolver import providers

    core.project_class = CondaProject

    pre_lock.connect(lock_conda_dependencies)
    for name, config in PluginConfig.configs():
        core.add_config(name, config)


__version__ = "0.1.0"
