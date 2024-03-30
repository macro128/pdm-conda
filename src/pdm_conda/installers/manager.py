from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.installers import InstallManager

from pdm_conda.conda import conda_install, conda_uninstall
from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.setup import CondaSetupDistribution

if TYPE_CHECKING:
    from importlib.metadata import Distribution

    from pdm_conda.environments import BaseEnvironment
    from pdm_conda.models.candidates import Candidate


class CondaInstallManager(InstallManager):
    def __init__(self, environment: BaseEnvironment, *, use_install_cache: bool = False) -> None:
        super().__init__(environment, use_install_cache=use_install_cache)
        self.environment = cast(CondaEnvironment, environment)
        self._num_install = 0
        self._num_remove = 0
        self._batch_install: list[str] = []
        self._batch_remove: list[str] = []

    def prepare_batch_operations(self, num_install: int, num_remove: int):
        self._num_install = num_install
        self._num_remove = num_remove

    def _run_with_conda(self, conda_func, new_requirement: str, requirements: list[str], min_requirements: int):
        requirements.append(new_requirement)
        if len(requirements) >= min_requirements:
            try:
                conda_func(
                    self.environment.project,
                    list(requirements),
                    no_deps=True,
                )
                requirements.clear()
            except:
                if min_requirements == 0:
                    requirements.clear()
                raise

    def install(self, candidate: Candidate) -> Distribution:
        """Install candidate, use conda if conda package else default installer.

        :param candidate: candidate to install
        """
        if isinstance(candidate, CondaCandidate):
            self._run_with_conda(
                conda_install,
                f"{candidate.link.url_without_fragment}#{candidate.link.hash}",
                self._batch_install,
                self._num_install,
            )
            return candidate.distribution

        return super().install(candidate)

    def uninstall(self, dist: Distribution) -> None:
        """Uninstall distribution, use conda if conda package else default uninstaller.

        :param dist: distribution to uninstall
        """
        if isinstance(dist, CondaSetupDistribution):
            self._run_with_conda(conda_uninstall, dist.name, self._batch_remove, self._num_remove)
        else:
            super().uninstall(dist)

    def overwrite(self, dist: Distribution, candidate: Candidate) -> None:
        """Overwrite distribution with candidate, uninstall and install with conda if conda package else default
        overwrite.

        :param dist: distribution to uninstall
        :param candidate: candidate to install
        """
        if isinstance(candidate, CondaCandidate) or isinstance(dist, CondaSetupDistribution):
            self.uninstall(dist)
            self.install(candidate)
        else:
            super().overwrite(dist, candidate)
