from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from pdm.installers import InstallManager

from pdm_conda.conda import conda_install, conda_uninstall
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.setup import CondaSetupDistribution

if TYPE_CHECKING:
    from importlib.metadata import Distribution

    from pdm_conda.environments import BaseEnvironment
    from pdm_conda.models.candidates import Candidate


class CondaInstallManager(InstallManager):
    def __init__(
        self,
        environment: BaseEnvironment,
        *,
        use_install_cache: bool = False,
        rename_pth: bool = False,
    ) -> None:
        super().__init__(environment, use_install_cache=use_install_cache, rename_pth=rename_pth)
        self._batch_install_queue: dict[str, str] = {}
        self._batch_install_expected: set[str] = set()
        self._batch_uninstall_queue: dict[str, str] = {}
        self._batch_uninstall_expected: set[str] = set()
        self.lock = Lock()

    def prepare_batch_operations(self, to_install: set[str], to_uninstall: set[str]):
        self._batch_install_expected = to_install
        self._batch_uninstall_expected = to_uninstall

    def _run_with_conda(
        self,
        conda_func,
        new_requirement: str,
        queue: dict[str, str],
        expected: set[str],
        op_name: str = "",
    ):
        if should_run := (new_requirement not in expected):
            queue = {new_requirement: op_name or new_requirement}
        else:
            queue[new_requirement] = op_name or new_requirement
            should_run = set(queue) == expected

        if should_run:
            with self.lock:
                conda_func(self.environment.project, list(queue.values()), no_deps=True)

    def install(self, candidate: Candidate) -> Distribution:
        """Install candidate, use conda if conda package else default installer.

        :param candidate: candidate to install
        """
        if isinstance(candidate, CondaCandidate):
            self._run_with_conda(
                conda_install,
                candidate.name,
                self._batch_install_queue,
                self._batch_install_expected,
                f"{candidate.link.url_without_fragment}#{candidate.link.hash}",
            )
            return candidate.distribution

        return super().install(candidate)

    def uninstall(self, dist: Distribution) -> None:
        """Uninstall distribution, use conda if conda package else default uninstaller.

        :param dist: distribution to uninstall
        """
        if isinstance(dist, CondaSetupDistribution):
            self._run_with_conda(
                conda_uninstall,
                dist.name,
                self._batch_uninstall_queue,
                self._batch_uninstall_expected,
            )
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
