import json
import subprocess
from functools import lru_cache
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from pdm.exceptions import RequirementError
from pdm.models.setup import Setup

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
    channels: tuple[str],
) -> list[CondaCandidate]:
    """
    Search conda candidates for a requirement
    :param requirement: requirement
    :param project: PDM project
    :param channels: requirement channels
    :return: list of conda candidates
    """
    command = project.conda_config.command("search")
    if not project.virtual_packages:
        project.virtual_packages = conda_virtual_packages(project)

    command.append(requirement)
    for c in channels:
        command.extend(["-c", c])
    command.append("--json")
    result = run_conda(command)
    candidates = []
    # sort values per build number (greater first)
    packages = result.get("result", dict()).get("pkgs", [])
    _packages: dict[tuple, list] = dict()
    for p in packages:
        name = p["name"]
        version = p["version"]
        k = (name, version)
        _packages.setdefault(k, []).append(p)
    packages = []
    for ps in _packages.values():
        packages.extend(sorted(reversed(ps), key=lambda p: p["build_number"], reverse=True))

    for p in packages:
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
    channels = [channel] if channel else (project.conda_config.channels or ["defaults"])
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
        if config.runner == "micromamba":
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
        _prune = "no-prune"
        if config.runner == "conda":
            _prune = "force-remove"
        command.append(f"--{_prune}")
    if dry_run:
        command.append("--dry-run")
    if isinstance(packages, str):
        packages = [packages]
    command.extend(packages)
    command.append("--json")

    _conda_install(project, command, verbose=verbose)


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
        # todo: fix conda
        virtual_packages = {parse_requirement(f"conda:{p}") for p in info["virtual packages"]}
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

    return distributions
