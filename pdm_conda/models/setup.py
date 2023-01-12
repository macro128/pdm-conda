from typing import Any

from pdm.models.setup import Setup, SetupDistribution


class CondaSetupDistribution(SetupDistribution):
    def __init__(self, data: Setup, extras: dict | None = None) -> None:
        self.extras = extras or dict()
        super().__init__(data)

    @property
    def metadata(self) -> dict[str, Any]:
        metadata = super().metadata
        metadata["Home-Page"] = None
        metadata["License"] = "other"
        return metadata
