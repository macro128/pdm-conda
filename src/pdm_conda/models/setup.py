from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.models.setup import SetupDistribution

from pdm_conda.models.requirements import CondaRequirement, parse_requirement

if TYPE_CHECKING:
    from typing import Any

    from pdm.models.setup import Setup


class CondaSetupDistribution(SetupDistribution):
    def __init__(self, data: Setup, package: dict | None = None) -> None:
        self.package = package or {}
        super().__init__(data)

    @property
    def metadata(self) -> dict[str, Any]:
        metadata = super().metadata
        metadata["Home-Page"] = None
        metadata["License"] = "other"
        return metadata

    def as_line(self):
        channel = self.package.get("channel", "")
        if channel:
            channel += "::"
        build_string = self.package.get("build_string", self.package.get("build", ""))
        if build_string:
            build_string = f" {build_string}"
        version = self.package.get("version", "")
        name = self.package.get("name", "")
        return f"{channel}{name}=={version}{build_string}"

    @property
    def req(self) -> CondaRequirement:
        return cast(CondaRequirement, parse_requirement(f"conda:{self.as_line()}"))
