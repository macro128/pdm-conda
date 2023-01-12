import dataclasses
import functools
import re
from typing import Any

from pdm._types import RequirementDict
from pdm.models.markers import get_marker
from pdm.models.requirements import NamedRequirement, PackageRequirement, Requirement, T
from pdm.models.requirements import parse_requirement as _parse_requirement

_conda_req_re = re.compile(r"conda:((\w+::)?.+)$")
_specifier_re = re.compile(r"[<>=~!].*")

_patched = False


@dataclasses.dataclass(eq=False)
class CondaRequirement(NamedRequirement):
    channel: str | None = None

    @property
    def project_name(self) -> str | None:
        return self.name

    @property
    def is_python_package(self) -> bool:
        return not self.requires_python

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        kwargs.pop("conda_managed", None)
        return super().create(**kwargs)

    def as_line(self, with_channel=False) -> str:
        channel = f"{self.channel}::" if with_channel and self.channel else ""
        return f"{channel}{self.project_name}{self.specifier}{self._format_marker()}"

    def _hash_key(self) -> tuple:
        return (
            self.key,
            frozenset(self.specifier),
        )

    def as_named_requirement(self) -> NamedRequirement:
        return NamedRequirement.create(name=self.name, marker=self.marker, specifier=self.specifier)


def wrap_from_req_dict(func):
    @functools.wraps(func)
    def wrapper(name: str, req_dict: RequirementDict) -> Requirement:
        if isinstance(req_dict, dict) and req_dict.get("conda_managed", False):
            return CondaRequirement.create(name=name, **req_dict)
        return func(name, req_dict)

    return wrapper


def parse_requirement(line: str, editable: bool = False) -> Requirement:
    m = _conda_req_re.match(line)
    if m is not None:
        if m is not None:
            line = m.group(1)
        channel = None
        if "::" in line:
            channel, line = line.split("::", maxsplit=1)
        if " " in line:
            name, version = line.split(" ", maxsplit=1)
            marker = ""
            if ";" in version:
                version, marker = line.split(";", maxsplit=1)
                marker = f";{marker}"
            for digit, s in re.findall(r"(\d)([a-z]+)", version):
                if s not in ("a", "b", "rc", "dev", "post"):
                    version = version.replace(f"{digit}{s}", digit)

            version = version.replace(",", " ")
            if not _specifier_re.match(version):
                version = f"=={version}"
            version = ",".join(v.strip() for v in version.split(" ") if _specifier_re.match(v))
            line = f"{name} {version} {marker}"
        prefix = ""
        if line.startswith("_"):
            prefix = "_"
            line = line[1:]

        package_req = PackageRequirement(line)  # type: ignore
        kwargs = dict(
            name=prefix + package_req.name,
            specifier=package_req.specifier,
            marker=get_marker(package_req.marker),
            channel=channel,
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
