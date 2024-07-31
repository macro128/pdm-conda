from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dep_logic.specifiers import VersionSpecifier
from dep_logic.tags import EnvCompatibility, os
from dep_logic.tags.platform import Arch
from dep_logic.tags.tags import _ensure_version_specifier
from pdm.exceptions import PdmUsageError
from pdm.models.markers import EnvSpec
from typing_extensions import Self


class InvalidCondaEnvSpec(PdmUsageError, ValueError):
    pass


@dataclass(frozen=True)
class CondaEnvSpec(EnvSpec):
    system: VersionSpecifier | None = None
    glibc: VersionSpecifier | None = None
    cuda: VersionSpecifier | None = None

    def replace(self, **kwargs: Any) -> Self:
        res = super().replace(**kwargs)
        if res.glibc and (res.platform is None or not isinstance(res.platform.os, os.Manylinux)):
            raise InvalidCondaEnvSpec("Glibc can only be specified on linux platform")
        if res.system and (res.platform is None or isinstance(res.platform.os, os.Windows)):
            raise InvalidCondaEnvSpec("System cannot be specified on windows platform")
        return res

    @classmethod
    def from_env_spec(
        cls,
        env_spec: EnvSpec,
        system: str | None = None,
        glibc: str | None = None,
        cuda: str | None = None,
    ) -> Self:
        return cls(
            requires_python=env_spec.requires_python,
            platform=env_spec.platform,
            implementation=env_spec.implementation,
        ).replace(
            system=_ensure_version_specifier(system) if system is not None else None,
            glibc=_ensure_version_specifier(glibc) if glibc is not None else None,
            cuda=_ensure_version_specifier(cuda) if cuda is not None else None,
        )

    def as_dict(self) -> dict[str, str | bool]:
        res = super().as_dict()
        if self.system is not None:
            res["system"] = str(self.system)
        if self.glibc is not None:
            res["glibc"] = str(self.glibc)
        if self.cuda is not None:
            res["cuda"] = str(self.cuda)
        return res

    def compare(self, target: EnvSpec) -> EnvCompatibility:
        if (
            self.is_conda_env
            and isinstance(target, CondaEnvSpec)
            and target.is_conda_env
            and (target.system != self.system or target.glibc != self.glibc or target.cuda != self.cuda)
        ):
            return EnvCompatibility.INCOMPATIBLE

        return super().compare(target)

    @property
    def is_conda_env(self) -> bool:
        return self.system is not None or self.glibc is not None or self.cuda is not None

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
                _os = ""
                if isinstance(self.platform.os, os.Macos):
                    _os = "osx"
                elif isinstance(self.platform.os, os.Windows):
                    _os = "win"
                elif isinstance(self.platform.os, os.Manylinux):
                    _os = "linux"
                virtual_packages[_os] = self.system
            if self.glibc is not None:
                virtual_packages["glibc"] = self.glibc
            if self.cuda is not None:
                virtual_packages["cuda"] = self.cuda

            extras = [f"{pkg}={v}" for pkg, v in virtual_packages.items()]
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


def get_default_virtual_packages(platform: str) -> dict[str, VersionSpecifier]:
    """
    Get the default virtual packages for each platform
    refer to https://github.com/conda/conda-lock/blob/main/conda_lock/virtual_package.py#L52
    :return: dict of virtual packages and version specifiers
    """
    res = {}
    for (pkg, version), subdirs in DEFAULT_VIRTUAL_PACKAGES.items():
        for subdir in subdirs:
            if subdir == platform:
                res[pkg] = _ensure_version_specifier(version)
    return res
