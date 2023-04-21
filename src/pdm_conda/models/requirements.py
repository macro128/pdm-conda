import dataclasses
import re
from copy import copy
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pdm.models.candidates import Candidate
from pdm.models.requirements import NamedRequirement, Requirement, T
from pdm.models.requirements import parse_requirement as _parse_requirement
from pdm.models.requirements import strip_extras

from pdm_conda.mapping import conda_to_pypi, pypi_to_conda
from pdm_conda.utils import normalize_name

_conda_meta_req_re = re.compile(r"conda:([\w\-_\d/]+::)?(.+)$")
_prev_spec = ",|<>!~="
_specifier_re = re.compile(rf"(?<![{_prev_spec}])(=|==|~=|!=|<|>|<=|>=)([^{_prev_spec}\s]+)")
_conda_specifier_star_re = re.compile(r"([\w.]+)\*")
_conda_version_letter_re = re.compile(r"(\d|\.)([a-z]+)(\d?)")

_patched = False


@dataclasses.dataclass(eq=False)
class CondaRequirement(NamedRequirement):
    channel: str | None = None
    _is_python_package: bool = dataclasses.field(default=True, repr=False, init=False)
    version_mapping: dict = dataclasses.field(default_factory=dict, repr=False)
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

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        kwargs.pop("conda_managed", None)
        if build_string := kwargs.get("build_string", None):
            kwargs["build_string"] = build_string.strip()

        return super().create(**kwargs)

    def as_line(
        self,
        as_conda: bool = False,
        with_channel=False,
        with_build_string=False,
        conda_compatible=False,
    ) -> str:
        channel = f"{self.channel}::" if with_channel and self.channel else ""
        if as_conda:
            channel = f"conda:{channel}"
        specifier = ""
        for s in self.specifier:
            if specifier:
                specifier += ","
            operator = s.operator
            version = self.version_mapping.get(s.version, s.version)
            if conda_compatible and operator == "~=":
                operator = "="
                if len(parts := version.split(".")) > 0:
                    if parts[-1] == "*":
                        version = f"{'.'.join(parts[:-1])}.0"
                    # special releases are omitted
                    if len(parts) > 2 and re.search(r"(a|b|rc|dev|post|rev|alpha|beta|preview|pre)\d", parts[-1]):
                        parts = parts[:-1]
                    version = f"{'.'.join(parts[:-1])}.*,>={version}"
            specifier += f"{operator}{version}"
        build_string = f" {self.build_string}" if with_build_string and self.build_string and specifier else ""
        return f"{channel}{self.conda_name}{specifier}{build_string}"

    def _hash_key(self) -> tuple:
        return (
            self.key,
            frozenset(self.specifier),
        )

    def as_named_requirement(self) -> NamedRequirement:
        return NamedRequirement.create(name=conda_to_pypi(self.name), specifier=self.specifier)

    def is_compatible(self, requirement_or_candidate: Requirement | Candidate):
        _compatible = True
        # test build string compatible
        if (build_string := getattr(requirement_or_candidate, "build_string", "")) and self.build_string:
            _compatible &= re.match(rf"{self.build_string.replace('*', r'.*')}", build_string) is not None

        # test equal name
        _compatible &= self.conda_name == getattr(
            requirement_or_candidate,
            "conda_name",
            getattr(requirement_or_candidate, "name", ""),
        )

        # test version/specifier compatible
        versions = []
        if (version := getattr(requirement_or_candidate, "version", None)) is not None:
            versions.append(version)
        else:
            versions += [s.version for s in requirement_or_candidate.specifier]

        spec = copy(self.specifier)
        spec.prereleases = True
        _compatible &= all(spec.contains(v) for v in versions)
        return _compatible

    def merge(self, requirement: Requirement) -> "CondaRequirement":
        """
        Merge with other requirement to get more specific
        :param requirement: other requirement
        :return: merged requirement
        """
        _req = copy(self)
        _req.specifier &= requirement.specifier
        if isinstance(requirement, CondaRequirement):
            _req.channel = requirement.channel
            _req.version_mapping.update(requirement.version_mapping)
            if not _req.build_string:
                _req.build_string = requirement.build_string
            elif requirement.build_string and requirement.build_string != _req.build_string:
                # test compatibility
                _compatible = dict()
                build_strings = [requirement.build_string, _req.build_string]
                for build_string in build_strings:
                    if build_string not in _compatible:
                        _compatible[build_string] = all(
                            re.match(build_string.replace("*", r".*"), bs)
                            or re.match(bs.replace("*", r".*"), build_string)
                            for bs in build_strings
                            if bs != build_string
                        )
                # if all incompatibles then keep fake build string to force failing search
                if not all(_compatible.values()):
                    build_string = f"{_req.build_string}{requirement.build_string}"
                else:
                    # tries to find the most specific build string
                    build_string = min(build_strings, key=lambda x: (-len(x.replace("*", "")), x.count("*")))
                _req.build_string = build_string
        return _req


def as_conda_requirement(requirement: NamedRequirement | CondaRequirement) -> Requirement:
    if isinstance(requirement, NamedRequirement) and not isinstance(requirement, CondaRequirement):
        req = copy(requirement)
        req.marker = None
        req.name = req.conda_name
        conda_req = parse_requirement(f"conda:{req.as_line()}")
    else:
        conda_req = requirement

    return conda_req


def correct_specifier_star(match):
    res = match.group(1)
    if res.endswith("."):
        res += "0"
    return res


def parse_conda_version(version, inverse=False):
    def correct_conda_version(match):
        digit, letter_specifier, follow_digit = match.groups()
        allowed_specifiers = ("a", "b", "rc", "dev", "post", "rev", "alpha", "beta", "preview", "pre")
        if letter_specifier in allowed_specifiers and follow_digit:
            letter_specifier += follow_digit
        else:
            _letter_specifier = (ord(letter) for letter in letter_specifier)
            if inverse:
                _letter_specifier = (ord("z") + 1 - letter for letter in _letter_specifier)
            letter_specifier = "".join(str(letter) for letter in _letter_specifier)
            if digit != ".":
                letter_specifier = f".{letter_specifier}"
        return f"{digit}{letter_specifier}"

    return _conda_version_letter_re.sub(correct_conda_version, version)


def remove_operator(version: str) -> str:
    return _specifier_re.sub(r"\2", version)


def comparable_version(version: str) -> Version:
    version = remove_operator(version)
    if version.endswith(".*"):
        version = version[:-2]
    return Version(version)


def parse_requirement(line: str, editable: bool = False) -> Requirement:
    if (match := _conda_meta_req_re.match(line)) is not None:
        version_mapping = dict()
        channel, line = match.groups()
        if channel:
            channel = channel[:-2]

        build_string = None
        if len(_line := re.split(r"\s+", line)) == 3 or (len(_line) == 2 and _specifier_re.search(_line[0])):
            build_string = _line[-1]
            line = " ".join(_line[:-1])
        elif len(_line := list(_specifier_re.finditer(line))) == 2:
            match = _line[-1]  # type: ignore
            build_string, line = line[match.end(1) :], line[: match.start()]

        name = line
        version = ""
        if match := _specifier_re.search(line):
            name, version = line[: match.start(1)], line[match.start(1) :]
        elif " " in line:
            name, version = line.split(" ", maxsplit=1)
        version_and = version.split(",")
        for i, conda_version in enumerate(version_and):
            version_or = conda_version.split("|")
            for j, conda_version_or in enumerate(version_or):
                if conda_version_or:
                    if conda_version_or == "*":
                        _version = ""
                    else:
                        if not (spec := _specifier_re.match(conda_version_or)) or spec.group(1) == "=":
                            spec_eq = spec and spec.group(1) == "="
                            if spec:
                                conda_version_or = conda_version_or[spec.end(1) :]
                            star_version = _conda_specifier_star_re.match(conda_version_or)
                            if spec_eq and not star_version:
                                conda_version_or += ".*"
                            if star_version:
                                s = "~"
                            else:
                                s = "="
                            conda_version_or = f"{s}={conda_version_or}"
                        _version = conda_version_or
                        if not _version.startswith("=="):
                            _version = _conda_specifier_star_re.sub(correct_specifier_star, _version)
                            if _version.startswith("~") and "." not in _version:
                                _version += ".0"
                        _version = parse_conda_version(_version)
                        version_mapping[remove_operator(_version)] = remove_operator(conda_version_or)
                    version_or[j] = _version
            version_and[i] = max((v for v in version_or if v), key=comparable_version, default="")
        version = ",".join(version_and)
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
