from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

from pdm.exceptions import ProjectError
from pdm.project import Project
from pdm.project.lockfile import Lockfile
from pdm.utils import get_venv_like_prefix
from tomlkit.items import Array

from pdm_conda.models.config import PluginConfig
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement, is_conda_managed, parse_requirement
from pdm_conda.project.project_file import PyProject

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from findpython import Finder
    from pdm.core import Core
    from pdm.environments import BaseEnvironment
    from pdm.models.repositories import LockedRepository
    from pdm.models.requirements import Requirement
    from pdm.resolver.providers import BaseProvider


class CondaProject(Project):
    def __init__(
        self,
        core: Core,
        root_path: str | Path | None,
        is_global: bool = False,
        global_config: str | Path | None = None,
    ) -> None:
        from pdm_conda.environments import CondaEnvironment
        from pdm_conda.installers.manager import CondaInstallManager
        from pdm_conda.installers.synchronizers import CondaSynchronizer
        from pdm_conda.models.repositories import LockedCondaRepository, PyPICondaRepository
        from pdm_conda.resolvers import CondaResolver

        super().__init__(core, root_path, is_global, global_config)
        self.core.repository_class = PyPICondaRepository
        self.core.install_manager_class = CondaInstallManager
        self.core.synchronizer_class = CondaSynchronizer
        self.core.resolver_class = CondaResolver
        self.locked_repository_class = LockedCondaRepository
        self.environment_class = CondaEnvironment
        self._virtual_packages: set[CondaRequirement] | None = None
        self._platform: str | None = None
        self._default_channels: list[str] | None = None
        self._conda_mapping: dict[str, str] = {}
        self._pypi_mapping: dict[str, str] = {}
        self.conda_config = PluginConfig.load_config(self)
        self._is_distribution: bool | None = None

    def _check_update_info(self, prop):
        if prop is None:
            self._get_conda_info()

    @cached_property
    def virtual_packages(self) -> set[CondaRequirement]:
        self._check_update_info(self._virtual_packages)
        return self._virtual_packages  # type: ignore

    @property
    def platform(self) -> str:
        self._check_update_info(self._platform)
        return self._platform  # type: ignore

    @property
    def default_channels(self) -> list[str]:
        self._check_update_info(self._default_channels)
        return self._default_channels  # type: ignore

    @property
    def locked_repository(self) -> LockedRepository:
        try:
            lockfile = self.lockfile._data.unwrap()
        except ProjectError:
            lockfile = {}

        return self.locked_repository_class(lockfile, self.sources, self.environment)

    @cached_property
    def pyproject(self) -> PyProject:
        return PyProject(self.root / self.PYPROJECT_FILENAME, ui=self.core.ui)

    @property
    def lockfile(self) -> Lockfile:
        if self._lockfile is None:
            self.set_lockfile(self.root / self.LOCKFILE_FILENAME)
        return self._lockfile

    def set_lockfile(self, path: str | Path) -> None:
        self._lockfile = Lockfile(path, ui=self.core.ui)
        # conda don't produce cross-platform locks
        if self.conda_config.is_initialized and not self._lockfile.empty():
            self._lockfile._data.setdefault("metadata", {})["cross_platform"] = False

    def _get_conda_info(self):
        from pdm_conda.conda import conda_info

        info = conda_info(self)
        self._virtual_packages = info["virtual_packages"]
        self._platform = info["platform"]
        self._default_channels = info["channels"]

    def get_conda_pyproject_dependencies(self, group: str, dev: bool = False, set_defaults=False) -> list[str]:
        """Get the conda dependencies array in the pyproject.toml."""

        def _getter(conf, name, default, set_defaults=False):
            return (conf.setdefault if set_defaults else conf.get)(name, default)

        settings = _getter(self.pyproject.settings, "conda", {}, set_defaults)
        if group == "default":
            group = "dependencies"
        else:
            name = "optional" if not dev else "dev"
            settings = _getter(settings, f"{name}-dependencies", {}, set_defaults)
        return _getter(settings, group, [], set_defaults)

    def iter_groups(self, dev: bool = True) -> Iterable[str]:
        groups = set(super().iter_groups())
        config = self.conda_config
        for is_dev, deps in ((False, config.optional_dependencies), (True, config.dev_dependencies)):
            if deps and (dev or not is_dev):
                groups.update(deps.keys())
        if not dev:
            for group in self.pyproject.settings.get("dev-dependencies", {}):
                groups.remove(group)
        return groups

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        result = super().get_dependencies(group) if group in super().iter_groups() else {}

        config = self.conda_config
        group = group or "default"

        dev = group not in config.optional_dependencies
        if group in config.optional_dependencies and group in config.dev_dependencies:
            self.core.ui.echo(
                f"The {group} group exists in both [optional-dependencies] "
                "and [dev-dependencies], the former is taken.",
                err=True,
                style="warning",
            )
        deps = self.get_conda_pyproject_dependencies(group, dev)

        for line in deps:
            req = parse_requirement(f"conda:{line}")
            req.groups = [group]
            # search for package with extras to remove it
            pypi_req = next((v for v in result.values() if v.conda_name == req.conda_name), None)
            if pypi_req is not None:
                result.pop(pypi_req.identify())
                if not req.specifier:
                    req.specifier = pypi_req.specifier
                if pypi_req.marker:
                    req.marker = pypi_req.marker
                if pypi_req.extras:
                    req.extras = pypi_req.extras
                req.groups = pypi_req.groups
            result[req.identify()] = req

        if self.conda_config.as_default_manager:
            for k in list(result):
                if is_conda_managed(req := result[k], config):
                    result[k] = as_conda_requirement(req)

        return result

    def add_dependencies(
        self,
        requirements: dict[str, Requirement],
        to_group: str = "default",
        dev: bool = False,
        show_message: bool = True,
    ) -> None:
        conda_requirements = {n: r for n, r in requirements.items() if isinstance(r, CondaRequirement)}
        requirements = {n: r for n, r in requirements.items() if n not in conda_requirements} | {
            n: r.as_named_requirement() for n, r in conda_requirements.items() if r.is_python_package
        }
        if self.conda_config.as_default_manager:
            conda_requirements = {
                n: r for n, r in conda_requirements.items() if not r.is_python_package or r.channel or r.build_string
            }
        if conda_requirements:
            deps = self.get_conda_pyproject_dependencies(to_group, dev, set_defaults=True)
            cast(Array, deps).multiline(True)
            for _, dep in conda_requirements.items():
                matched_index = next((i for i, r in enumerate(deps) if dep.matches(f"conda:{r}")), None)
                req = dep.as_line(with_channel=True)
                if matched_index is None:
                    deps.append(req)
                else:
                    deps[matched_index] = req

        super().add_dependencies(requirements, to_group, dev, show_message)

    def get_environment(self) -> BaseEnvironment:
        if not self.conda_config.is_initialized:
            return super().get_environment()

        if not self.config["python.use_venv"]:
            raise ProjectError("python.use_venv is required to use Conda.")
        if get_venv_like_prefix(self.python.executable) is None:
            raise ProjectError("Conda environment not detected.")

        return self.environment_class(self)

    def get_provider(
        self,
        strategy: str = "all",
        tracked_names: Iterable[str] | None = None,
        for_install: bool = False,
        ignore_compatibility: bool = True,
        direct_minimal_versions: bool = False,
    ) -> BaseProvider:
        from pdm_conda.resolver.providers import BaseProvider, CondaBaseProvider

        kwargs = {"direct_minimal_versions": direct_minimal_versions}
        provider = super().get_provider(strategy, tracked_names, for_install, ignore_compatibility, **kwargs)
        if isinstance(provider, BaseProvider) and not isinstance(provider, CondaBaseProvider):
            kwargs["locked_candidates"] = provider.locked_candidates
            return CondaBaseProvider(provider.repository, **kwargs)  # type: ignore[arg-type]
        return provider

    def _get_python_finder(self, search_venv: bool = True) -> Finder:
        finder = super()._get_python_finder(search_venv)
        from pdm_conda.cli.commands.venv.utils import CondaProvider

        if self.conda_config.is_initialized:
            finder.add_provider(CondaProvider(self), 0)
        return finder

    @property
    def is_distribution(self) -> bool:
        if self._is_distribution is not None:
            return self._is_distribution
        return super().is_distribution

    @is_distribution.setter
    def is_distribution(self, value: bool | None):
        self._is_distribution = value
