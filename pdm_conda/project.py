from pathlib import Path
from typing import cast

from pdm.core import Core
from pdm.exceptions import ProjectError
from pdm.project import Project
from tomlkit.items import Array

from pdm_conda.installers.manager import CondaInstallManager
from pdm_conda.installers.synchronizers import CondaSynchronizer
from pdm_conda.mapping import download_mapping
from pdm_conda.models.config import PluginConfig
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
        self._conda_mapping: dict[str, str] = dict()
        self._pypi_mapping: dict[str, str] = dict()

    @property
    def pypi_mapping(self):
        if self.conda_mapping and not self._pypi_mapping:
            self._pypi_mapping = {v: k for k, v in self._conda_mapping.items()}
        return self._pypi_mapping

    @property
    def conda_mapping(self):
        if not self._conda_mapping:
            config = PluginConfig.load_config(self)
            if config.is_initialized:
                self.conda_mapping = download_mapping(config.mappings_download_dir)
        return self._conda_mapping

    @conda_mapping.setter
    def conda_mapping(self, value):
        self._conda_mapping = value
        self._pypi_mapping = {v: k for k, v in value.items()}

    @staticmethod
    def _requirement_map(requirement: str, mapping: dict):
        requirement = requirement.strip()
        name = requirement
        for s in (">", "<", "=", "!", "~", " "):
            name = name.split(s, maxsplit=1)[0]
        name = name.strip()
        _name = name.split("[")[0].split("::")[-1]
        map_name = mapping.get(_name, name)
        requirement = f"{map_name}{requirement[len(name):]}"
        return requirement, map_name, name

    def conda_to_pypi(self, requirement: str) -> tuple[str, str, str]:
        """
        Map Conda requirement to PyPI version
        :param requirement: Conda requirement
        :return: PyPI requirement, PyPI requirement name and Conda requirement name
        """
        return self._requirement_map(requirement, self.conda_mapping)

    def pypi_to_conda(self, requirement: str) -> str:
        """
        Map PyPI requirement to Conda version
        :param requirement: PyPI requirement
        :return: Conda requirement
        """
        return self._requirement_map(requirement, self.pypi_mapping)[0]

    def get_conda_pyproject_dependencies(self, group: str, dev: bool = False) -> list[str]:
        """
        Get the conda dependencies array in the pyproject.toml
        """
        settings = self.pyproject.settings.setdefault("conda", dict())
        if group == "default":
            deps = settings.setdefault("dependencies", [])
        else:
            name = "optional" if not dev else "dev"
            deps = settings.setdefault(f"{name}-dependencies", dict()).setdefault(group, [])

        for i, dep in enumerate(deps):
            deps[i] = self.conda_to_pypi(dep)[0]

        return deps

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        result = super().get_dependencies(group)

        settings = self.pyproject.settings.get("conda", {})
        group = group or "default"
        optional_dependencies = settings.get("optional-dependencies", {})
        dev_dependencies = settings.get("dev-dependencies", {})

        dev = group not in optional_dependencies
        if group in optional_dependencies and group in dev_dependencies:
            self.core.ui.echo(
                f"The {group} group exists in both [optional-dependencies] "
                "and [dev-dependencies], the former is taken.",
                err=True,
                style="warning",
            )
        deps = self.get_conda_pyproject_dependencies(group, dev)

        for line in deps:
            req = parse_requirement(f"conda:{line}")
            # search for package with extras to remove it
            pypi_req = next((v for v in result.values() if v.name == req.name), None)
            if pypi_req is not None:
                result.pop(pypi_req.identify())
                if not req.specifier:
                    req.specifier = pypi_req.specifier
            else:
                req.is_python_package = False
            result[req.identify()] = req

        if self.pyproject.settings.get("conda", {}).get("as_default_manager", False):
            for k in list(result):
                req = result[k]
                if isinstance(req, NamedRequirement) and not isinstance(req, CondaRequirement):
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
