import re
from importlib.metadata import Distribution
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from pdm.models.candidates import Candidate, PreparedCandidate
from pdm.models.environment import Environment
from pdm.models.setup import Setup
from unearth import Link

from pdm_conda.models.requirements import (
    CondaRequirement,
    Requirement,
    as_conda_requirement,
    parse_conda_version,
    parse_requirement,
)
from pdm_conda.models.setup import CondaSetupDistribution


def parse_channel(channel_url: str) -> str:
    """
    Parse channel from channel url
    :param channel_url: channel url from package
    :return: channel
    """
    channel = urlparse(channel_url).path
    if channel.startswith("/"):
        channel = channel[1:]
    return channel


class CondaPreparedCandidate(PreparedCandidate):
    def __init__(self, candidate: Candidate, environment: Environment) -> None:
        super().__init__(candidate, environment)
        self.candidate = cast(CondaCandidate, self.candidate)  # type: ignore

    def get_dependencies_from_metadata(self) -> list[str]:
        # if conda candidate return already obtained dependencies
        return [d.as_line(as_conda=True, with_build_string=True) for d in self.candidate.dependencies]

    def prepare_metadata(self) -> Distribution:
        # if conda candidate get setup from package
        return self.candidate.distribution


class CondaCandidate(Candidate):
    def __init__(
        self,
        req: Requirement,
        name: str | None = None,
        version: str | None = None,
        link: Link | None = None,
        dependencies: list[str] | None = None,
        constrains: list[str] | None = None,
        build_string: str | None = None,
        build_number: int = 0,
        timestamp: int = 0,
        channel: str | None = None,
        track_feature: str = "",
    ):
        super().__init__(req, name, version, link)
        self._req = cast(CondaRequirement, req)  # type: ignore
        self._preferred = None
        self._prepared: CondaPreparedCandidate | None = None
        self.dependencies: list[CondaRequirement] = [
            cast(CondaRequirement, parse_requirement(f"conda:{r}")) for r in (dependencies or [])
        ]
        self.constrains: dict[str, CondaRequirement] = dict()
        self.hashes = {self.link: f"{self.link.hash_name}:{self.link.hash}"}
        for r in constrains or []:
            c = cast(CondaRequirement, parse_requirement(f"conda:{r}"))
            self.constrains[str(c.conda_name)] = c
        self.build_string = build_string
        self.build_number = build_number
        self.timestamp = timestamp
        self.channel = channel
        self.track_feature = track_feature
        self.conda_version = version
        self.version = parse_conda_version(version)

    @property
    def req(self):
        return self._req

    @req.setter
    def req(self, value):
        if isinstance(value, CondaRequirement):
            self._req = value

    @property
    def distribution(self):
        return CondaSetupDistribution(
            Setup(
                name=self.name,
                summary="",
                version=self.version,
                install_requires=self.dependencies_lines,
                python_requires=self.requires_python,
            ),
        )

    @property
    def dependencies_lines(self):
        return [dep.as_line(as_conda=True, with_build_string=True, with_channel=True) for dep in self.dependencies]

    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        result = super().as_lockfile_entry(project_root)
        result["conda_managed"] = True
        if self.link is None:
            raise ValueError("Uninitialized conda requirement")
        result["channel"] = self.channel
        if self.build_string is not None:
            result["build_string"] = self.build_string
        result["build_number"] = self.build_number
        if self.track_feature:
            result["track_feature"] = self.track_feature
        if self.constrains:
            result["constrains"] = [c.as_line(with_build_string=True) for c in self.constrains.values()]
        result["version"] = self.conda_version
        return result

    def prepare(self, environment: Environment) -> CondaPreparedCandidate:
        """Prepare the candidate for installation."""
        if self._prepared is None:
            self._prepared = CondaPreparedCandidate(self, environment)
        return self._prepared

    @classmethod
    def from_lock_package(cls, package: dict) -> "CondaCandidate":
        """
        Create conda candidate from lockfile package.
        :param package: lockfile package
        :return: conda candidate
        """
        requires_python = package.get("requires_python", "")
        dependencies = package.get("dependencies", [])
        if requires_python:
            dependencies.append(f"python {requires_python}")
        return CondaCandidate.from_conda_package(package | {"depends": dependencies})

    @classmethod
    def from_conda_package(cls, package: dict, requirement: CondaRequirement | None = None) -> "CondaCandidate":
        """
        Create conda candidate from conda package.
        :param package: conda package
        :param requirement: conda requirement associated with conda package
        :return: conda candidate
        """
        dependencies: list = package["depends"] or []
        requires_python = None
        to_delete = []
        for d in dependencies:
            if d.startswith("__"):
                to_delete.append(d)
            elif match := re.match(r"python( .+|$)", d):
                to_delete.append(d)
                if requires_python is None:
                    requires_python = match.group(1).strip().split(" ")[0] or "*"
        for d in to_delete:
            dependencies.remove(d)
        hashes = {h: package[h] for h in ["md5"] if h in package}
        url = package["url"]
        for k, v in hashes.items():
            url += f"#{k}={v}"
        name, version = package["name"], package["version"]
        build_string = package.get("build", package.get("build_string", ""))
        channel = parse_channel(package["channel"])
        if requirement is not None:
            requirement = cast(CondaRequirement, as_conda_requirement(requirement))
            requirement.version_mapping.update({parse_conda_version(version): version})
        else:
            requirement = parse_requirement(f"conda:{name} {version} {build_string}")

        assert requirement is not None
        requirement.is_python_package = requires_python is not None
        return CondaCandidate(
            req=requirement,
            name=name,
            version=version,
            link=Link(
                url,
                requires_python=requires_python,
                comes_from=channel,
            ),
            channel=channel,
            dependencies=dependencies,
            constrains=package.get("constrains", None) or [],
            build_string=build_string,
            build_number=package.get("build_number", 0),
            track_feature=package.get("track_feature", ""),
            timestamp=package.get("timestamp", 0),
        )

    def __str__(self) -> str:
        if self.req.is_named:
            return f"{self.name}@{self.conda_version}"
        return super().__str__()

    def format(self) -> str:
        """Format for output."""
        return f"[req]{self.name}[/] [warning]{self.conda_version}[/]"
