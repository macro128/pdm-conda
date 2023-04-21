import contextlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from pdm import termui
from pdm.cli.commands.venv.backends import VirtualenvCreateError
from pdm.exceptions import (
    InstallationError,
    PdmException,
    RequirementError,
    UninstallError,
)
from pdm.models.setup import Setup
from pdm.termui import Verbosity

from pdm_conda.models.candidates import CondaCandidate, parse_channel
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


class CondaResolutionError(PdmException):
    pass


@contextlib.contextmanager
def _optional_temporary_file(environment: dict | list):
    """
    If environment contains data then creates temporary file else yield None
    :param environment: environment data
    :return: Temporary file or None
    """
    if environment:
        with NamedTemporaryFile(mode="w+", suffix=".yml" if isinstance(environment, dict) else ".lock") as f:
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
    :param environment: environment or lockfile data
    :return: conda command response
    """
    lockfile = environment.get("lockfile", [])
    with _optional_temporary_file(lockfile or environment) as f:
        if lockfile or environment:
            if lockfile:
                f.writelines(lockfile)
            elif environment:
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
            cmd = cmd + ["--file", f.name]
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


def sort_candidates(project: CondaProject, packages: list[CondaCandidate]) -> Iterable[CondaCandidate]:
    """
    Sort candidates following mamba specification
    (https://mamba.readthedocs.io/en/latest/advanced_usage/package_resolution.html).
    :param project: PDM project
    :param packages: list of conda candidates
    :return: sorted conda candidates
    """
    if len(packages) <= 1:
        return packages
    channels_sorter = _get_channel_sorter(project.platform, tuple(project.conda_config.channels))

    def get_preference(candidate: CondaCandidate):
        return (
            not candidate.track_feature,
            candidate.version,
            candidate.build_number,
            -channels_sorter.get_priority(candidate.channel or ""),
            candidate.timestamp,
        )

    return sorted(packages, key=get_preference, reverse=True)


def _parse_candidates(project: CondaProject, packages: list[dict], requirement=None) -> list[CondaCandidate]:
    """
    Convert conda packages to candidates
    :param project: PDM project
    :param packages: conda packages
    :param requirement: requirement linked to packages
    :return: list of candidates
    """
    candidates = []
    for p in packages:
        dependencies = p.get("depends", None) or []
        valid_candidate = True
        for d in dependencies:
            if d.startswith("__"):
                d = parse_requirement(f"conda:{d}")
                if not any(d.is_compatible(v) for v in project.virtual_packages):
                    valid_candidate = False
                    break
        if valid_candidate:
            candidates.append(CondaCandidate.from_conda_package(p, requirement))

    return candidates


def _ensure_channels(
    project: CondaProject,
    channels: list[str],
    log_message: str = "No channels specified, using defaults if exist.",
) -> list[str]:
    """
    Ensure channels and if empty use defaults
    :param project: PDM project
    :param channels: channels to validate
    :param log_message: log message to display if using defaults
    :return: list of channels
    """
    channels = channels or project.conda_config.channels
    if not channels:
        project.core.ui.echo(log_message, verbosity=Verbosity.DEBUG)
        channels.append("defaults")

    return list(dict.fromkeys(channels))


@lru_cache(maxsize=None)
def _conda_search(
    project: CondaProject,
    requirement: str,
    channels: tuple[str],
) -> list[dict]:
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

    if config.runner == CondaRunner.CONDA:
        packages = result.get(parse_requirement(f"conda:{requirement}").name, [])
    else:
        packages = result.get("result", dict()).get("pkgs", [])
    return packages


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
    _requirement = requirement
    if isinstance(_requirement, CondaRequirement):
        channel = channel or _requirement.channel
        _requirement = _requirement.as_line(with_build_string=True, conda_compatible=True).replace(" ", "=")
    if "::" in _requirement:
        channel, _requirement = _requirement.split("::", maxsplit=1)
    if isinstance(requirement, str):
        requirement = parse_requirement(f"conda::{requirement}")
    channels = _ensure_channels(
        project,
        [channel] if channel else [],
        f"No channel specified for searching [req]{requirement}[/] using defaults if exist.",
    )
    packages = _conda_search(project, _requirement, tuple(channels))
    return _parse_candidates(project, packages, requirement)


def conda_create(
    project: CondaProject,
    requirements: list[CondaRequirement],
    channels: list[str] | None = None,
    prefix: Path | str | None = None,
    name: str = "",
    dry_run: bool = False,
) -> dict[str, list[CondaCandidate]]:
    """
    Creates environment using conda
    :param project: PDM project
    :param requirements: conda requirements
    :param channels: requirement channels
    :param prefix: environment prefix
    :param name: environment name
    :param dry_run: don't install if dry run
    """
    config = project.conda_config
    if not config.is_initialized:
        raise VirtualenvCreateError("Error creating environment, no pdm-conda configs were found on pyproject.toml.")
    candidates = dict()
    channels = channels or []
    for req in requirements:
        if req.channel:
            channels.append(req.channel)
    channels = _ensure_channels(
        project,
        channels,
        "No channels specified for creating environment, using defaults if exist.",
    )
    command = config.command("create")
    command.append("--json")
    if prefix is not None:
        command.extend(["--prefix", str(prefix)])
    elif name:
        command.extend(["--name", name])
    else:
        raise VirtualenvCreateError("Error creating environment, name or prefix must be specified.")

    if dry_run:
        command.append("--dry-run")

    for req in requirements:
        command.append(req.as_line(with_build_string=True, conda_compatible=True, with_channel=True).replace(" ", "="))

    if channels:
        for c in channels:
            command.extend(["-c", c])
        command.append("--override-channels")

    result = run_conda(
        command,
        exception_cls=CondaResolutionError if dry_run else VirtualenvCreateError,
        exception_msg=f"Error resolving requirements with {config.runner}" if dry_run else "Error creating environment",
    )

    actions = result.get("actions", dict())
    fetch_packages = {pkg["name"]: pkg for pkg in actions.get("FETCH", [])}
    packages = actions.get("LINK", [])
    for i, pkg in enumerate(packages):
        pkg = fetch_packages.get(pkg["name"], pkg)
        if any(True for n in ("constrains", "depends") if n not in pkg):
            pkg = conda_search(
                project,
                f'{pkg["name"]}={pkg["version"]}={pkg["build_string"]}',
                parse_channel(pkg["channel"]),
            )
        packages[i] = pkg

    _requirements = {req.conda_name: req for req in requirements}
    for pkg in packages:
        # if is list of candidates then it comes from search
        if isinstance(pkg, list):
            if pkg:
                candidates[pkg[0].name] = pkg
        else:
            name = pkg["name"]
            candidates[name] = _parse_candidates(
                project,
                packages=[pkg],
                requirement=_requirements.get(name, None),
            )
    return candidates


def _conda_install(
    command: list[str],
    packages: str | list[str] | None = None,
    exception_cls: type[PdmException] = InstallationError,
    dry_run: bool = False,
    explicit: bool = False,
):
    if isinstance(packages, str):
        packages = [packages]
    if not packages:
        raise exception_cls(f"No packages used for {' '.join(command[:3])} command.")
    if explicit:
        packages.insert(0, "@EXPLICIT")
    else:
        command.extend(packages)
    if dry_run:
        command.append("--dry-run")
    kwargs: dict = dict()
    if explicit:
        kwargs["lockfile"] = packages
    run_conda(command + ["--json"], **kwargs)


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

    _conda_install(command, packages, dry_run=dry_run, explicit=True)


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

    _conda_install(command, packages, dry_run=dry_run, exception_cls=UninstallError)


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
        res["channels"] = [parse_channel(channel) for channel in (info["channels"] or [])]
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
