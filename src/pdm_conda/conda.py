import contextlib
import json
import subprocess
from functools import lru_cache
from tempfile import NamedTemporaryFile
from typing import Iterable
from urllib.parse import urlparse

from packaging.version import Version
from pdm import termui
from pdm.exceptions import PdmException, RequirementError
from pdm.models.setup import Setup
from pdm.termui import Verbosity

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.conda import ChannelSorter
from pdm_conda.models.config import CondaRunner
from pdm_conda.models.requirements import (
    CondaRequirement,
    parse_conda_version,
    parse_requirement,
)
from pdm_conda.models.setup import CondaSetupDistribution
from pdm_conda.project import CondaProject
from pdm_conda.utils import normalize_name

logger = termui.logger


@contextlib.contextmanager
def _optional_temporary_file(environment: dict):
    """
    If environment contains data then creates temporary file else yield None
    :param environment: environment data
    :return: Temporary file or None
    """
    if environment:
        with NamedTemporaryFile(mode="w+", suffix=".yml") as f:
            yield f
    else:
        yield


def run_conda(
    cmd,
    exception_cls: type[PdmException] = RequirementError,
    exception_msg: str = "Error locking dependencies",
    **environment,
) -> dict:
    """
    Optionally creates temporary environment file and run conda command
    :param cmd: conda command
    :param exception_cls: exception to raise on error
    :param exception_msg: base message to show on error
    :param environment: environment data
    :return: conda command response
    """
    with _optional_temporary_file(environment) as f:
        if environment:
            for name, options in environment.items():
                if options:
                    f.write(f"{name}:")
                    if isinstance(options, str):
                        f.write(f" {options}\n")
                        continue
                    else:
                        f.write("\n")
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
        response = {"message": f"{process.stdout}\n{process.stderr}"}
    try:
        process.check_returncode()
    except subprocess.CalledProcessError as e:
        msg = f"{exception_msg}\n"
        if isinstance(response, dict) and not response.get("success", False):
            if err := response.get("solver_problems", response.get("error", response.get("message", process.stderr))):
                if isinstance(err, str):
                    err = [err]
                msg += "\n".join(err)
        else:
            msg += process.stderr
        if environment:
            msg += f"\n{environment}"
        raise exception_cls(msg) from e
    return response


@lru_cache(maxsize=None)
def _get_channel_sorter(platform: str, channels: tuple[str]) -> ChannelSorter:
    """
    Get channel sorter
    :param channels: list of conda channels used to determine priority
    :param platform: env platform
    :return: channel sorter
    """
    return ChannelSorter(platform, channels)


def _sort_packages(packages: list[dict], channels: Iterable[str], platform: str) -> Iterable[dict]:
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

    channels_sorter = _get_channel_sorter(platform, tuple(channels))

    def get_preference(package):
        return (
            not package.get("track_feature", ""),
            Version(parse_conda_version(package["version"], inverse=package.get("name", "") == "openssl")),
            package.get("build_number", 0),
            -channels_sorter.get_priority(package["channel"]),
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
    project: CondaProject,
    requirement: str,
    channels: tuple[str],
) -> list[CondaCandidate]:
    """
    Search conda candidates for a requirement
    :param project: PDM project
    :param requirement: requirement
    :param channels: requirement channels
    :return: list of conda candidates
    """
    config = project.conda_config
    command = config.command("search")
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

    for p in packages:
        p["channel"] = _parse_channel(p["channel"])

    for p in _sort_packages(packages, channels, project.platform):
        dependencies = p.get("depends", [])
        valid_candidate = True
        for d in dependencies:
            if d.startswith("__"):
                d = parse_requirement(f"conda:{d}")
                if not any(d.is_compatible(v) for v in project.virtual_packages):
                    valid_candidate = False
                    break
        if valid_candidate:
            candidates.append(CondaCandidate.from_conda_package(p))

    return candidates


def conda_search(
    project: CondaProject,
    requirement: CondaRequirement | str,
    channel: str | None = None,
) -> list[CondaCandidate]:
    """
    Search conda candidates for a requirement
    :param project: PDM project
    :param requirement: requirement
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
        channels.append("defaults")

    # set defaults if exist
    try:
        idx = channels.index("defaults")
        channels = channels[:idx] + project.default_channels + channels[idx + 1 :]
    except ValueError:
        pass

    return _conda_search(requirement, project, tuple(channels))


def _conda_install(
    project: CondaProject,
    command: list[str],
    packages: str | list[str] | None = None,
    dry_run: bool = False,
):
    if isinstance(packages, str):
        packages = [packages]
    if packages:
        command.extend(packages)
    if dry_run:
        command.append("--dry-run")
    response = run_conda(command + ["--json"])
    project.core.ui.echo(response, verbosity=Verbosity.DEBUG)


def conda_install(
    project: CondaProject,
    packages: str | list[str],
    dry_run: bool = False,
    no_deps: bool = False,
):
    """
    Install resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param dry_run: don't install if dry run
    :param no_deps: don't install dependencies if true
    """
    config = project.conda_config
    command = config.command("install")
    if no_deps:
        command.append("--no-deps")
        if config.runner != CondaRunner.MICROMAMBA:
            command.append("--no-update-deps")

    if config.installation_method == "copy":
        _copy = "copy"
        if config.runner == CondaRunner.MICROMAMBA:
            _copy = f"always-{_copy}"
        command.append(f"--{_copy}")

    _conda_install(project, command, packages, dry_run=dry_run)


def conda_uninstall(
    project: CondaProject,
    packages: str | list[str],
    dry_run: bool = False,
    no_deps: bool = False,
):
    """
    Uninstall resolved packages using conda
    :param project: PDM project
    :param packages: resolved packages
    :param dry_run: don't uninstall if dry run
    :param no_deps: don't uninstall dependencies if true
    """
    config = project.conda_config

    with config.with_config(
        runner=CondaRunner.CONDA if no_deps and config.runner == CondaRunner.MAMBA else config.runner,
    ):
        command = config.command("remove")

    if no_deps:
        if config.runner == CondaRunner.MICROMAMBA:
            command.append("--no-prune")
        command.append("--force")

    _conda_install(project, command, packages, dry_run=dry_run)


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
    res: dict = dict(virtual_packages=set(), platform="", channels=[])
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
