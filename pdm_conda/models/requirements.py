import dataclasses
import re
from typing import Any

from packaging.specifiers import SpecifierSet
from pdm.models.requirements import NamedRequirement, Requirement, T
from pdm.models.requirements import parse_requirement as _parse_requirement
from pdm.models.requirements import strip_extras

from pdm_conda.mapping import conda_to_pypi, pypi_to_conda
from pdm_conda.utils import normalize_name

_conda_meta_req_re = re.compile(r"conda:([\w\-_]+::)?(.+)$")
_specifier_re = re.compile(r"([<>=~!]+)(.+)")
_conda_specifier_star_re = re.compile(r"([\w.]+)\*")
_conda_version_letter_re = re.compile(r"(\d)([a-z]+)")

_patched = False


def correct_specifier_star(match):
    res = match.group(1)
    if res.endswith("."):
        res += "0"
    return res


def parse_conda_version(version):
    def correct_conda_version(match):
        digit, letter_specifier = match.groups()
        if letter_specifier not in ("a", "b", "rc", "dev", "post"):
            letter_specifier = "." + "".join(str(ord(letter)) for letter in letter_specifier)
        return f"{digit}{letter_specifier}"

    return _conda_version_letter_re.sub(correct_conda_version, version)


@dataclasses.dataclass(eq=False)
class CondaRequirement(NamedRequirement):
    channel: str | None = None
    _is_python_package: bool = dataclasses.field(default=True, repr=False, init=False)
    version_mapping: dict = dataclasses.field(default_factory=dict, repr=False)
    mapping_excluded: bool = dataclasses.field(default=False, repr=False)
    build_string: str | None = None

    @property
    def conda_name(self) -> str | None:
        return self.name

    @property
    def is_python_package(self):
        return self._is_python_package

    @is_python_package.setter
    def is_python_package(self, value):
        self._is_python_package = value
        self.mapping_excluded = not value

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        kwargs.pop("conda_managed", None)
        if build_string := kwargs.get("build_string", None):
            kwargs["build_string"] = build_string.strip()

        return super().create(**kwargs)

    def as_line(self, as_conda: bool = False, with_channel=False, with_build_string=False) -> str:
        channel = f"{self.channel}::" if with_channel and self.channel else ""
        if as_conda:
            channel = f"conda:{channel}"
        specifier = ""
        for s in self.specifier:
            if specifier:
                specifier += ","
            specifier += f"{s.operator}{self.version_mapping.get(s.version, s.version)}"
        build_string = f" {self.build_string}" if with_build_string and self.build_string and specifier else ""
        return f"{channel}{self.conda_name}{specifier}{build_string}"

    def _hash_key(self) -> tuple:
        return (
            self.key,
            frozenset(self.specifier),
        )

    def as_named_requirement(self) -> NamedRequirement:
        return NamedRequirement.create(name=conda_to_pypi(self.name), specifier=self.specifier)


def remove_operator(version):
    return _specifier_re.sub(r"\2", version)


def parse_requirement(line: str, editable: bool = False) -> Requirement:
    if (match := _conda_meta_req_re.match(line)) is not None:
        version_mapping = dict()
        channel, line = match.groups()
        if channel:
            channel = channel[:-2]

        build_string = None
        if len(_line := line.split(" ")) == 3 or (len(_line) == 2 and _specifier_re.search(_line[0])):
            line = " ".join(_line[:-1])
            build_string = _line[-1]

        line = _conda_specifier_star_re.sub(correct_specifier_star, line)
        name = line
        version = ""
        if match := _specifier_re.search(line):
            name, version = line[: match.start(1)], line[match.start(1) :]
        elif " " in line:
            name, version = line.split(" ", maxsplit=1)
        version_and = version.split(",")
        for i, conda_version in enumerate(version_and):
            conda_version = conda_version.split("|")[0]
            if conda_version:
                if not _specifier_re.match(conda_version):
                    conda_version = f"=={conda_version}"
                version = parse_conda_version(conda_version)
                version_mapping[remove_operator(version)] = remove_operator(conda_version)
                version_and[i] = version
        req = CondaRequirement.create(
            name=strip_extras(name.strip())[0],
            specifier=SpecifierSet(version),
            channel=channel,
            version_mapping=version_mapping,
            build_string=build_string,
        )
    else:
        req = _parse_requirement(line=line, editable=editable)
    return req


def conda_name(self) -> str | None:
    if not hasattr(self, "_conda_name"):
        name = self.name
        self._conda_name = pypi_to_conda(strip_extras(name)[0]) if name else None
    return self._conda_name


def key(self) -> str | None:
    return normalize_name(self.conda_name).lower() if self.conda_name else None


if not _patched:
    from pdm.cli import actions
    from pdm.models import requirements

    for m in [actions, requirements]:
        setattr(m, "parse_requirement", parse_requirement)

    setattr(Requirement, "conda_name", property(conda_name))
    setattr(Requirement, "key", property(key))
    _patched = True
