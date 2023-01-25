from importlib.metadata import Distribution
from typing import cast

from installer.exceptions import InstallerError
from pdm.exceptions import RequirementError, UninstallError
from pdm.installers import InstallManager

from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.environment import CondaEnvironment, Environment
from pdm_conda.models.setup import CondaSetupDistribution
from pdm_conda.plugin import conda_install, conda_uninstall


class CondaInstallManager(InstallManager):
    def __init__(self, environment: Environment, *, use_install_cache: bool = False) -> None:
        super().__init__(environment, use_install_cache=use_install_cache)
        self.environment = cast(CondaEnvironment, environment)

    def install(self, candidate: Candidate) -> None:
        """
        Install candidate, use conda if conda package else default installer
        :param candidate: candidate to install
        """
        if isinstance(candidate, CondaCandidate):
            try:
                conda_install(self.environment.project, candidate.link.url, no_deps=True)
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
                conda_uninstall(self.environment.project, dist.name, no_deps=True)
            except RequirementError as e:
                raise UninstallError(e) from e
        else:
            super().uninstall(dist)
