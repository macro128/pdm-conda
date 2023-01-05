from pathlib import Path

from pdm.core import Core
from pdm.exceptions import PdmUsageError
from pdm.project import Project

from pdm_conda.models.requirements import CondaPackage, Requirement, parse_requirement


class CondaProject(Project):
    def __init__(
        self,
        core: Core,
        root_path: str | Path | None,
        is_global: bool = False,
        global_config: str | Path | None = None,
    ) -> None:
        super().__init__(core, root_path, is_global, global_config)
        self.conda_packages: dict[str, CondaPackage] = dict()

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        result = super().get_dependencies(group)

        settings = self.pyproject.settings.get("conda", {})
        group = group or "default"
        optional_dependencies = settings.get("optional-dependencies", {})
        dev_dependencies = settings.get("dev-dependencies", {})
        deps = []

        if group == "default":
            deps = settings.get("dependencies", [])
        else:
            if group in optional_dependencies and group in dev_dependencies:
                self.core.ui.echo(
                    f"The {group} group exists in both [optional-dependencies] "
                    "and [dev-dependencies], the former is taken.",
                    err=True,
                    style="warning",
                )
            if group in optional_dependencies:
                deps = optional_dependencies[group]
            elif group in dev_dependencies:
                deps = dev_dependencies[group]
            elif not result:
                raise PdmUsageError(f"Non-exist group {group}")

        for line in deps:
            req = parse_requirement(line, conda_managed=True)
            req_id = req.identify()
            pypi_req = result.pop(req_id, None)
            # search for package with extras to remove it
            if pypi_req is None:
                _req_id = next((k for k in result if k.startswith(f"{req_id}[")), None)
                pypi_req = result.pop(_req_id, None)
            if pypi_req is not None and not req.specifier:
                req.specifier = pypi_req.specifier
            result[req.identify()] = req

        return result
