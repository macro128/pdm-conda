from pdm.core import Core


def main(core: Core):
    from pdm.signals import pre_lock

    from pdm_conda import utils
    from pdm_conda.cli.commands.add import Command as AddCommand
    from pdm_conda.cli.commands.remove import Command as RemoveCommand
    from pdm_conda.models import environment
    from pdm_conda.models.config import PluginConfig
    from pdm_conda.plugin import lock_conda_dependencies
    from pdm_conda.project import CondaProject

    core.project_class = CondaProject

    core.register_command(AddCommand)
    core.register_command(RemoveCommand)

    pre_lock.connect(lock_conda_dependencies)
    for name, config in PluginConfig.configs():
        core.add_config(name, config)


__version__ = "0.3.0"
