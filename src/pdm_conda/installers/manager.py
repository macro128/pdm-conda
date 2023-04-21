from importlib.metadata import Distribution
from typing import cast

from installer.exceptions import InstallerError
from pdm.exceptions import RequirementError, UninstallError
from pdm.installers import InstallManager

from pdm_conda.conda import conda_install, conda_uninstall
from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.environment import CondaEnvironment, Environment
from pdm_conda.models.setup import CondaSetupDistribution


class CondaInstallManager(InstallManager):
    def __init__(self, environment: Environment, *, use_install_cache: bool = False) -> None:
        super().__init__(environment, use_install_cache=use_install_cache)
        self.environment = cast(CondaEnvironment, environment)
        self._num_install = 0
        self._num_remove = 0
        self._batch_install: list[CondaCandidate] = []
        self._batch_remove: list[CondaSetupDistribution] = []

    def prepare_batch_operations(self, num_install: int, num_remove: int):
        self._num_install = num_install
        self._num_remove = num_remove

    def install(self, candidate: Candidate) -> None:
        """
        Install candidate, use conda if conda package else default installer
        :param candidate: candidate to install
        """
        if isinstance(candidate, CondaCandidate):
            try:
                self._batch_install.append(candidate)
                if len(self._batch_install) >= self._num_install:
                    conda_install(
                        self.environment.project,
                        [f"{c.link.url_without_fragment}#{c.link.hash}" for c in self._batch_install],
                        no_deps=True,
                    )
                    self._batch_install.clear()
            except (RequirementError, ValueError) as e:
                raise InstallerError(e) from e
        else:
            super().install(candidate)

    def uninstall(self, dist: Distribution) -> None:
        """
        Uninstall distribution, use conda if conda package else default uninstaller
        :param dist: distribution to uninstall
        """
        if isinstance(dist, CondaSetupDistribution):
            try:
                self._batch_remove.append(dist)
                if len(self._batch_remove) >= self._num_remove:
                    conda_uninstall(self.environment.project, [d.name for d in self._batch_remove], no_deps=True)
                    self._batch_remove.clear()
            except RequirementError as e:
                raise UninstallError(e) from e
        else:
            super().uninstall(dist)
