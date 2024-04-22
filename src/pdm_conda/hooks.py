from pdm.project import Project
from pdm.signals import post_lock

from pdm_conda.project import CondaProject


@post_lock.connect
def on_post_lock(project: Project, *args, dry_run: bool, **kwargs):
    """Write the pyproject.toml file after the lock file is generated if the project is a CondaProject and auto_excludes
    is configured.

    :param project: PDM project
    :param dry_run: whether it is a dry run
    """
    if isinstance(project, CondaProject):
        config = project.conda_config
        if not dry_run and config.is_initialized and config.auto_excludes and config.excluded_identifiers:
            project.pyproject.write(show_message=False)
