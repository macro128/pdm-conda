import re
from importlib.metadata import Distribution
from pathlib import Path
from typing import Any, cast

from pdm.models.candidates import Candidate, PreparedCandidate
from pdm.models.environment import Environment
from pdm.models.setup import Setup
from unearth import Link

from pdm_conda.models.requirements import (
    CondaRequirement,
    Requirement,
    parse_requirement,
)
from pdm_conda.models.setup import CondaSetupDistribution


class CondaPreparedCandidate(PreparedCandidate):
    def __init__(self, candidate: Candidate, environment: Environment) -> None:
        super().__init__(candidate, environment)
        self.candidate = cast(CondaCandidate, self.candidate)  # type: ignore
        self.req = cast(CondaRequirement, self.req)  # type: ignore

    def get_dependencies_from_metadata(self) -> list[str]:
        # if conda candidate return already obtained dependencies
        return [d.as_line() for d in self.candidate.dependencies]

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
        build_string: str | None = None,
    ):
        super().__init__(req, name, version, link)
        # extract hash from link
        if link and link.hash is not None:
            self.hashes = {link: link.hash}
        self._req = cast(CondaRequirement, req)  # type: ignore
        self._preferred = None
        self._prepared: CondaPreparedCandidate | None = None
        self.dependencies = [parse_requirement(f"conda:{r}") for r in (dependencies or [])]
        self.build_string = build_string

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
                install_requires=[d.as_line() for d in self.dependencies],
                python_requires=self.requires_python,
            ),
        )

    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        result = super().as_lockfile_entry(project_root)
        result["conda_managed"] = True
        if self.req.channel is not None:
            result["channel"] = self.req.channel
        if self.link is None:
            raise ValueError("Uninitialized conda requirement")
        result["url"] = self.link.url
        if self.link.comes_from is not None:
            result["channel_url"] = self.link.comes_from
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
        return CondaCandidate.from_conda_package(
            package
            | {
                "channel": package.get("channel_url", None),
                "depends": dependencies,
                "build_string": None,
            },
        )

    @classmethod
    def from_conda_package(cls, package: dict) -> "CondaCandidate":
        """
        Create conda candidate from conda package.
        :param package: conda package
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
                    requires_python = match.group(1).strip() or None
        for d in to_delete:
            dependencies.remove(d)
        hashes = {h: package[h] for h in ["sha256", "md5"] if h in package}
        url = package["url"]
        for k, v in hashes.items():
            url += f"#{k}={v}"
        name, version = package["name"], package["version"]
        return CondaCandidate(
            req=parse_requirement(f"conda:{name} {version}"),
            name=name,
            version=version,
            link=Link(url, comes_from=package["channel"], requires_python=requires_python, hashes=hashes),
            dependencies=dependencies,
            build_string=package["build_string"],
        )
