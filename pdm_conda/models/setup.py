from typing import Any

from pdm.models.setup import SetupDistribution


class CondaSetupDistribution(SetupDistribution):
    @property
    def metadata(self) -> dict[str, Any]:
        metadata = super().metadata
        metadata["Home-Page"] = None
        metadata["License"] = "other"
        return metadata
