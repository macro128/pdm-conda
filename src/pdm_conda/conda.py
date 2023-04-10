import contextlib
import json
import re
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


def _sort_packages(packages: list[dict], channels: Iterable[str], platform: str | None) -> Iterable[dict]:
    """
    Sort packages following mamba specification
    (https://mamba.readthedocs.io/en/latest/advanced_usage/package_resolution.html).
    :param packages: list of conda packages
    :param channels: list of conda channels used to determine priority
    :param platform: env platform
    :return: sorted conda packages
    """
    if len(packages) <= 1:
        return packages

    if not channels:
        channels = list(dict.fromkeys([p["channel"] for p in packages]))

    channels_priority: dict[str, tuple[list, list]] = dict()
    for channel in channels:
        parent_channel = channel.split("/")[0]
        _channels, _ = channels_priority.setdefault(parent_channel, ([], []))
        if not _channels and platform:
            _channels.append(f"{parent_channel}/{platform}")
        if "/" in channel and channel not in _channels:
            _channels.append(channel)

    max_priority = 0
    for parent_channel, (_channels, priority) in channels_priority.items():
        for channel in [rf"{parent_channel}/.*", f"{parent_channel}/noarch"]:
            if channel not in _channels:
                _channels.append(channel)
        priority.extend([max_priority + i * 100 for i in range(len(_channels))])
        max_priority += 1000
    channels_priority_cache = dict()

    def get_preference(package):
        channel = package["channel"]
        if channel not in channels_priority_cache:
            parent_channel = channel.split("/")[0]
            _channels, priority = channels_priority[parent_channel]
            for i, c in enumerate(_channels):
                if c == channel or re.match(c, channel):
                    channels_priority_cache[channel] = priority[i]
                    if c != channel:
                        priority[i] += 1
                    break
        return (
            not package.get("track_feature", ""),
            -channels_priority_cache.get(channel, 0),
            Version(parse_conda_version(package["version"], inverse=package.get("name", "") == "openssl")),
            package.get("build_number", 0),
            package.get("timestamp", 0),
        )

    return sorted(packages, key=get_preference, reverse=True)


@lru_cache(maxsize=None)
def _parse_channel(channel_url: str) -> str:
    """
    Parse channel from channel url
    :param channel_url: channel url from package
    :return: channel
    """
    channel = urlparse(channel_url).path
    if channel.startswith("/"):
        channel = channel[1:]
    return channel


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
    if project.virtual_packages is None or project.platform is None or project.default_channels is None:
        info = conda_info(project)
        project.virtual_packages = info["virtual_packages"]
        project.platform = info["platform"]
        project.default_channels = info["channels"]

    command.append(requirement)
    channels = channels or project.default_channels
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

    for p in packages:
        p["channel"] = _parse_channel(p["channel"])

    for p in _sort_packages(packages, channels, project.platform):
        dependencies = p.get("depends", [])
        valid_candidate = True
        for d in dependencies:
            if d.startswith("__"):
                d = parse_requirement(f"conda:{d}")
                if not any(d.is_compatible(v) for v in project.virtual_packages):  # type: ignore
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
        requirement = requirement.as_line(with_build_string=True, conda_compatible=True).replace(" ", "=")
    if "::" in requirement:
        channel, requirement = requirement.split("::", maxsplit=1)
    channels = [channel] if channel else project.conda_config.channels
    if not channels:
        project.core.ui.echo(
            f"No channel specified for searching [success]{requirement}[/] using defaults if exist.",
            verbosity=Verbosity.DEBUG,
        )
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


def conda_info(project: CondaProject) -> dict:
    """
    Get conda info containing virtual packages, default channels and packages
    :param project: PDM project
    :return: dict with conda info
    """
    config = project.conda_config
    res: dict = dict(virtual_packages=set(), platform=None, channels=[])
    if config.is_initialized:
        info = run_conda(config.command("info") + ["--json"])
        if config.runner != CondaRunner.MICROMAMBA:
            virtual_packages = {"=".join(p) for p in info["virtual_pkgs"]}
        else:
            virtual_packages = set(info["virtual packages"])

        res["virtual_packages"] = {parse_requirement(f"conda:{p.replace('=', '==', 1)}") for p in virtual_packages}
        res["platform"] = info["platform"]
        res["channels"] = [_parse_channel(channel) for channel in (info["channels"] or [])]
    else:
        not_initialized_warning(project)
    return res


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
