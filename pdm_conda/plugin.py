import json
import subprocess
from functools import lru_cache
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import cast

from pdm.exceptions import RequirementError
from pdm.models.setup import Setup
from pdm.project import Project

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import (
    CondaRequirement,
    Requirement,
    parse_conda_version,
    parse_requirement,
)
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


@lru_cache(maxsize=None)
def _conda_search(
    requirement: str,
    project: CondaProject,
    channel: str | None = None,
) -> list[CondaCandidate]:
    """
    Search conda candidates for a requirement
    :param requirement: requirement
    :param project: PDM project
    :param channel: requirement channel
    :return: list of conda candidates
    """
    config = project.conda_config
    command = config.command("search")
    if not project.virtual_packages:
        project.virtual_packages = conda_virtual_packages(project)

    command.append(requirement)
    channels = [channel] if channel else config.channels
    for c in channels:
        command.extend(["-c", c])
    command.append("--json")
    result = run_conda(command)
    candidates = []
    for p in result.get("result", dict()).get("pkgs", []):
        dependencies = p.get("depends", [])
        valid_candidate = True
        for d in dependencies:
            if d.startswith("__"):
                print(d)
                if d not in project.virtual_packages:
                    valid_candidate = False
                    break
        if valid_candidate:
            candidates.append(CondaCandidate.from_conda_package(p))

    return candidates


def conda_search(
    requirement: CondaRequirement | str,
    project: CondaProject,
    channel: str | None = None,
) -> list[CondaCandidate]:
    """
    Search conda candidates for a requirement
    :param requirement: requirement
    :param project: PDM project
    :param channel: requirement channel
    :return: list of conda candidates
    """
    if isinstance(requirement, CondaRequirement):
        channel = channel or requirement.channel
        requirement = requirement.as_line(with_build_string=True).replace(" ", "=")
    if "::" in requirement:
        channel, requirement = requirement.split("::", maxsplit=1)
    return _conda_search(requirement, project, channel)


def update_requirements(requirements: list[Requirement], conda_packages: dict[str, CondaCandidate]):
    """
    Update requirements list with conda_packages
    :param requirements: requirements list
    :param conda_packages: conda packages
    """
    repeated_packages: dict[str, int] = dict()
    for i, requirement in enumerate(requirements):
        if (name := requirement.name) in conda_packages:
            req = conda_packages[name].req
            req.specifier = requirement.specifier
            requirements[i] = req
        repeated_packages[name] = repeated_packages.get(name, 0) + 1
    to_remove = []
    for r in requirements:
        if repeated_packages.get(r.name, 1) > 1:
            to_remove.append(r)
            repeated_packages.pop(r.name)
    for r in to_remove:
        requirements.remove(r)


def lock_conda_dependencies(project: Project, requirements: list[Requirement], **kwargs):
    """
    Overwrite requirements with conda versions if needed in lock
    :param project: PDM project
    :param requirements: requirements list
    """
    project = cast(CondaProject, project)
    config = project.conda_config
    if not config.is_initialized:
        return

    _requirements = [r for r in requirements if isinstance(r, CondaRequirement)]
    if 0 < len(_requirements) < len(requirements):
        python_req = f"python=={project.python.version}"
        working_set = conda_list(project)
        if "python" in working_set:
            python_req = working_set["python"].as_line()
        _requirements.insert(0, parse_requirement(f"conda:{python_req}"))
        with TemporaryDirectory() as d:
            prefix = f"{d}/env"
            run_conda(config.command("create") + ["--prefix", prefix, "--json"])
            project.core.ui.echo(f"Created temporary environment at {prefix}")
            try:
                conda_packages = conda_lock(project, _requirements, prefix)
            finally:
                run_conda(config.command("remove") + ["--prefix", prefix, "--json"])
                project.core.ui.echo(f"Removed temporary environment at {prefix}")
    else:
        conda_packages = {}
        for r in _requirements:
            candidate = conda_search(r, project)[0]
            conda_packages[candidate.name] = candidate

    update_requirements(requirements, conda_packages)


def conda_lock(
    project: CondaProject,
    requirements: list[CondaRequirement],
    prefix: str,
) -> dict[str, CondaCandidate]:
    """
    Resolve conda marked requirements
    :param project: PDM project
    :param requirements: list of requirements
    :param prefix: environment prefix
    :return: resolved packages
    """
    packages: dict[str, CondaCandidate] = dict()
    config = project.conda_config
    core = project.core
    if not requirements:
        return packages

    core.ui.echo("Using conda to get: " + " ".join([r.as_line() for r in requirements if r.name != "python"]))
    _requirements = [r.as_line(with_build_string=True, with_channel=True).replace(" ", "=") for r in requirements]
    response = run_conda(
        config.command() + ["--force-reinstall", "--json", "--dry-run", "--prefix", prefix],
        channels=config.channels,
        dependencies=_requirements,
    )

    if "actions" in response:
        for package in response["actions"]["LINK"]:
            package = CondaCandidate.from_conda_package(package)
            packages[package.name] = package
    else:
        if (msg := response.get("message", None)) is not None:
            core.ui.echo(msg)

    return packages


def _conda_install(
    project: CondaProject,
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
    project: CondaProject,
    packages: str | list[str],
    verbose: bool = False,
    dry_run: bool = False,
    no_deps: bool = False,
):
    """
    Install resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param verbose: show conda response if true
    :param dry_run: don't install if dry run
    :param no_deps: don't install dependencies if true
    """
    config = project.conda_config
    command = config.command()
    if no_deps:
        command.append("--no-deps")
    if dry_run:
        command.append("--dry-run")

    _conda_install(project, command, packages, verbose)


def conda_uninstall(
    project: CondaProject,
    packages: str | list[str],
    verbose: bool = False,
    dry_run: bool = False,
    no_deps: bool = False,
):
    """
    Uninstall resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param verbose: show conda response if true
    :param dry_run: don't uninstall if dry run
    :param no_deps: don't uninstall dependencies if true
    """
    config = project.conda_config
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


def conda_virtual_packages(project: CondaProject) -> set[str]:
    """
    Get conda virtual packages
    :param project: PDM project
    :return: set of virtual packages
    """
    config = project.conda_config
    virtual_packages = []
    if config.is_initialized:
        info = run_conda(config.command("info") + ["--json"])
        virtual_packages = [p.split("=")[0] for p in info["virtual packages"]]
    return set(virtual_packages)


def conda_list(project: CondaProject) -> dict[str, CondaSetupDistribution]:
    """
    List conda installed packages
    :param project: PDM project
    :return: packages distribution
    """
    config = project.conda_config
    distributions = dict()
    if config.is_initialized:
        packages = run_conda(config.command("list") + ["--json"])
        for package in packages:
            name, version = package["name"], package["version"]
            distributions[normalize_name(name)] = CondaSetupDistribution(
                Setup(
                    name=name,
                    summary="",
                    version=parse_conda_version(version),
                ),
                package=package,
            )

    return distributions
