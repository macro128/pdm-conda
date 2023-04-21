from pdm.core import Core


def main(core: Core):
    from pdm_conda import utils  # noqa
    from pdm_conda.cli import utils as cli_utils  # noqa
    from pdm_conda.cli.commands.add import Command as AddCommand
    from pdm_conda.cli.commands.remove import Command as RemoveCommand
    from pdm_conda.models.config import CONFIGS
    from pdm_conda.project import CondaProject

    core.project_class = CondaProject

    core.register_command(AddCommand)
    core.register_command(RemoveCommand)

    for name, config in CONFIGS:
        core.add_config(name, config)


__version__ = "0.9.1"
