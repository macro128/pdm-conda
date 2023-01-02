import dataclasses
import functools
from dataclasses import dataclass, field
from typing import Any

from pdm.models.markers import get_marker
from pdm.models.requirements import (
    PackageRequirement,
    Requirement,
    T,
    parse_requirement,
)
from pdm.models.setup import Setup
from unearth import Link


@dataclass
class CondaPackage:
    name: str
    version: str
    url: Link
    _dependencies: list[str] = field(repr=False)
    dependencies: list["CondaRequirement"] = field(
        init=False,
        default_factory=lambda: [],
    )
    req: "CondaRequirement" = field(init=False, repr=False)
    requires_python: str | None = None

    def __post_init__(self):
        self.req = parse_requirement(self.name, conda_package=self)

    @property
    def distribution(self):
        return Setup(
            name=self.name,
            summary="",
            version=self.version,
            install_requires=[d.as_line() for d in self.dependencies]
            if self.dependencies
            else self._dependencies,
            python_requires=self.requires_python,
        ).as_dist()

    def load_dependencies(self, packages: dict[str, "CondaPackage"]):
        self.dependencies = []
        for dependency in self._dependencies:
            name = dependency.split(" ", maxsplit=1)[0]
            if name in packages:
                self.dependencies.append(packages[name].req)


@dataclasses.dataclass(eq=False)
class CondaRequirement(Requirement):
    url: str = ""
    link: Link | None = None
    channel: str | None = None
    package: CondaPackage | None = None

    @property
    def project_name(self) -> str | None:
        return self.name

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        if (link := kwargs.get("link", None)) is not None:
            kwargs["url"] = link.url
        kwargs.pop("conda_managed", None)
        return super().create(**kwargs)

    def as_line(self) -> str:
        channel = f"{self.channel}::" if self.channel else ""
        return f"{channel}{self.project_name}{self.specifier}{self._format_marker()}"


def wrap_from_req_dict(func):
    @functools.wraps(func)
    def wrapper(name, req_dict):
        if isinstance(req_dict, dict) and req_dict.get("conda_managed", False):
            return CondaRequirement.create(name=name, **req_dict)

        return func(name=name, req_dict=req_dict)

    return wrapper


def wrap_parse_requirement(func):
    @functools.wraps(func)
    def wrapper(
        line: str,
        editable: bool = False,
        conda_managed: bool = False,
        conda_package: CondaPackage | None = None,
    ):
        if conda_managed or conda_package is not None:
            channel = None
            if "::" in line:
                channel, line = line.split("::", maxsplit=1)
            if conda_package is not None:
                return CondaRequirement.create(
                    name=conda_package.name,
                    version=f"=={conda_package.version}",
                    link=conda_package.url,
                    package=conda_package,
                    channel=channel,
                )
            else:
                package_req = PackageRequirement(line)  # type: ignore
                return CondaRequirement.create(
                    name=package_req.name,
                    specifier=package_req.specifier,
                    marker=get_marker(package_req.marker),
                    channel=channel,
                    url=package_req.url or "",
                )
        return func(line=line, editable=editable)

    return wrapper


if not hasattr(Requirement, "_patched"):
    setattr(Requirement, "_patched", True)
    Requirement.from_req_dict = wrap_from_req_dict(Requirement.from_req_dict)
    parse_requirement = wrap_parse_requirement(parse_requirement)
