import dataclasses
import functools
import re
from dataclasses import dataclass, field
from typing import Any, cast

from pdm._types import RequirementDict
from pdm.models.markers import get_marker
from pdm.models.requirements import NamedRequirement, PackageRequirement, Requirement, T
from pdm.models.requirements import parse_requirement as _parse_requirement
from pdm.models.setup import Setup
from unearth import Link

from pdm_conda.models.setup import CondaSetupDistribution

_conda_req_re = re.compile(r"conda:((\w+::)?.+)$")

_patched = False


@dataclass
class CondaPackage:
    name: str
    version: str
    link: Link
    full_dependencies: list[str] = field(repr=False, default_factory=list)
    dependencies: list["CondaRequirement"] = field(init=False, default_factory=list)
    req: "CondaRequirement" = field(init=False, repr=False)
    requires_python: str | None = None

    def __post_init__(self):
        self.req = cast(CondaRequirement, parse_requirement(self.name, conda_package=self))

    @property
    def distribution(self):
        return CondaSetupDistribution(
            Setup(
                name=self.name,
                summary="",
                version=self.version,
                install_requires=[d.as_line() for d in self.dependencies]
                if self.dependencies
                else self.full_dependencies,
                python_requires=self.requires_python,
            ),
        )

    def load_dependencies(self, packages: dict[str, "CondaPackage"]):
        self.dependencies = []
        for dependency in self.full_dependencies:
            if (match := re.search(r"([a-zA-Z0-9_\-]+)", dependency)) is not None:
                name = match.group(1)
                if name in packages:
                    self.dependencies.append(packages[name].req)


@dataclasses.dataclass(eq=False)
class CondaRequirement(NamedRequirement):
    url: str = ""
    link: Link | None = None
    channel: str | None = None
    package: CondaPackage | None = None

    @property
    def project_name(self) -> str | None:
        return self.name

    @property
    def is_python_package(self) -> bool:
        if self.package is None:
            return False
        return self.package.requires_python is not None

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        if (link := kwargs.get("link", None)) is not None:
            kwargs["url"] = link.url
        else:
            kwargs["link"] = Link(kwargs["url"])
        kwargs.pop("conda_managed", None)
        return super().create(**kwargs)

    def as_line(self) -> str:
        channel = f"{self.channel}::" if self.channel else ""
        return f"{channel}{self.project_name}{self.specifier}{self._format_marker()}"

    def as_named_requirement(self) -> NamedRequirement:
        return NamedRequirement.create(name=self.name, marker=self.marker, specifier=self.specifier)


def wrap_from_req_dict(func):
    @functools.wraps(func)
    def wrapper(name: str, req_dict: RequirementDict) -> Requirement:
        if isinstance(req_dict, dict) and req_dict.get("conda_managed", False):
            return CondaRequirement.create(name=name, **req_dict)
        return func(name, req_dict)

    return wrapper


def parse_requirement(line: str, editable: bool = False, conda_package: CondaPackage | None = None) -> Requirement:
    m = _conda_req_re.match(line)
    if m is not None or conda_package is not None:
        if m is not None:
            line = m.group(1)
        channel = None
        if "::" in line:
            channel, line = line.split("::", maxsplit=1)
        if conda_package is not None:
            version = conda_package.version.removesuffix("g").strip()
            if not re.match(r"[<>=].*", version) and version:
                version = f"=={version}"
            kwargs = dict(
                name=conda_package.name,
                version=version,
                link=conda_package.link,
                package=conda_package,
                channel=channel,
            )
        else:
            package_req = PackageRequirement(line)  # type: ignore
            kwargs = dict(
                name=package_req.name,
                specifier=package_req.specifier,
                marker=get_marker(package_req.marker),
                channel=channel,
                url=package_req.url or "",
            )
        return CondaRequirement.create(**kwargs)

    return _parse_requirement(line=line, editable=editable)


if not _patched:
    from pdm.cli import actions
    from pdm.models import requirements

    setattr(Requirement, "from_req_dict", wrap_from_req_dict(Requirement.from_req_dict))
    setattr(actions, "parse_requirement", parse_requirement)
    setattr(requirements, "parse_requirement", parse_requirement)
    _patched = True
