from installer.exceptions import InstallerError
from pdm.compat import Distribution
from pdm.exceptions import RequirementError, UninstallError
from pdm.installers import InstallManager

from pdm_conda.models.candidates import Candidate, CondaCandidate


class CondaInstallManager(InstallManager):
    def install(self, candidate: Candidate) -> None:
        if isinstance(candidate, CondaCandidate):
            try:
                from pdm_conda.plugin import conda_install

                if candidate.req.package is None:
                    raise ValueError("Uninitialized conda requirement")
                conda_install(self.environment.project, candidate.req.package.link.url, no_deps=True)
            except (RequirementError, ValueError) as e:
                raise InstallerError(e) from e
        else:
            super().install(candidate)

    def uninstall(self, dist: Distribution) -> None:
        if dist.name.startswith("conda:"):
            try:
                from pdm_conda.plugin import conda_uninstall

                conda_uninstall(self.environment.project, dist.name.split("conda:")[-1], no_deps=True)
            except RequirementError as e:
                raise UninstallError(e) from e
        else:
            super().uninstall(dist)
