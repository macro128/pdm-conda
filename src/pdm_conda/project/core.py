from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

from pdm.exceptions import PdmUsageError, ProjectError
from pdm.models.python import PythonInfo
from pdm.project import Project
from pdm.project.lockfile import Lockfile
from pdm.utils import get_venv_like_prefix
from tomlkit.items import Array

from pdm_conda import logger
from pdm_conda.models.config import PluginConfig
from pdm_conda.models.requirements import CondaRequirement, as_conda_requirement, is_conda_managed, parse_requirement
from pdm_conda.project.project_file import PyProject

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

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
        self._conda_mapping: dict[str, str] = {}
        self._pypi_mapping: dict[str, str] = {}
        self.conda_config = PluginConfig.load_config(self)
        self._is_distribution: bool | None = None
        self._base_env: Path | None = None

    @property
    def virtual_packages(self) -> set[CondaRequirement]:
        from pdm_conda.environments import CondaEnvironment

        if isinstance(self.environment, CondaEnvironment):
            return self.environment.virtual_packages
        return set()

    @property
    def platform(self) -> str:
        from pdm_conda.environments import CondaEnvironment

        if isinstance(self.environment, CondaEnvironment):
            return self.environment.platform
        return ""

    @property
    def default_channels(self) -> list[str]:
        from pdm_conda.environments import CondaEnvironment

        if isinstance(self.environment, CondaEnvironment):
            return self.environment.default_channels
        return []

    @property
    def base_env(self) -> Path:
        if self._base_env is None:
            from pdm_conda.conda import conda_base_path

            self._base_env = conda_base_path(self)
        return self._base_env

    @property
    def locked_repository(self) -> LockedRepository:
        try:
            lockfile = self.lockfile._data.unwrap()
        except ProjectError:
            lockfile = {}

        return self.locked_repository_class(lockfile=lockfile, sources=self.sources, environment=self.environment)  # type: ignore

    @Project.python.setter
    @PluginConfig.check_active
    def python(self, value: PythonInfo) -> None:
        if not self.conda_config.is_initialized:
            Project.python.fset(self, value)
            return

        self._python = value
        self._saved_python = value.path.as_posix()
        self.environment = None

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
        if not config.is_initialized:
            return groups
        for is_dev, deps in ((False, config.optional_dependencies), (True, config.dev_dependencies)):
            if deps and (dev or not is_dev):
                groups.update(deps.keys())
        if not dev:
            for group in self.pyproject.settings.get("dev-dependencies", {}):
                groups.remove(group)
        return groups

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        config = self.conda_config
        if not config.is_initialized:
            return super().get_dependencies(group)

        group = group or "default"
        dev = group not in config.optional_dependencies
        try:
            result = super().get_dependencies(group)
        except PdmUsageError:
            result = {}

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
        write: bool = True,
    ) -> None:
        conda_requirements = {n: r for n, r in requirements.items() if isinstance(r, CondaRequirement)}
        requirements = {n: r for n, r in requirements.items() if n not in conda_requirements} | {
            n: r.as_named_requirement() for n, r in conda_requirements.items() if r.is_python_package
        }
        if self.conda_config.is_initialized:
            if self.conda_config.as_default_manager:
                conda_requirements = {
                    n: r
                    for n, r in conda_requirements.items()
                    if not r.is_python_package or r.channel or r.build_string
                }
            if conda_requirements:
                deps = self.get_conda_pyproject_dependencies(to_group, dev, set_defaults=True)
                python_deps, _ = self.use_pyproject_dependencies(to_group, dev)
                cast(Array, deps).multiline(True)
                for name, dep in conda_requirements.items():
                    matched_index = next((i for i, r in enumerate(deps) if dep.matches(f"conda:{r}")), None)
                    req = dep.as_line(with_channel=True)
                    if matched_index is None:
                        deps.append(req)
                    else:
                        deps[matched_index] = req
                    if name not in requirements:
                        matched_index = next((i for i, r in enumerate(python_deps) if dep.matches(r)), None)
                        if matched_index is not None:
                            python_deps.pop(matched_index)
        else:
            assert not conda_requirements, "Conda is not initialized but conda requirements are present."

        super().add_dependencies(requirements, to_group, dev, show_message, write=write)

    @PluginConfig.check_active
    def get_environment(self) -> BaseEnvironment:
        if not self.conda_config.is_initialized:
            return super().get_environment()

        if not get_venv_like_prefix(self.python.executable)[1]:
            logger.debug("Conda environment not detected.")
            return super().get_environment()
        if not self.config["python.use_venv"]:
            raise ProjectError("python.use_venv is required to use Conda.")
        from pdm_conda.environments import CondaEnvironment

        return CondaEnvironment(self)

    def get_provider(
        self,
        strategy: str = "all",
        tracked_names: Iterable[str] | None = None,
        for_install: bool = False,
        ignore_compatibility: bool = True,
        direct_minimal_versions: bool = False,
    ) -> BaseProvider:
        if not self.conda_config.is_initialized:
            return super().get_provider(strategy, tracked_names, for_install, ignore_compatibility)

        from pdm_conda.resolver.providers import BaseProvider, CondaBaseProvider

        kwargs = {"direct_minimal_versions": direct_minimal_versions}
        provider = super().get_provider(strategy, tracked_names, for_install, ignore_compatibility, **kwargs)
        if isinstance(provider, BaseProvider) and not isinstance(provider, CondaBaseProvider):
            kwargs["locked_candidates"] = provider.locked_candidates
            return CondaBaseProvider(provider.repository, **kwargs)  # type: ignore[arg-type]
        return provider

    @property
    def is_distribution(self) -> bool:
        if self._is_distribution is not None:
            return self._is_distribution
        return super().is_distribution

    @is_distribution.setter
    def is_distribution(self, value: bool | None):
        self._is_distribution = value

    @PluginConfig.check_active
    def find_interpreters(
        self,
        python_spec: str | None = None,
        search_venv: bool | None = None,
    ) -> Iterable[PythonInfo]:
        if not self.conda_config.is_initialized:
            yield from super().find_interpreters(python_spec, search_venv)
        else:
            roots = set()
            if self.base_env:
                roots.add(self.base_env)
            for i in super().find_interpreters(python_spec, search_venv):
                if (venv := i.get_venv()) is not None and venv.is_conda:
                    if (root := venv.root) not in roots:
                        roots.add(root)
                        yield i
                else:
                    yield i
