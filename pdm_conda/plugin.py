import json
import re
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import cast

from pdm.exceptions import RequirementError
from pdm.project import Project
from unearth import Link

from pdm_conda.models.config import PluginConfig
from pdm_conda.models.requirements import CondaPackage, CondaRequirement, Requirement
from pdm_conda.project import CondaProject


def run_conda(cmd, **environment) -> dict:
    """
    Creates temporary environment file and run conda command
    :param cmd: conda command
    :param environment: environment data
    :return: conda command response
    """
    with NamedTemporaryFile(mode="w+", suffix=".yml") as f:
        for k in environment:
            f.write(f"{k}:\n")
            for v in environment[k]:
                f.write(f"  - {v}\n")
        if environment:
            f.seek(0)
            cmd = cmd + ["-f", f.name]
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        if "--json" in cmd:
            try:
                response = json.loads(process.stdout)
            except:
                response = {}
        else:
            response = {"message": process.stdout}
        try:
            process.check_returncode()
        except subprocess.CalledProcessError:
            msg = "Error locking dependencies\n"
            if err := response.get("solver_problems", []):
                msg += "\n".join(err)
            elif err := response.get("message", []):
                msg += err
            else:
                msg += process.stderr
            raise RequirementError(msg)
    return response


def lock_conda_dependencies(
    project: Project, requirements: list[Requirement], **kwargs
):
    """
    Extract conda marked dependencies from requirements, install them if not dry_run and add conda resolved versions
    """
    config = PluginConfig.load_config(project)
    _requirements = [
        r.as_line() for r in requirements if isinstance(r, CondaRequirement)
    ]
    if _requirements:
        with TemporaryDirectory() as d:
            prefix = f"{d}/env"
            run_conda(
                config.command("create") + ["--prefix", prefix, "--json"],
                channels=[c.split("/")[0] for c in config.channels],
                dependencies=[f"python=={project.python.version}"],
            )
            project.core.ui.echo(f"Created temporary environment at {prefix}")
            try:
                conda_packages = conda_lock(
                    project,
                    _requirements,
                    prefix,
                    config,
                )
            finally:
                run_conda(config.command("remove") + ["--prefix", prefix, "--json"])
                project.core.ui.echo(f"Removed temporary environment at {prefix}")
        update_requirements(requirements, conda_packages)
        project = cast(CondaProject, project)
        project.conda_packages.update(conda_packages)


def conda_lock(
    project: Project,
    requirements: list[str],
    prefix: str,
    config: PluginConfig | None = None,
) -> dict[str, CondaPackage]:
    """
    Resolve conda marked requirements
    :param project: PDM project
    :param requirements: list of requirements
    :param prefix: environment prefix
    :param config: plugin config
    :return: resolved packages
    """
    packages: dict[str, CondaPackage] = dict()
    if config is None:
        config = PluginConfig.load_config(project)
    core = project.core
    if not requirements:
        return packages

    core.ui.echo("Using conda to get: " + " ".join(requirements))
    response = run_conda(
        config.command()
        + ["--force-reinstall", "--json", "--dry-run", "--prefix", prefix],
        channels=config.channels,
        dependencies=requirements,
    )

    if "actions" in response:
        for package in response["actions"]["LINK"]:
            dependencies: list = package["depends"] or []
            requires_python = None
            to_delete = []
            for d in dependencies:
                if match := re.match(r"python( .+|$)", d):
                    to_delete.append(d)
                    if requires_python is None:
                        requires_python = match.group(1).strip() or "*"
            for d in to_delete:
                dependencies.remove(d)
            hashes = {h: package[h] for h in ["sha256", "md5"] if h in package}
            url = package["url"]
            for k, v in hashes.items():
                url += f"#{k}={v}"
            name = package["name"]
            packages[name] = CondaPackage(
                name=name,
                version=package["version"],
                link=Link(
                    url,
                    comes_from=package["channel"],
                    requires_python=requires_python,
                    hashes=hashes,
                ),
                _dependencies=dependencies,
                requires_python=requires_python,
            )
    else:
        if (msg := response.get("message", None)) is not None:
            core.ui.echo(msg)

    for p in packages.values():
        p.load_dependencies(packages)

    return packages


def conda_install(
    project: Project,
    packages: dict[str, CondaPackage],
    config: PluginConfig | None = None,
    verbose: bool = False,
    dry_run: bool = False,
):
    """
    Install resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param config: plugin config
    :param verbose: show conda response if true
    :param dry_run: don't install if dry run
    """
    config = config or PluginConfig.load_config(project)
    command = config.command() + ["--freeze-installed"]
    if dry_run:
        command.append("--dry-run")
    response = run_conda(
        command,
        dependencies=[p.link.url_without_fragment for p in packages.values()],
    )
    if verbose:
        project.core.ui.echo(response)


def update_requirements(
    requirements: list[Requirement],
    conda_packages: dict[str, CondaPackage],
):
    """
    Update requirements list with conda_packages
    :param requirements: requirements list
    :param conda_packages: conda packages
    """
    dependencies = set()
    for package in conda_packages.values():
        dependencies.update(package.dependencies)
    for i, requirement in enumerate(requirements):
        if requirement.name in conda_packages:
            requirements[i] = conda_packages[requirement.name].req
            dependencies.add(requirements[i])
    requirements.extend(
        [p.req for p in conda_packages.values() if p.req not in dependencies],
    )
