from __future__ import annotations

import dataclasses
import fnmatch
import functools
import re
from copy import copy
from typing import TYPE_CHECKING

from packaging.version import Version
from pdm.cli import utils
from pdm.exceptions import RequirementError
from pdm.models import requirements
from pdm.models.markers import Marker, get_marker
from pdm.models.requirements import NamedRequirement, Requirement, strip_extras
from pdm.models.requirements import parse_requirement as _parse_requirement
from pdm.resolver import providers

from pdm_conda.mapping import conda_to_pypi, pypi_to_conda
from pdm_conda.utils import normalize_name

if TYPE_CHECKING:
    from typing import Any

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import T

    from pdm_conda.models.config import PluginConfig

_conda_meta_req_re = re.compile(r"conda:([\w\-_/]+::)?(.+)$")
_prev_spec = ",|<>!~="
_specifier_re = re.compile(rf"(?<![{_prev_spec}])(=|==|~=|!=|<|>|<=|>=)([^{_prev_spec}\s]+)")
_conda_specifier_star_re = re.compile(r"([\w.]+)\*")
_conda_version_letter_re = re.compile(r"(\d|\.)([a-z]+)(\d?)")
_conda_virtual_package_re = re.compile(r"^(_+)(.*)")


def extract_platform_marker(conda_channel: str | None, as_dict: bool = False) -> Marker | dict[str, str] | None:
    """Extract platform marker from conda channel subdir.

    :param conda_channel: conda channel
    :param as_dict: return as dict
    :return: platform marker
    """
    if conda_channel is None:
        return None
    subdir = conda_channel.split("/")[-1].lower()
    marker = {}
    for platform, _marker in [("linux", "Linux"), ("osx", "Darwin"), ("win", "Windows")]:
        if subdir.startswith(platform):
            marker["platform_system"] = _marker
            break

    for machine, _marker in [("64", "x86_64"), ("32", "x86"), ("arm64", "arm64"), ("aarch64", "aarch64")]:
        if subdir.endswith(f"-{machine}"):
            marker["platform_machine"] = _marker
            break
    return marker if as_dict else get_marker(" and ".join(f"{k}=='{v}'" for k, v in marker.items()))


@dataclasses.dataclass(eq=False)
class CondaRequirement(NamedRequirement):
    channel: str | None = None
    is_python_package: bool = dataclasses.field(default=True, repr=False)
    version_mapping: dict = dataclasses.field(default_factory=dict, repr=False)
    build_string: str | None = None

    @property
    def conda_name(self) -> str:
        if self.name is None:
            raise RequirementError("CondaRequirement must have a name")
        return self.name

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        kwargs.pop("conda_managed", None)
        if build_string := kwargs.get("build_string", ""):
            kwargs["build_string"] = build_string.strip()
        if "is_python_package" not in kwargs:
            kwargs["is_python_package"] = not kwargs.get("name", "").startswith("_")
        platform_marker = extract_platform_marker(kwargs.get("channel", None))
        if platform_marker is not None and str(platform_marker) not in str(marker := kwargs.get("marker", None)):
            kwargs["marker"] = platform_marker if marker is None else marker & platform_marker

        return super().create(**kwargs)

    def as_line(
        self,
        as_conda: bool = False,
        with_channel: bool = False,
        with_build_string: bool = False,
        conda_compatible: bool = False,
    ) -> str:
        channel = f"{self.channel}::" if with_channel and self.channel else ""
        if as_conda:
            channel = f"conda:{channel}"
        specifiers = []
        for s in frozenset(self.specifier):
            specifiers.append(f"{s.operator}{self.version_mapping.get(s.version, s.version)}")
        specifier = ",".join(sorted(specifiers))
        build_string = f" {self.build_string}" if with_build_string and self.build_string and specifier else ""
        extras = ""
        marker = ""
        if not conda_compatible:
            extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
            marker = self._format_marker()

        return f"{channel}{self.conda_name}{extras}{specifier}{build_string}{marker}"

    def _hash_key(self) -> tuple:
        return (
            *super()._hash_key(),
            frozenset(self.specifier),
        )

    def as_named_requirement(self) -> NamedRequirement:
        return NamedRequirement.create(
            name=conda_to_pypi(self.name),
            version=str(self.specifier),
            marker=self.marker,
            extras=self.extras,
            groups=list(self.groups),
        )

    def is_compatible(self, requirement_or_candidate: Requirement | Candidate):
        if requirement_or_candidate is None:
            return False

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

    def merge(self, requirement: Requirement) -> CondaRequirement:
        """Merge with other requirement to get more specific.

        :param requirement: other requirement
        :return: merged requirement
        """
        _req = copy(self)
        _req.specifier &= requirement.specifier
        _req.groups = requirement.groups
        _req.extras = requirement.extras
        _req.marker = _req.marker
        if isinstance(requirement, CondaRequirement):
            _req.channel = requirement.channel
            _req.version_mapping.update(requirement.version_mapping)
            if not _req.build_string:
                _req.build_string = requirement.build_string
            elif requirement.build_string and requirement.build_string != _req.build_string:
                # test compatibility
                _compatible = {}
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
                    build_string = f"{_req.build_string}&{requirement.build_string} (incompatible build strings)"
                else:
                    # tries to find the most specific build string
                    build_string = min(build_strings, key=lambda x: (-len(x.replace("*", "")), x.count("*")))
                _req.build_string = build_string
        return _req


class CondaVirtualPackageRequirement(CondaRequirement):
    """A virtual package requirement."""

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        kwargs.pop("channel", None)
        if not (name := kwargs.get("name", "")).startswith("__"):
            kwargs["name"] = f"__{name}"
        if kwargs.get("build_string", None) == "0":
            kwargs.pop("build_string", None)
        obj = super().create(is_python_package=False, **kwargs)
        if obj.conda_name == "__archspec" and not obj.build_string:
            raise RequirementError(f"Missing build string for {obj.conda_name}")

        return obj

    def as_named_requirement(self) -> NamedRequirement:
        raise NotImplementedError

    def as_line(self) -> str:  # type: ignore[override]
        return super().as_line(with_build_string=True, conda_compatible=True)


def as_conda_requirement(requirement: NamedRequirement | CondaRequirement) -> CondaRequirement:
    if isinstance(requirement, NamedRequirement) and not isinstance(requirement, CondaRequirement):
        req = copy(requirement)
        req.name = req.conda_name
        conda_req = parse_requirement(f"conda:{req.as_line()}")
        conda_req.groups = req.groups
        conda_req.extras = req.extras
    else:
        conda_req = requirement

    return conda_req


def is_conda_managed(
    requirement: Requirement,
    conda_config: PluginConfig,
    excluded_identifiers: set[str] | None = None,
) -> bool:
    """True if requirement is conda requirement or (not excluded and named requirement and conda as default manager or
    used by another conda requirement)

    :param requirement: requirement to evaluate
    :param conda_config: conda config
    :param excluded_identifiers: identifiers to exclude
    """
    from pdm.resolver.python import PythonRequirement

    excluded_identifiers = excluded_identifiers or conda_config.excluded_identifiers
    identifier = requirement.key
    return (
        identifier != conda_config.project_name
        and all(not fnmatch.fnmatch(identifier, pattern) for pattern in excluded_identifiers)
        and (
            isinstance(requirement, CondaRequirement | PythonRequirement)
            or (isinstance(requirement, NamedRequirement) and conda_config.as_default_manager)
        )
    )


def correct_specifier_star(match):
    res = match.group(1)
    if res.endswith("."):
        res += "0"
    return res


def parse_conda_version(version: str) -> str:
    """Transform conda version specifier to PEP 440 version specifier.

    :param version: conda version
    :return: PEP 440 version
    """

    def correct_conda_version(match) -> str:
        digit, letter_specifier, follow_digit = match.groups()
        allowed_specifiers = ("a", "b", "rc", "dev", "post", "rev", "alpha", "beta", "preview", "pre")
        if letter_specifier in allowed_specifiers and follow_digit:
            letter_specifier += follow_digit
        else:
            letter_specifier = "".join(str(letter) for letter in (ord(letter) for letter in letter_specifier))
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
        version_mapping = {}
        channel, line = match.groups()
        if channel:
            channel = channel[:-2]
        marker = ""
        if ";" in line:
            line, marker = line.split(";", maxsplit=1)
        marker = marker.strip()

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

        # check if it's a virtual package
        prefix = ""
        is_virtual_package = False
        if virtual_package := _conda_virtual_package_re.match(name):
            prefix = virtual_package.group(1)
            name = virtual_package.group(2)
            is_virtual_package = len(prefix) == 2
        if is_virtual_package and name == "archspec":
            if build_string is None and version:
                build_string = version.split("=")[-1]
            version = "1"

        # we need to handle the "or" and "and" operator in the conda version
        # e.g. "1.2.3|1.2.4" and "1.2.3,1.2.4"
        version_and = version.split(",")
        for i, conda_version in enumerate(version_and):
            version_or = conda_version.split("|")
            for j, conda_version_or in enumerate(version_or):
                conda_version_or = conda_version_or.strip()
                if conda_version_or:
                    # if the version is just a star, we treat it as an empty string
                    if conda_version_or == "*":
                        pep_compatible_version = ""
                    else:
                        # if the version is a specifier, we need to parse it
                        if not (spec := _specifier_re.match(conda_version_or)) or spec.group(1) == "=":
                            is_eq_spec = spec and spec.group(1) == "="
                            if spec:
                                conda_version_or = conda_version_or[spec.end(1) :]
                            is_star_version = _conda_specifier_star_re.match(conda_version_or)
                            # if is equality specifier and not a virtual package, we need to add `.*` to the version
                            if is_eq_spec and not is_star_version and not is_virtual_package:
                                conda_version_or += ".*"
                            conda_version_or = f"{'~' if is_star_version else '='}={conda_version_or}"
                        # we need to convert the conda version to a comparable version
                        # so that we can use it to sort the versions
                        pep_compatible_version = conda_version_or
                        if not pep_compatible_version.startswith("=="):
                            # we need to replace the `*` with `.*` so that the version
                            # can be parsed correctly
                            pep_compatible_version = _conda_specifier_star_re.sub(
                                correct_specifier_star,
                                pep_compatible_version,
                            )
                            if pep_compatible_version.startswith("~") and "." not in pep_compatible_version:
                                pep_compatible_version += ".0"
                        # we transform the conda version to a pep 440 compatible version
                        pep_compatible_version = parse_conda_version(pep_compatible_version)
                        # we need to save the version mapping so that we can
                        # use it to get the python compatible version
                        version_mapping[remove_operator(pep_compatible_version)] = remove_operator(conda_version_or)
                    version_or[j] = pep_compatible_version
            version_and[i] = max((v for v in version_or if v), key=comparable_version, default="")
        # we need to join the versions with comma so that it can be used as a specifier
        version = ",".join(version_and)
        if marker:
            name += f"; {marker}"
        _req = _parse_requirement(line=name)
        cls = CondaVirtualPackageRequirement
        if not is_virtual_package:
            _req.name = f"{prefix}{_req.name}"
            cls = CondaRequirement

        req = cls.create(
            name=_req.name,
            version=version,
            channel=channel,
            version_mapping=version_mapping,
            build_string=build_string,
            marker=_req.marker,
            extras=_req.extras,
        )
    else:
        req = _parse_requirement(line=line, editable=editable)
    return req


def conda_name(self) -> str | None:
    if not hasattr(self, "_conda_name"):
        name = self.name
        self._conda_name = pypi_to_conda(strip_extras(name)[0]) if name else None
    return self._conda_name


def wrap_filter_requirements_with_extras(func):
    @functools.wraps(func)
    def wrapper(requirement_lines: list[str], *args, **kwargs):
        conda_requirements = [r for r in requirement_lines if _conda_meta_req_re.match(r)]
        res = func([r for r in requirement_lines if r not in conda_requirements], *args, **kwargs)
        conda_filtered = func(conda_requirements, *args, **kwargs)
        conda_idx = 0
        for i, req in enumerate(conda_filtered):
            while conda_idx < len(conda_requirements):
                conda_req = conda_requirements[conda_idx]
                conda_idx += 1
                if req in conda_req:
                    conda_filtered[i] = f"conda:{req}"
                    break
        return res + conda_filtered

    return wrapper


def key(self) -> str | None:
    return normalize_name(self.conda_name) if self.conda_name else None


for m in [providers, requirements]:
    m.parse_requirement = parse_requirement

utils.filter_requirements_with_extras = wrap_filter_requirements_with_extras(utils.filter_requirements_with_extras)
Requirement.conda_name = property(conda_name)
Requirement.key = property(key)
