from importlib.metadata import Distribution

from installer.exceptions import InstallerError
from pdm.exceptions import RequirementError, UninstallError
from pdm.installers import InstallManager

from pdm_conda.models.candidates import Candidate, CondaCandidate
from pdm_conda.models.setup import CondaSetupDistribution


class CondaInstallManager(InstallManager):
    def install(self, candidate: Candidate) -> None:
        """
        Install candidate, use conda if conda package else default installer
        :param candidate: candidate to install
        """
        if isinstance(candidate, CondaCandidate):
            try:
                from pdm_conda.plugin import conda_install

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
                from pdm_conda.plugin import conda_uninstall

                conda_uninstall(self.environment.project, dist.name, no_deps=True)
            except RequirementError as e:
                raise UninstallError(e) from e
        else:
            super().uninstall(dist)
