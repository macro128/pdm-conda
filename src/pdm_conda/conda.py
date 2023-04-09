import contextlib
import json
import subprocess
from functools import lru_cache
from tempfile import NamedTemporaryFile
from typing import Iterable
from urllib.parse import urlparse

from packaging.version import Version
from pdm import termui
from pdm.exceptions import RequirementError
from pdm.models.setup import Setup
from pdm.termui import Verbosity

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.config import CondaRunner
from pdm_conda.models.requirements import (
    CondaRequirement,
    Requirement,
    parse_conda_version,
    parse_requirement,
)
from pdm_conda.models.setup import CondaSetupDistribution
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name

logger = termui.logger


@contextlib.contextmanager
def _optional_temporary_file(environment: dict):
    if environment:
        with NamedTemporaryFile(mode="w+", suffix=".yml") as f:
            yield f
    else:
        yield


def run_conda(cmd, **environment) -> dict:
    """
    Creates temporary environment file and run conda command
    :param cmd: conda command
    :param environment: environment data
    :return: conda command response
    """
    with _optional_temporary_file(environment) as f:
        if environment:
            for name, options in environment.items():
                if options:
                    f.write(f"{name}:\n")
                    for v in options:
                        f.write(f"  - {v}\n")
            f.seek(0)
            cmd = cmd + ["-f", f.name]
        logger.debug(f"cmd: {' '.join(cmd)}")
        if environment:
            logger.debug(f"env: {environment}")
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
    except subprocess.CalledProcessError as e:
        msg = "Error locking dependencies\n"
        if isinstance(response, dict) and not response.get("success", False):
            if err := response.get("solver_problems", response.get("error", response.get("message", []))):
                if isinstance(err, str):
                    err = [err]
                msg += "\n".join(err)
        else:
            msg += process.stderr
        if environment:
            msg += f"\n{environment}"
        raise RequirementError(msg) from e
    return response


def _sort_packages(packages: list[dict]) -> Iterable[dict]:
    """
    Sort packages following mamba specification
    (https://mamba.readthedocs.io/en/latest/advanced_usage/package_resolution.html).
    :param packages: list of conda packages
    :return: sorted conda packages
    """
    if len(packages) <= 1:
        return packages

    def get_preference(package):
        return (
            not package.get("track_feature", ""),
            Version(parse_conda_version(package["version"], inverse=package.get("name", "") == "openssl")),
            package.get("build_number", 0),
            package.get("timestamp", 0),
        )

    return sorted(packages, key=get_preference, reverse=True)


@lru_cache(maxsize=None)
def _conda_search(
    requirement: str,
    project: CondaProject,
    channels: tuple[str],
) -> list[CondaCandidate]:
    """
    Search conda candidates for a requirement
    :param requirement: requirement
    :param project: PDM project
    :param channels: requirement channels
    :return: list of conda candidates
    """
    config = project.conda_config
    command = config.command("search")
    if not project.virtual_packages:
        project.virtual_packages = conda_virtual_packages(project)

    command.append(requirement)
    for c in channels:
        command.extend(["-c", c])
    if channels:
        command.append("--override-channels")
    command.append("--json")
    try:
        result = run_conda(command)
    except RequirementError as e:
        if "PackagesNotFoundError:" in str(e):
            result = dict()
        else:
            raise

    candidates = []
    if config.runner == CondaRunner.CONDA:
        packages = result.get(parse_requirement(f"conda:{requirement}").name, [])
    else:
        packages = result.get("result", dict()).get("pkgs", [])

    for p in _sort_packages(packages):
        dependencies = p.get("depends", [])
        valid_candidate = True
        for d in dependencies:
            if d.startswith("__"):
                d = parse_requirement(f"conda:{d}")
                if not any(d.is_compatible(v) for v in project.virtual_packages):
                    valid_candidate = False
                    break
        if valid_candidate:
            package_channel = urlparse(p["channel"]).path
            for c in channels:
                if c in package_channel:
                    p["channel"] = c
                    break
            if "defaults" in channels and p["channel"].startswith("http"):
                p["channel"] = "defaults"

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
        requirement = requirement.as_line(with_build_string=True, conda_compatible=True).replace(" ", "=")
    if "::" in requirement:
        channel, requirement = requirement.split("::", maxsplit=1)
    channels = [channel] if channel else project.conda_config.channels
    if not channels:
        project.core.ui.echo(f"No channel specified for searching [success]{requirement}[/]", verbosity=Verbosity.DEBUG)
    return _conda_search(requirement, project, tuple(channels))


def update_requirements(requirements: list[Requirement], conda_packages: dict[str, CondaCandidate]):
    """
    Update requirements list with conda_packages
    :param requirements: requirements list
    :param conda_packages: conda packages
    """
    repeated_packages: dict[str, int] = dict()
    for i, requirement in enumerate(requirements):
        if (name := requirement.conda_name) in conda_packages and not isinstance(requirement, CondaRequirement):
            requirement.name = requirement.conda_name
            requirements[i] = parse_requirement(f"conda:{requirement.as_line()}")
        repeated_packages[name] = repeated_packages.get(name, 0) + 1
    to_remove = []
    for r in requirements:
        if repeated_packages.get(r.name, 1) > 1:
            to_remove.append(r)
            repeated_packages.pop(r.name)
    for r in to_remove:
        requirements.remove(r)


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
    if config.installation_method == "copy":
        _copy = "copy"
        if config.runner == CondaRunner.MICROMAMBA:
            _copy = f"always-{_copy}"
        command.append(f"--{_copy}")

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
        if config.runner == CondaRunner.MICROMAMBA:
            command.append("--no-prune")
        elif config.runner == CondaRunner.MAMBA:
            command[0] = "conda"
        command.append("--force")
    if dry_run:
        command.append("--dry-run")
    if isinstance(packages, str):
        packages = [packages]
    command.extend(packages)
    command.append("--json")

    _conda_install(project, command, verbose=verbose)


def not_initialized_warning(project):
    project.core.ui.echo(
        "[warning]Tried to execute a conda command but no pdm-conda configs were found on pyproject.toml.[/]",
    )


def conda_virtual_packages(project: CondaProject) -> set[CondaRequirement]:
    """
    Get conda virtual packages
    :param project: PDM project
    :return: set of virtual packages
    """
    config = project.conda_config
    virtual_packages = set()
    if config.is_initialized:
        info = run_conda(config.command("info") + ["--json"])
        if config.runner != CondaRunner.MICROMAMBA:
            _virtual_packages = {"=".join(p) for p in info["virtual_pkgs"]}
        else:
            _virtual_packages = set(info["virtual packages"])

        virtual_packages = {parse_requirement(f"conda:{p.replace('=', '==', 1)}") for p in _virtual_packages}
    else:
        not_initialized_warning(project)
    return virtual_packages


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
    else:
        not_initialized_warning(project)
    return distributions
