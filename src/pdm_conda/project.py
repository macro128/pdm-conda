from pathlib import Path
from typing import Iterable, cast

from pdm.core import Core
from pdm.exceptions import ProjectError
from pdm.models.environment import Environment
from pdm.models.repositories import LockedRepository
from pdm.project import Project
from pdm.resolver.providers import BaseProvider
from pdm.utils import get_venv_like_prefix
from tomlkit.items import Array

from pdm_conda.models.config import PluginConfig
from pdm_conda.models.requirements import (
    CondaRequirement,
    Requirement,
    as_conda_requirement,
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
        from pdm_conda.installers.manager import CondaInstallManager
        from pdm_conda.installers.synchronizers import CondaSynchronizer
        from pdm_conda.models.environment import CondaEnvironment
        from pdm_conda.models.repositories import (
            LockedCondaRepository,
            PyPICondaRepository,
        )
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
        self._conda_mapping: dict[str, str] = dict()
        self._pypi_mapping: dict[str, str] = dict()
        self.conda_config = PluginConfig.load_config(self)

    def _check_update_info(self, prop):
        if prop is None:
            self._get_conda_info()

    @property
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

    def _get_conda_info(self):
        from pdm_conda.conda import conda_info

        info = conda_info(self)
        self._virtual_packages = info["virtual_packages"]
        self._platform = info["platform"]
        self._default_channels = info["channels"]

    def get_conda_pyproject_dependencies(self, group: str, dev: bool = False, set_defaults=False) -> list[str]:
        """
        Get the conda dependencies array in the pyproject.toml
        """

        def _getter(conf, name, default, set_defaults=False):
            return (conf.setdefault if set_defaults else conf.get)(name, default)

        settings = _getter(self.pyproject.settings, "conda", dict(), set_defaults)
        if group == "default":
            group = "dependencies"
        else:
            name = "optional" if not dev else "dev"
            settings = _getter(settings, f"{name}-dependencies", dict(), set_defaults)
        return _getter(settings, group, [], set_defaults)

    def iter_groups(self) -> Iterable[str]:
        groups = set(super().iter_groups())
        config = self.conda_config
        for deps in (config.optional_dependencies, config.dev_dependencies):
            if deps:
                groups.update(deps.keys())
        return groups

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        if group in super().iter_groups():
            result = super().get_dependencies(group)
        else:
            result = dict()

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
            # search for package with extras to remove it
            pypi_req = next((v for v in result.values() if v.conda_name == req.conda_name), None)
            if pypi_req is not None:
                result.pop(pypi_req.identify())
                if not req.specifier:
                    req.specifier = pypi_req.specifier
            result[req.identify()] = req

        if self.conda_config.as_default_manager:
            for k in list(result):
                req = result[k]
                if req.name not in self.conda_config.excludes and not isinstance(req, CondaRequirement):
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

    def get_environment(self) -> Environment:
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
    ) -> BaseProvider:
        from pdm_conda.resolver.providers import (
            CondaBaseProvider,
            CondaEagerUpdateProvider,
            CondaReusePinProvider,
            EagerUpdateProvider,
        )

        provider = super().get_provider(strategy, tracked_names, for_install, ignore_compatibility)
        args = [provider.repository, provider.allow_prereleases, provider.overrides]
        provider_class = CondaBaseProvider
        if not isinstance(provider, BaseProvider):
            provider_class = (
                CondaEagerUpdateProvider  # type: ignore
                if isinstance(
                    provider,
                    EagerUpdateProvider,
                )
                else CondaReusePinProvider  # type: ignore
            )
            args = [provider.preferred_pins, provider.tracked_names] + args
        return provider_class(*args)
