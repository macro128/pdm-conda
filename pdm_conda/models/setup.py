from typing import Any

from pdm.models.setup import Setup, SetupDistribution


class CondaSetupDistribution(SetupDistribution):
    def __init__(self, data: Setup, conda_name: str | None = None, extras: dict | None = None) -> None:
        if conda_name is conda_name:
            conda_name = data.name
        if conda_name is None:
            raise ValueError(f"Missing conda name for package {data}")
        self.conda_name: str = conda_name
        self.extras = extras or dict()
        super().__init__(data)

    @property
    def metadata(self) -> dict[str, Any]:
        metadata = super().metadata
        metadata["Home-Page"] = None
        metadata["License"] = "other"
        return metadata
