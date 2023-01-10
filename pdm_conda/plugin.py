import json
import re
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import cast

from pdm.exceptions import RequirementError
from pdm.models.requirements import strip_extras
from pdm.models.setup import Setup
from pdm.project import Project
from unearth import Link

from pdm_conda.models.config import PluginConfig
from pdm_conda.models.requirements import CondaPackage, CondaRequirement, Requirement
from pdm_conda.models.setup import CondaSetupDistribution
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name


def run_conda(cmd, **environment) -> dict:
    """
    Creates temporary environment file and run conda command
    :param cmd: conda command
    :param environment: environment data
    :return: conda command response
    """
    with NamedTemporaryFile(mode="w+", suffix=".yml") as f:
        if environment:
            for name, options in environment.items():
                if options:
                    f.write(f"{name}:\n")
                    for v in options:
                        f.write(f"  - {v}\n")
            f.seek(0)
            cmd = cmd + ["-f", f.name]
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
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
            if isinstance(response, dict):
                if response.get("success", False):
                    pass
                if err := response.get("solver_problems", []):
                    msg += "\n".join(err)
                elif err := response.get("message", []):
                    msg += err
            else:
                msg += process.stderr
            msg += str(environment)
            raise RequirementError(msg)
    return response


def update_dependencies(package: CondaPackage | None, dependencies: set):
    if package is None or not package.dependencies:
        return
    for dep in package.dependencies:
        dependencies.add(dep)
        update_dependencies(dep.package, dependencies)


def update_requirements(requirements: list[Requirement], conda_packages: dict[str, CondaPackage]):
    """
    Update requirements list with conda_packages
    :param requirements: requirements list
    :param conda_packages: conda packages
    """
    dependencies: set[Requirement] = set()
    for package in conda_packages.values():
        update_dependencies(package, dependencies)
    repeated_packages: dict[str, int] = dict()
    for i, requirement in enumerate(requirements):
        name, _ = strip_extras(requirement.name)
        if name in conda_packages:
            req = conda_packages[name].req
            requirements[i] = req
            dependencies.add(req)
        repeated_packages[name] = repeated_packages.get(name, 0) + 1
    if (package := conda_packages.get("python", None)) is not None:  # type: ignore
        dependencies.add(package.req)
    # remove repeated requirements
    to_remove = []
    for r in requirements:
        if repeated_packages.get(r.name, 1) > 1:
            to_remove.append(r)
            repeated_packages.pop(r.name)
    for r in to_remove:
        requirements.remove(r)
    requirements.extend([p.req for p in conda_packages.values() if p.req not in dependencies])


def lock_conda_dependencies(project: Project, requirements: list[Requirement], **kwargs):
    """
    Extract conda marked dependencies from requirements, install them if not dry_run and add conda resolved versions
    """
    config = PluginConfig.load_config(project)
    _requirements = [r.as_line() for r in requirements if isinstance(r, CondaRequirement)]
    if _requirements:
        _requirements.insert(0, f"python=={project.python.version}")
        with TemporaryDirectory() as d:
            prefix = f"{d}/env"
            run_conda(config.command("create") + ["--prefix", prefix, "--json"])
            project.core.ui.echo(f"Created temporary environment at {prefix}")
            try:
                conda_packages = conda_lock(project, _requirements, prefix, config)
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

    core.ui.echo("Using conda to get: " + " ".join([r for r in requirements if not r.startswith("python==")]))
    response = run_conda(
        config.command() + ["--force-reinstall", "--json", "--dry-run", "--prefix", prefix],
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
                link=Link(url, comes_from=package["channel"], requires_python=requires_python, hashes=hashes),
                full_dependencies=dependencies,
                requires_python=requires_python,
            )
    else:
        if (msg := response.get("message", None)) is not None:
            core.ui.echo(msg)

    for p in packages.values():
        p.load_dependencies(packages)

    return packages


def _conda_install(
    project: Project,
    command: list[str],
    packages: str | list[str] | None = None,
    verbose: bool = False,
):
    if isinstance(packages, str):
        packages = [packages]
    kwargs = dict()
    if packages:
        kwargs["dependencies"] = packages
    response = run_conda(command + ["--json"], **kwargs)
    if verbose:
        project.core.ui.echo(response)


def conda_install(
    project: Project,
    packages: str | list[str],
    config: PluginConfig | None = None,
    verbose: bool = False,
    dry_run: bool = False,
    no_deps: bool = False,
):
    """
    Install resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param config: plugin config
    :param verbose: show conda response if true
    :param dry_run: don't install if dry run
    :param no_deps: don't install dependencies if true
    """

    config = config or PluginConfig.load_config(project)
    command = config.command()
    if no_deps:
        command.append("--no-deps")
    if dry_run:
        command.append("--dry-run")

    _conda_install(project, command, packages, verbose)


def conda_uninstall(
    project: Project,
    packages: str | list[str],
    config: PluginConfig | None = None,
    verbose: bool = False,
    dry_run: bool = False,
    no_deps: bool = False,
):
    """
    Uninstall resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param config: plugin config
    :param verbose: show conda response if true
    :param dry_run: don't uninstall if dry run
    :param no_deps: don't uninstall dependencies if true
    """

    config = config or PluginConfig.load_config(project)
    command = config.command("remove")
    if no_deps:
        command.append("--no-prune")
    if dry_run:
        command.append("--dry-run")
    if isinstance(packages, str):
        packages = [packages]
    command.extend(packages)
    command.append("--json")

    _conda_install(project, command, verbose=verbose)


def conda_list(project: Project) -> dict[str, CondaSetupDistribution]:
    project = cast(CondaProject, project)
    config = PluginConfig.load_config(project)
    distributions = dict()
    if config.is_initialized:
        packages = run_conda(config.command("list") + ["--json"])
        for package in packages:
            name = package["name"]
            if name != "python":
                distributions[normalize_name(name)] = CondaSetupDistribution(
                    Setup(
                        name=name,
                        summary="",
                        version=package["version"],
                    ),
                )

    return distributions
