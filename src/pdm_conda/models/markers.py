from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from dep_logic.tags import EnvCompatibility, os
from dep_logic.tags.platform import Arch
from pdm.exceptions import PdmUsageError
from pdm.models.markers import EnvSpec
from typing_extensions import Self

from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import CondaVirtualPackageRequirement, extract_platform_marker, parse_requirement


class InvalidCondaEnvSpec(PdmUsageError, ValueError):
    pass


@dataclass(frozen=True)
class CondaEnvSpec(EnvSpec):
    """The env spec for conda environments."""

    system: CondaVirtualPackageRequirement | None = None
    glibc: CondaVirtualPackageRequirement | None = None
    cuda: CondaVirtualPackageRequirement | None = None
    archspec: CondaVirtualPackageRequirement | None = None

    @staticmethod
    def is_system(name: str) -> bool:
        """Check if the name is system related.

        :param name: name to check
        :return: bool
        """
        return name.lstrip("_") in ("linux", "osx", "win")

    def __str__(self) -> str:
        """If the env spec is a conda env, add the system, glibc, cuda and archspec to the string.

        :return: the string representation of the env spec
        """
        res = super().__str__()
        if self.is_conda_env:
            parts = []
            for r in [self.system, self.glibc, self.cuda, self.archspec]:
                if r is not None:
                    parts.append(r.as_line())
            if parts:
                res = ", ".join([res[:-1]] + parts) + res[-1]
        return res

    def replace(self, **kwargs: Any) -> Self:
        """Replace the env spec with the given kwargs, if the env spec is a conda env run some checks. If the env spec
        is not a conda env and platform was replaced, add the default specs for the platform.

        :param kwargs: the kwargs to replace
        :return: the replaced env spec
        """
        kwargs |= {
            k: parse_requirement("conda:" + (f"__{k}={v}" if not v.startswith("__") else v))
            if isinstance(v := kwargs.get(k, None), str)
            else v
            for k in kwargs
            if k in ("system", "glibc", "cuda", "archspec")
        }
        res = cast(CondaEnvSpec, super().replace(**kwargs))
        # check conda env spec correctness
        if res.platform is not None:
            if res.glibc is not None and not isinstance(res.platform.os, os.Manylinux):
                raise InvalidCondaEnvSpec("Glibc can only be specified on linux platform")
            if (
                res.system is not None
                and str(res.system.specifier) != "==0"
                and isinstance(res.platform.os, os.Windows)
            ):
                raise InvalidCondaEnvSpec("System cannot be specified on windows platform")
        elif res.system is not None:
            raise InvalidCondaEnvSpec("System version can only be specified after platform")
        # if platform was replaced, add the default virtual packages for conda env spec
        if "platform" in kwargs and not res.is_conda_env:
            default_virtual_packages = get_default_virtual_packages(res.conda_platform, include_unix=False)
            # add the default virtual package for the system
            for k in list(default_virtual_packages):
                if self.is_system(k):
                    default_virtual_packages["system"] = default_virtual_packages.pop(k)
                    break

            res = res.replace(**default_virtual_packages)

        if res.conda_platform is not None and res.system is not None:
            res.system.name = f"__{res.conda_platform.split('-')[0]}"
        return res

    @classmethod
    def from_env_spec(cls, env_spec: EnvSpec, **kwargs: Any) -> Self:
        return cls(
            requires_python=env_spec.requires_python,
            platform=env_spec.platform,
            implementation=env_spec.implementation,
        ).replace(**kwargs)

    @classmethod
    def from_spec(
        cls,
        requires_python: str,
        platform: str | None = None,
        implementation: str | None = None,
        gil_disabled: bool = False,
        **kwargs: Any,
    ) -> Self:
        return cls.from_env_spec(super().from_spec(requires_python, platform, implementation, gil_disabled), **kwargs)

    def as_dict(self) -> dict[str, str | bool]:
        res = super().as_dict()
        for k in ("system", "glibc", "cuda", "archspec"):
            if (v := getattr(self, k, None)) is not None:
                res[k] = v.as_line()

        return res

    def compare(self, target: EnvSpec) -> EnvCompatibility:
        if (
            self.is_conda_env
            and isinstance(target, CondaEnvSpec)
            and target.is_conda_env
            and (
                target.system != self.system
                or target.archspec != self.archspec
                or (self.glibc is not None and not self.glibc.is_compatible(target.glibc))
                or (self.glibc is None and target.glibc is not None)
                or (self.cuda is not None and not self.cuda.is_compatible(target.cuda))
                or (self.cuda is None and target.cuda is not None)
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
            _arch = str(platform.arch) if not isinstance(platform.os, os.Macos) else "arm64"
        elif platform.arch in (Arch.Armv7L, Arch.Armv6L):
            _arch = "arm64"
        elif platform.arch == Arch.X86_64:
            _arch = "64"

        if _os is None or _arch is None:
            raise ValueError(f"Unsupported conda platform: {platform}")
        return f"{_os}-{_arch}"

    def markers(self) -> dict[str, str]:
        """Get the markers for this env spec, if it is a conda env and the platform is set, force the platform marker.

        :return: Env spec markers
        """
        markers = super().markers()
        if self.is_conda_env and self.conda_platform is not None:
            # add platform marker
            markers |= extract_platform_marker(self.conda_platform, as_dict=True)
        return markers

    def candidate_is_compatible(self, candidate: CondaCandidate) -> bool:
        """
        Check if the candidate is compatible with this env spec:
        - If the env spec is not a conda env, it is always compatible
        - If the env spec is a conda env:
            - Check if the candidate marker is compatible with the env spec
            - Check if the candidate virtual packages are compatible with the env spec

        :param candidate: Conda candidate
        :return: True if the candidate is compatible
        """
        if not self.is_conda_env:
            return True
        if candidate.req.marker is not None and not candidate.req.marker.matches(self):
            return False
        return all(
            v.is_compatible(getattr(self, (k if not self.is_system(k) else "system").lstrip("_")))
            for k, v in candidate.virtual_packages.items()
        )


DEFAULT_VIRTUAL_PACKAGES = {
    ("unix", "0"): ["linux-aarch64", "linux-ppc64le", "linux-64", "osx-64", "osx-arm64"],
    ("linux", "5.10"): ["linux-aarch64", "linux-ppc64le", "linux-64"],
    ("win", "0"): ["win-64"],
    # ("archspec", "1=x86_64"): ["win-64", "linux-64", "osx-64"],
    ("archspec", "1=x86_64"): ["linux-64", "osx-64"],
    ("archspec", "1=arm64"): ["osx-arm64"],
    ("archspec", "1=aarch64"): ["linux-aarch64"],
    ("archspec", "1=ppc64le"): ["linux-ppc64le"],
    ("glibc", "2.28"): ["linux-aarch64", "linux-ppc64le", "linux-64"],
    ("cuda", "11.4"): ["linux-aarch64", "linux-ppc64le", "linux-64", "win-64"],
    ("osx", "11.0"): ["osx-64", "osx-arm64"],
}


def get_default_virtual_packages(
    platform: str | None,
    include_cuda: bool = False,
    include_unix: bool = True,
) -> dict[str, CondaVirtualPackageRequirement]:
    """
    Get the default virtual packages for each platform
    refer to https://github.com/conda/conda-lock/blob/main/conda_lock/virtual_package.py#L52

    :param platform: conda platform string
    :param include_cuda: include cuda virtual package
    :param include_unix: include unix virtual package
    :return: dict of virtual packages and version specifiers
    """
    if platform is None:
        return {}
    res = {}
    for (pkg, version), subdirs in DEFAULT_VIRTUAL_PACKAGES.items():
        if (not include_cuda and pkg == "cuda") or (not include_unix and pkg == "unix"):
            continue
        for subdir in subdirs:
            if subdir == platform:
                res[pkg] = cast(CondaVirtualPackageRequirement, parse_requirement(f"conda:__{pkg}={version}"))
    return res
