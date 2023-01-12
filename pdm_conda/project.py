from pathlib import Path
from typing import cast

from pdm.core import Core
from pdm.exceptions import PdmUsageError, ProjectError
from pdm.project import Project
from tomlkit.items import Array

from pdm_conda.installers.manager import CondaInstallManager
from pdm_conda.installers.synchronizers import CondaSynchronizer
from pdm_conda.models.repositories import (
    LockedCondaRepository,
    LockedRepository,
    PyPICondaRepository,
)
from pdm_conda.models.requirements import (
    CondaRequirement,
    NamedRequirement,
    Requirement,
    parse_requirement,
)


class CondaProject(Project):
    def __init__(
        self,
        core: Core,
        root_path: str | Path | None,
        is_global: bool = False,
        global_config: str | Path | None = None,
    ) -> None:
        super().__init__(core, root_path, is_global, global_config)
        self.core.repository_class = PyPICondaRepository
        self.core.install_manager_class = CondaInstallManager
        self.locked_repository_class = LockedCondaRepository
        self.core.synchronizer_class = CondaSynchronizer
        self.virtual_packages: set[str] = set()

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
            req = parse_requirement(f"conda:{line}")
            # search for package with extras to remove it
            pypi_req = next((v for v in result.values() if v.name == req.name), None)
            if pypi_req is not None:
                result.pop(pypi_req.identify())
                if not req.specifier:
                    req.specifier = pypi_req.specifier
            result[req.identify()] = req

        if self.pyproject.settings.get("conda", {}).get("as_default_manager", False):
            for k in list(result):
                req = result[k]
                if isinstance(req, NamedRequirement):
                    result.pop(k)
                    req.extras = None
                    result[k] = parse_requirement(f"conda:{req.as_line()}")
        return result

    @property
    def locked_repository(self) -> LockedRepository:
        try:
            lockfile = self.lockfile._data.unwrap()
        except ProjectError:
            lockfile = {}

        return self.locked_repository_class(lockfile, self.sources, self.environment)

    def get_conda_pyproject_dependencies(self, group: str, dev: bool = False) -> list[str]:
        """
        Get the conda dependencies array in the pyproject.toml
        """
        settings = self.pyproject.settings.setdefault("conda", dict())
        if group == "default":
            return settings.setdefault("dependencies", [])
        name = "optional" if not dev else "dev"
        return settings.setdefault(f"{name}-dependencies", dict()).setdefault(group, [])

    def add_dependencies(
        self,
        requirements: dict[str, Requirement],
        to_group: str = "default",
        dev: bool = False,
        show_message: bool = True,
    ) -> None:
        conda_requirements = {n: r for n, r in requirements.items() if isinstance(r, CondaRequirement)}
        if conda_requirements:
            deps = self.get_conda_pyproject_dependencies(to_group, dev)
            cast(Array, deps).multiline(True)
            for _, dep in conda_requirements.items():
                matched_index = next((i for i, r in enumerate(deps) if dep.matches(f"conda:{r}")), None)
                req = dep.as_line(with_channel=True)
                if matched_index is None:
                    deps.append(req)
                else:
                    deps[matched_index] = req

        requirements = {n: r for n, r in requirements.items() if n not in conda_requirements} | {
            n: r.as_named_requirement() for n, r in conda_requirements.items() if r.is_python_package
        }
        super().add_dependencies(requirements, to_group, dev, show_message)
