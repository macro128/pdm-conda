from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from dep_logic.tags import EnvCompatibility, os
from dep_logic.tags.platform import Arch
from pdm.exceptions import PdmUsageError
from pdm.models.markers import EnvSpec
from typing_extensions import Self

from pdm_conda.models.requirements import CondaRequirement, parse_requirement


class InvalidCondaEnvSpec(PdmUsageError, ValueError):
    pass


@dataclass(frozen=True)
class CondaEnvSpec(EnvSpec):
    system: CondaRequirement | None = None
    glibc: CondaRequirement | None = None
    cuda: CondaRequirement | None = None
    archspec: CondaRequirement | None = None

    def replace(self, **kwargs: Any) -> Self:
        res = super().replace(**kwargs)
        if res.glibc is not None and (res.platform is None or not isinstance(res.platform.os, os.Manylinux)):
            raise InvalidCondaEnvSpec("Glibc can only be specified on linux platform")
        if res.system is not None and (res.platform is None or isinstance(res.platform.os, os.Windows)):
            raise InvalidCondaEnvSpec("System cannot be specified on windows platform")
        return res

    @classmethod
    def from_env_spec(cls, env_spec: EnvSpec, **kwargs: Any) -> Self:
        kwargs = {
            k: parse_requirement(f"conda:{k}={v}") if isinstance(v := kwargs.get(k, None), str) else v
            for k in ("system", "glibc", "cuda", "archspec")
        }
        return cls(
            requires_python=env_spec.requires_python,
            platform=env_spec.platform,
            implementation=env_spec.implementation,
        ).replace(**kwargs)

    def as_dict(self) -> dict[str, str | bool]:
        res = super().as_dict()
        for k in ("system", "glibc", "cuda", "archspec"):
            if (v := getattr(self, k, None)) is not None:
                res[k] = v.as_line(conda_compatible=True, with_build_string=False)

        return res

    def compare(self, target: EnvSpec) -> EnvCompatibility:
        if (
            self.is_conda_env
            and isinstance(target, CondaEnvSpec)
            and target.is_conda_env
            and (
                target.system != self.system
                or target.glibc != self.glibc
                or target.cuda != self.cuda
                or target.archspec != self.archspec
            )
        ):
            return EnvCompatibility.INCOMPATIBLE

        return super().compare(target)

    @property
    def is_conda_env(self) -> bool:
        return self.system is not None or self.glibc is not None or self.cuda is not None or self.archspec is not None

    def is_allow_all(self) -> bool:
        return super().is_allow_all() and not self.is_conda_env

    @property
    def conda_platform(self) -> str | None:
        if self.platform is None:
            return None
        platform = self.platform
        _os = None
        _arch = None
        if isinstance(platform.os, os.Macos):
            _os = "osx"
        elif isinstance(platform.os, os.Windows):
            _os = "win"
        elif isinstance(platform.os, os.Manylinux):
            _os = "linux"

        if platform.arch in (Arch.Aarch64, Arch.Powerpc64Le):
            _arch = str(platform.arch)
        elif platform.arch in (Arch.Armv7L, Arch.Armv6L):
            _arch = "arm64"
        elif platform.arch == Arch.X86_64:
            _arch = "64"

        if _os is None or _arch is None:
            raise ValueError(f"Unsupported conda platform: {platform}")
        return f"{_os}-{_arch}"

    def markers(self) -> dict[str, str | list[str]]:
        markers = super().markers()
        if self.is_conda_env:
            virtual_packages = get_default_virtual_packages(self.conda_platform) if self.conda_platform else {}

            if self.system is not None:
                virtual_packages[self.system.name] = self.system
            if self.glibc is not None:
                virtual_packages["glibc"] = self.glibc
            if self.cuda is not None:
                virtual_packages["cuda"] = self.cuda
            if self.archspec is not None:
                virtual_packages["archspec"] = self.archspec

            extras = [v.as_line(conda_compatible=True, with_build_string=True) for v in virtual_packages.values()]
            if extras:
                if (_extra := markers.get("extra", None)) is None:
                    if isinstance(_extra, str):
                        extras.append(_extra)
                    elif isinstance(_extra, (list, tuple)):
                        extras.extend(_extra)
                markers["extra"] = extras

        return markers


DEFAULT_VIRTUAL_PACKAGES = {
    ("unix", "0"): ["linux-aarch64", "linux-ppc64le", "linux-64", "osx-64", "osx-arm64"],
    ("linux", "5.10"): ["linux-aarch64", "linux-ppc64le", "linux-64"],
    ("win", "0"): ["win-64"],
    ("archspec", "1-x86_64"): ["win-64", "linux-64", "osx-64"],
    ("archspec", "1-arm64"): ["osx-arm64"],
    ("archspec", "1-aarch64"): ["linux-aarch64"],
    ("archspec", "1-ppc64le"): ["linux-ppc64le"],
    ("glibc", "2.28"): ["linux-aarch64", "linux-ppc64le", "linux-64"],
    ("cuda", "11.4"): ["linux-aarch64", "linux-ppc64le", "linux-64", "win-64"],
    ("osx", "11.0"): ["osx-64", "osx-arm64"],
}


def get_default_virtual_packages(platform: str) -> dict[str, CondaRequirement]:
    """
    Get the default virtual packages for each platform
    refer to https://github.com/conda/conda-lock/blob/main/conda_lock/virtual_package.py#L52
    :return: dict of virtual packages and version specifiers
    """
    res = {}
    for (pkg, version), subdirs in DEFAULT_VIRTUAL_PACKAGES.items():
        for subdir in subdirs:
            if subdir == platform:
                res[pkg] = cast(CondaRequirement, parse_requirement(f"conda:__{pkg}={version}"))
    return res
