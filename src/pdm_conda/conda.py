from __future__ import annotations

import contextlib
import json
import re
import subprocess
from functools import cache
from pathlib import Path
from shutil import which
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

from pdm.cli.commands.venv.backends import VirtualenvCreateError
from pdm.exceptions import InstallationError, PdmException, RequirementError, UninstallError
from pdm.models.finder import ReverseVersion
from pdm.models.setup import Setup
from pdm.termui import Verbosity

from pdm_conda import logger
from pdm_conda.models.candidates import CondaCandidate, parse_channel
from pdm_conda.models.conda import ChannelSorter
from pdm_conda.models.config import CondaRunner
from pdm_conda.models.requirements import CondaRequirement, parse_conda_version, parse_requirement
from pdm_conda.models.setup import CondaSetupDistribution
from pdm_conda.utils import normalize_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pdm_conda.project import CondaProject

_conda_response_packages_res = [
    re.compile(r"(nothing provides( requested)?|^.(\s+.)?─)\s+(?P<package>\S+)"),
    re.compile(r"(nothing provides .* needed by)\s+(?P<package>.+)-\d+\.\w+\.\w+-.+$"),
]


class CondaExecutionError(PdmException):
    def __init__(self, *args, data: dict | None = None):
        super().__init__(*args)
        self.data = data or {}
        self.message = self.data.get("message", "")


class CondaResolutionError(CondaExecutionError):
    def __init__(self, *args, data: dict | None = None):
        super().__init__(*args, data=data)
        self.packages: list = self.data.get("packages", [])


class CondaSearchError(CondaExecutionError):
    pass


class CondaRunnerNotFoundError(CondaExecutionError):
    pass


@contextlib.contextmanager
def _optional_temporary_file(environment: dict | list):
    """If environment contains data then creates temporary file else yield None.

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
    exception_cls: type[PdmException] = CondaExecutionError,
    exception_msg: str = "Error locking dependencies",
    **environment,
) -> dict:
    """Optionally creates temporary environment file and run conda command.

    :param cmd: conda command
    :param exception_cls: exception to raise on error
    :param exception_msg: base message to show on error
    :param environment: environment or lockfile data
    :return: conda command response
    """
    executable = which(cmd[0])
    if executable is None:
        raise CondaRunnerNotFoundError(f"Conda runner {cmd[0]} not found.")

    lockfile = environment.get("lockfile", [])
    with _optional_temporary_file(lockfile or environment) as f:
        if lockfile or environment:
            if lockfile:
                f.write("\n".join(lockfile))
            elif environment:
                for name, options in environment.items():
                    if options:
                        f.write(f"{name}:")
                        if isinstance(options, str):
                            f.write(f" {options}\n")
                            continue

                        f.write("\n")
                        for v in options:
                            f.write(f"  - {v}\n")
            f.seek(0)
            cmd += ["--file", f.name]
        logger.debug(f"cmd: {' '.join(cmd)}")
        if environment:
            logger.debug(f"env: {environment}")
        process = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if "--json" in cmd:
        try:
            out = process.stdout.strip()
            if not out.startswith("{") and not out.startswith("["):
                out = "{" + out.split("{")[-1]

            response = json.loads(out)
        except json.JSONDecodeError:
            response = {}
    else:
        response = {}
        msg = f"{process.stdout}\n" if process.stdout else ""
        if process.stderr:
            msg += process.stderr
        if msg:
            response["message"] = msg
    try:
        process.check_returncode()
    except subprocess.CalledProcessError as e:
        msg = ""
        if exception_msg:
            msg = f"{exception_msg}\n"
        kwargs = {}
        if isinstance(response, dict) and not response.get("success", False):
            if err := response.get(
                "solver_problems",
                response.get("error", response.get("message", f"{process.stderr}\n{process.stdout}")),
            ):
                if isinstance(err, str):
                    err = [err]
                msg += "\n".join(err)
            if exception_cls == CondaResolutionError:
                if "message" not in response:
                    response["message"] = process.stdout or process.stderr
                kwargs["data"] = response
        else:
            msg += process.stderr
        if environment:
            msg += f"\n{environment}"
        raise exception_cls(msg, **kwargs) from e
    return response


@cache
def _get_channel_sorter(platform: str, channels: tuple[str]) -> ChannelSorter:
    """Get channel sorter.

    :param channels: list of conda channels used to determine priority
    :param platform: env platform
    :return: channel sorter
    """
    return ChannelSorter(platform, channels)


def sort_candidates(
    project: CondaProject,
    packages: list[CondaCandidate],
    minimal_version: bool,
) -> Iterable[CondaCandidate]:
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
            ReverseVersion(candidate.version) if minimal_version else candidate.version,
            candidate.build_number,
            -channels_sorter.get_priority(candidate.channel or ""),
            candidate.timestamp,
        )

    return sorted(packages, key=get_preference, reverse=True)


def _parse_candidates(project: CondaProject, packages: list[dict], requirement=None) -> list[CondaCandidate]:
    """Convert conda packages to candidates.

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
    """Ensure channels and if empty use defaults.

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


@cache
def _conda_search(
    project: CondaProject,
    requirement: str,
    channels: tuple[str],
) -> list[dict]:
    """Search conda candidates for a requirement.

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
            result = {}
        else:
            raise

    if config.runner == CondaRunner.CONDA:
        packages = result.get(parse_requirement(f"conda:{requirement}").name, [])
    else:
        packages = result.get("result", {}).get("pkgs", [])
    return packages


def conda_search(
    project: CondaProject,
    requirement: CondaRequirement | str,
    channel: str | None = None,
) -> list[CondaCandidate]:
    """Search conda candidates for a requirement.

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
        requirement = parse_requirement(f"conda:{requirement}")
    channels = _ensure_channels(
        project,
        [channel] if channel else [],
        f"No channel specified for searching [req]{requirement}[/] using defaults if exist.",
    )
    packages = _conda_search(project, _requirement, tuple(channels))
    return _parse_candidates(project, packages, requirement)


def conda_create(
    project: CondaProject,
    requirements: Iterable[CondaRequirement],
    channels: list[str] | None = None,
    prefix: Path | str | None = None,
    name: str = "",
    dry_run: bool = False,
    fetch_candidates: bool = True,
) -> dict[str, list[CondaCandidate]]:
    """Creates environment using conda.

    :param project: PDM project
    :param requirements: conda requirements
    :param channels: requirement channels
    :param prefix: environment prefix
    :param name: environment name
    :param dry_run: don't install if dry run
    :param fetch_candidates: if True ensure ensure candidates were fetched
    """
    config = project.conda_config
    if not config.is_initialized:
        raise VirtualenvCreateError("Error creating environment, no pdm-conda configs were found on pyproject.toml.")
    candidates = {}
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

    command += list(
        {
            req.as_line(with_build_string=True, conda_compatible=True, with_channel=True).replace(" ", "="): None
            for req in requirements
        },
    )

    if channels:
        for c in channels:
            command.extend(["-c", c])
        command.append("--override-channels")

    try:
        result = run_conda(
            command,
            exception_cls=CondaResolutionError if dry_run else VirtualenvCreateError,
            exception_msg=(
                f"Error resolving requirements with {config.runner}" if dry_run else "Error creating environment"
            ),
        )
    except CondaResolutionError as err:
        if not err.packages:
            failed_packages = set()
            for line in err.message.split("\n"):
                for pat in _conda_response_packages_res:
                    if (match := pat.search(line)) is not None:
                        failed_packages.add(match.group("package"))
            err.packages = list(failed_packages)
        raise
    if fetch_candidates:
        actions = result.get("actions", {})
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
                    requirement=_requirements.get(name),
                )
    return candidates


def conda_env_remove(project: CondaProject, prefix: Path | str | None = None, name: str = "", dry_run: bool = False):
    """Removes environment using conda.

    :param project: PDM project
    :param prefix: environment prefix
    :param name: environment name
    :param dry_run: don't install if dry run
    """
    config = project.conda_config
    if not config.is_initialized:
        raise VirtualenvCreateError("Error removing environment, no pdm-conda configs were found on pyproject.toml.")
    command = config.command("env remove")
    command.append("--json")
    if prefix is not None:
        command += ["--prefix", str(prefix)]
    elif name:
        command += ["--name", name]
    else:
        raise VirtualenvCreateError("Error removing environment, name or prefix must be specified.")

    if dry_run:
        command.append("--dry-run")

    run_conda(command, exception_cls=VirtualenvCreateError, exception_msg="Error removing environment")


def conda_env_list(project: CondaProject) -> list[Path]:
    """List Conda environments.

    :param project: PDM project
    :return: list of conda environments
    """
    config = project.conda_config
    command = config.command("env list")
    command.append("--json")
    environments = run_conda(command, exception_cls=CondaExecutionError, exception_msg="Error listing environments")
    return [Path(env) for env in environments.get("envs", [])]


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
    kwargs: dict = {}
    if explicit:
        kwargs["lockfile"] = packages
    run_conda(command + ["--json"], exception_cls=exception_cls, exception_msg="", **kwargs)


def conda_install(
    project: CondaProject,
    packages: str | list[str],
    dry_run: bool = False,
    no_deps: bool = False,
):
    """Install resolved packages using conda.

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
    """Uninstall resolved packages using conda.

    :param project: PDM project
    :param packages: resolved packages
    :param dry_run: don't uninstall if dry run
    :param no_deps: don't uninstall dependencies if true
    """
    config = project.conda_config

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
    """Get conda info containing virtual packages, default channels and packages.

    :param project: PDM project
    :return: dict with conda info
    """
    config = project.conda_config
    res: dict = {"virtual_packages": set(), "platform": "", "channels": []}
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
    """List conda installed packages.

    :param project: PDM project
    :return: packages distribution
    """
    config = project.conda_config
    distributions = {}
    if config.is_initialized:
        packages = run_conda(config.command("list") + ["--json"])
        for package in packages:
            if config.runner != CondaRunner.MICROMAMBA and package.get("platform", "") == "pypi":
                continue
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
