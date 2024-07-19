from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dep_logic.tags import Platform, os
from dep_logic.tags.platform import Arch

from pdm_conda.models.requirements import parse_requirement

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self

    from pdm_conda.models.requirements import CondaRequirement


def get_default_virtual_packages(platform: str, cuda_version: str | None = "11.4") -> list[CondaRequirement]:
    """
    Get the default virtual packages for each platform
    refer to https://github.com/conda/conda-lock/blob/main/conda_lock/virtual_package.py#L52
    :return: dict of platform and list of virtual packages
    """
    res: dict[str, list[CondaRequirement]] = {}
    pkgs = {
        "unix=0": ["linux-aarch64", "linux-ppc64le", "linux-64", "osx-64", "osx-arm64"],
        "linux=5.10": ["linux-aarch64", "linux-ppc64le", "linux-64"],
        "win=0": ["win-64"],
        "archspec=1=x86_64": ["win-64", "linux-64", "osx-64"],
        "archspec=1=arm64": ["osx-arm64"],
        "archspec=1=aarch64": ["linux-aarch64"],
        "archspec=1=ppc64le": ["linux-ppc64le"],
        "glibc=2.28": ["linux-aarch64", "linux-ppc64le", "linux-64"],
        f"cuda={cuda_version}": ["linux-aarch64", "linux-ppc64le", "linux-64", "win-64"],
        "osx=10.15": ["osx-64"],
        "osx=11.0": ["osx-64", "osx-arm64"],
    }
    for pkg, subdirs in pkgs.items():
        conda_pkg: CondaRequirement = parse_requirement(f"conda:__{pkg}")
        for subdir in subdirs:
            res.setdefault(subdir, []).append(conda_pkg)
    return res[platform]


@dataclass
class CondaPlatform:
    virtual_packages: list[CondaRequirement]

    @classmethod
    def create(
        cls,
        platform: Platform | None = None,
        virtual_packages: Iterable[CondaRequirement] | None = None,
        cuda_version: str | None = None,
    ) -> Self:
        """Create conda platform from platform or virtual packages :param platform: EnvSpec platform :param
        virtual_packages: list of virtual packages :param cuda_version: cuda version :return: CondaPlatform."""
        if virtual_packages is None:
            if platform is None:
                raise ValueError("Either platform or virtual_packages must be provided for CondaPlatform")
            if isinstance(platform.os, os.Macos):
                _os = "osx"
            elif isinstance(platform.os, os.Windows):
                _os = "win"
            elif isinstance(platform.os, os.Manylinux):
                _os = "linux"
            else:
                _os = None

            if platform.arch in (Arch.Aarch64, Arch.Powerpc64Le):
                _arch = str(platform.arch)
            elif platform.arch in (Arch.Armv7L, Arch.Armv6L):
                _arch = "arm64"
            elif platform.arch == Arch.X86_64:
                _arch = "64"
            else:
                _arch = None

            if _os is None or _arch is None:
                raise ValueError(f"Unsupported conda platform: {platform}")
            virtual_packages = get_default_virtual_packages(f"{_os}-{_arch}", cuda_version)
        return cls(virtual_packages=list(virtual_packages))


class ChannelSorter:
    def __init__(self, platform: str, channels: Iterable[str] | None = None) -> None:
        self._priority: dict[str, int] = {}
        self._tree: dict[str, list[str]] = {}
        self.platform = platform
        if channels:
            for channel in channels:
                self.add_channel(channel)
            for root in self._tree:
                self.add_defaults(root)

    def get_root(self, channel: str) -> str:
        return channel.split("/")[0]

    def add_defaults(self, root: str):
        for channel in [f"{root}/{self.platform}", rf"{root}/.*", f"{root}/noarch"]:
            self.add_channel(channel, allow_fuzzy=not channel.endswith("noarch"))

    def get_variants(self, root: str):
        # add parent channel priority
        if root not in self._tree:
            self._priority[root] = 1000 * len(self._tree)
            self._tree[root] = []

        return self._tree[root]

    def add_channel(self, channel: str, allow_fuzzy=True):
        root = self.get_root(channel)
        if channel not in self._priority:
            for c in (variants := self.get_variants(root)):
                if c == channel or (allow_fuzzy and re.match(c, channel)):
                    self._priority[channel] = self._priority[c]
                    # then fuzzy match
                    if c != channel:
                        self._priority[c] += 1
                    break
            # couldn't find priority in saved variant
            if channel not in self._priority:
                self._priority[channel] = self._priority[root] + len(variants) * 10
                variants.append(channel)

    def get_priority(self, channel: str) -> int:
        self.add_channel(channel)
        return self._priority[channel]
